# OctoPrint-PSUControl-Tapo

Standalone OctoPrint plugin to switch a TP-Link Tapo smart plug (tested with P110 on TPAP firmware).
Adds a plug icon to the top bar (green = on, red = off, grey = error; click to toggle) and a settings page with auto-detect.

## Requirements
- OctoPrint on **Python 3.11+**: check Settings > About > System info `python` or `~/oprint/bin/python --version`
- Tapo app: **Me > Third-Party Services > Third-Party Compatibility = ON**

## Install
Plugin Manager > Get More > "...from URL":
```
https://github.com/sudo-atharva/OctoPrint-PSUControl-Tapo/archive/main.zip
```
Restart OctoPrint.

## Setup
Settings > **Tapo Plug**: enter Tapo email + password, click **Auto-detect**, pick your plug, Save. Use the On/Off buttons there to test; errors are shown next to them.

**Auto-off** (`auto-off` branch, testing): tick "Turn plug off after a print finishes" and set the delay in minutes. Starting a new print cancels a pending auto-off; cancelled/failed prints don't trigger it.
Test build install URL: `https://github.com/sudo-atharva/OctoPrint-PSUControl-Tapo/archive/refs/heads/auto-off.zip`

Uses an unreleased python-kasa build ([PR #1592](https://github.com/python-kasa/python-kasa/pull/1592)) because released python-kasa does not support TPAP firmware yet.

`tapo_test.py` is a standalone CLI test: `python tapo_test.py <ip> status|on|off` (credentials via `TAPO_USERNAME` / `TAPO_PASSWORD` env vars).
