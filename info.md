# EASYTRON (Stiebel Eltron heatapp)

Local-polling Home Assistant integration for the Stiebel Eltron **EASYTRON
heatapp Zentrale** base station.

After signing in once, every paired Z-Wave device on your EASYTRON —
thermostats, room sensors, floor heating actuators, and repeaters — is
automatically discovered and exposed as Home Assistant entities, plus
system-level diagnostics for monitoring dashboards.

## Quick start

1. Add this repository as a HACS custom repository
   (category: **Integration**)
2. Install the integration and restart Home Assistant
3. **Settings → Devices & Services → Add Integration → EASYTRON**
4. Enter your EASYTRON's local IP and credentials (defaults `Expert`/`Expert`)

The integration uses only the local HTTP API on the EASYTRON itself —
no cloud is contacted.

See the [README](README.md) for the full feature list and limitations.
