"""Async aiohttp client for the EASYTRON heatapp Zentrale.

Port of /tmp/easytron_client.py that can be used inside Home Assistant
without blocking the event loop.

Auth flow:
  1. POST /api/user/token/challenge  -> challenge devicetoken
  2. md5(password + challenge) as raw strings
  3. POST /api/user/token/response -> encrypted session devicetoken
  4. AES-256-CBC decrypt with key=SHA256(password), IV=hardcoded base64
  5. Every signed request: sorted k=v|...| + devicetoken, md5 -> request_signature

See the constants AES_IV, PRODUCT, UDID for values extracted from the
device's assets.min.js.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from typing import Any

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

_LOGGER = logging.getLogger(__name__)

# Hardcoded in the device's assets.min.js
AES_IV = base64.b64decode("D3GC5NQEFH13is04KD2tOg==")
PRODUCT = "stiebel-eltron"
UDID = "web"


class EasytronAuthError(Exception):
    """Raised when login fails."""


class EasytronApiError(Exception):
    """Raised on other API failures."""


class EasytronClient:
    """Async client for the heatapp HTTP API."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        base = host.strip().rstrip("/")
        if not base.startswith("http"):
            base = "http://" + base
        self._base = base
        self._host = base.replace("http://", "").replace("https://", "").split(":")[0]
        self._username = username
        self._password = password
        self._session = session
        self._devicetoken: str | None = None
        self._userid: int | None = None
        self._reqcount = 0
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    @property
    def base_url(self) -> str:
        return self._base

    # ------------------------------------------------------------------
    # Low level HTTP
    # ------------------------------------------------------------------
    async def _post(
        self,
        path: str,
        data: dict[str, Any],
        timeout: int = 30,
    ) -> str:
        """POST form-encoded data, returning text body.

        Lists are encoded as repeated key[] params to match jQuery default.
        """
        # Flatten list values into key[]=v pairs (ordered list of tuples).
        form: list[tuple[str, str]] = []
        for k, v in data.items():
            if isinstance(v, list):
                for item in v:
                    form.append((f"{k}[]", str(item)))
            elif v is None:
                continue
            else:
                form.append((k, str(v)))

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        }
        url = self._base + path
        try:
            async with self._session.post(
                url,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                text = await resp.text()
                return text
        except asyncio.TimeoutError as err:
            raise EasytronApiError(f"Timeout posting {path}") from err
        except aiohttp.ClientError as err:
            raise EasytronApiError(f"HTTP error posting {path}: {err}") from err

    async def _post_json(
        self,
        path: str,
        data: dict[str, Any],
        timeout: int = 30,
    ) -> dict[str, Any]:
        import json

        text = await self._post(path, data, timeout=timeout)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    async def login(self) -> None:
        """Perform full challenge/response login."""
        ch = await self._post_json(
            "/api/user/token/challenge",
            {"udid": UDID, "product": PRODUCT},
        )
        if not ch.get("success") or "devicetoken" not in ch:
            raise EasytronAuthError(f"challenge failed: {ch}")
        challenge_token = ch["devicetoken"]

        hashed = hashlib.md5(
            (self._password + challenge_token).encode()
        ).hexdigest()
        lg = await self._post_json(
            "/api/user/token/response",
            {
                "udid": UDID,
                "product": PRODUCT,
                "login": self._username,
                "devicename": "HomeAssistant",
                "token": challenge_token,
                "hashed": hashed,
            },
        )
        if not lg.get("success") or "devicetoken_encrypted" not in lg:
            raise EasytronAuthError(f"login failed: {lg}")

        enc = base64.b64decode(lg["devicetoken_encrypted"])
        key = hashlib.sha256(self._password.encode()).digest()
        # AES work is CPU-light and synchronous but fast; fine in loop.
        cipher = AES.new(key, AES.MODE_CBC, AES_IV)
        self._devicetoken = unpad(cipher.decrypt(enc), AES.block_size).decode()
        self._userid = lg["userid"]
        self._reqcount = 0
        _LOGGER.debug("EASYTRON login success userid=%s", self._userid)

    async def async_test_connection(self) -> dict[str, Any]:
        """Validate credentials + host. Returns the ping response."""
        await self.login()
        ping = await self._post_json(
            "/api/ping", {"udid": UDID, "product": PRODUCT}
        )
        if not ping.get("success"):
            raise EasytronApiError(f"ping failed: {ping}")
        return ping

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    @staticmethod
    def _sign(devicetoken: str, params: dict[str, Any]) -> str:
        parts: list[str] = []
        for k in sorted(params.keys()):
            v = params[k]
            if isinstance(v, list):
                if len(v) >= 2:
                    parts.append(f"{k}=[{','.join(map(str, v))}]")
                else:
                    parts.append(f"{k}={v[0]}")
            elif v is None:
                continue
            else:
                parts.append(f"{k}={v}")
        sigstr = "|".join(parts) + "|"
        return hashlib.md5((sigstr + devicetoken).encode()).hexdigest()

    # ------------------------------------------------------------------
    # Signed call
    # ------------------------------------------------------------------
    async def call(
        self,
        path: str,
        extra: dict[str, Any] | None = None,
        timeout: int = 30,
        _retry: bool = True,
    ) -> dict[str, Any]:
        """Make a signed POST. Auto re-login on session expiry."""
        async with self._lock:
            if not self._devicetoken:
                await self.login()
            self._reqcount += 1
            params: dict[str, Any] = dict(extra or {})
            params["product"] = PRODUCT
            params["udid"] = UDID
            params["reqcount"] = self._reqcount
            params["userid"] = self._userid
            params["request_signature"] = self._sign(
                self._devicetoken,  # type: ignore[arg-type]
                {k: v for k, v in params.items() if k != "request_signature"},
            )
            data = await self._post_json(path, params, timeout=timeout)

        if data.get("loginRejected") and _retry:
            _LOGGER.debug("Session rejected, re-logging in")
            self._devicetoken = None
            return await self.call(path, extra, timeout=timeout, _retry=False)
        return data

    # ------------------------------------------------------------------
    # Convenience wrappers for documented endpoints
    # ------------------------------------------------------------------
    async def ping(self) -> dict[str, Any]:
        return await self._post_json(
            "/api/ping", {"udid": UDID, "product": PRODUCT}
        )

    async def version(self) -> dict[str, Any]:
        return await self._post_json(
            "/api/version", {"udid": UDID, "product": PRODUCT}
        )

    async def dbmodules(self) -> dict[str, Any]:
        return await self.call("/shared-gw/api/gateway/dbmodules")

    async def allmodules(self) -> dict[str, Any]:
        return await self.call("/shared-gw/api/gateway/allmodules")

    async def systemstate(self) -> dict[str, Any]:
        return await self.call("/api/systemstate")

    async def datetime_get(self) -> dict[str, Any]:
        return await self.call("/admin/datetime/get")

    async def systeminformation_get(self) -> dict[str, Any]:
        return await self.call("/admin/systeminformation/get")

    async def daylist(self) -> dict[str, Any]:
        return await self.call("/api/monitor/daylist")

    async def start_inclusion(self) -> dict[str, Any]:
        return await self.call(
            "/shared-gw/api/room/setlearnmode",
            {"status": 1, "remove_device": "false"},
        )

    async def start_exclusion(self) -> dict[str, Any]:
        return await self.call(
            "/shared-gw/api/room/setlearnmode",
            {"status": 1, "remove_device": "true"},
        )

    async def stop_learnmode(self) -> dict[str, Any]:
        return await self.call(
            "/shared-gw/api/room/setlearnmode",
            {"status": 0, "remove_device": "false"},
        )

    async def poll_learnmode(self) -> dict[str, Any]:
        return await self.call("/shared-gw/api/room/polllearnmode")

    async def update_device(
        self,
        device_id: str,
        name: str,
        room_name: str,
        room_id: str | int,
        instances: list[int] | None = None,
    ) -> dict[str, Any]:
        """Rename/assign a device. roomid is required for persistence."""
        body: dict[str, Any] = {
            "id": device_id,
            "name": name,
            "room": room_name,
            "roomid": room_id,
        }
        if instances is not None:
            body["instances"] = instances
        # Floor instance assignments can take ~60s to commit.
        return await self.call(
            "/shared-gw/api/gateway/updatedevice",
            body,
            timeout=120,
        )

    async def remove_device(self, device_id: str) -> dict[str, Any]:
        """SAFE remove (DB only, no radio action)."""
        return await self.call(
            "/shared-gw/api/gateway/removedevice", {"id": device_id}
        )

    async def reorganize(self) -> dict[str, Any]:
        return await self.call("/shared-gw/api/gateway/reorganize")

    async def reboot(self) -> dict[str, Any]:
        return await self.call("/common/admin/system/reboot")

    # ------------------------------------------------------------------
    # Z-Way direct API (port 8083, read-only)
    # ------------------------------------------------------------------
    async def zway_get(self, expr: str, timeout: int = 10) -> Any:
        """GET from /ZWaveAPI/Run/<expr> on port 8083.

        Only use for reads — writes desync the heatapp daemon.
        """
        import urllib.parse as _u

        url = f"http://{self._host}:8083/ZWaveAPI/Run/{_u.quote(expr, safe='.()[]=')}"
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                text = await resp.text()
                import json

                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.debug("zway_get failed: %s", err)
            return None

    async def zway_node_ids(self) -> list[int]:
        """Return the list of known Z-Way node ids."""
        res = await self.zway_get("Object.keys(zway.devices)")
        if isinstance(res, list):
            try:
                return [int(x) for x in res]
            except (TypeError, ValueError):
                return []
        return []

    async def zway_neighbours(self, node_id: int) -> list[int]:
        """Return the neighbours list for a node id (may be empty).

        The neighbours field has type "binary" in Z-Way, so querying
        .value directly returns raw bytes that JSON cannot decode.
        We wrap with JSON.stringify() to get the decoded object and
        then read .value from the parsed result.
        """
        res = await self.zway_get(
            f"JSON.stringify(zway.devices[{node_id}].data.neighbours)"
        )
        if isinstance(res, dict):
            val = res.get("value")
            if isinstance(val, list):
                return [int(x) for x in val if isinstance(x, (int, float))]
        return []

    async def zway_last_received(self, node_id: int) -> float | None:
        res = await self.zway_get(
            f"zway.devices[{node_id}].data.lastReceived.updateTime"
        )
        if isinstance(res, (int, float)):
            return float(res)
        return None
