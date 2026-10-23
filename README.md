# OctoPrint-PSUControl-Tapo

[PSU Control](https://github.com/kantlivelong/OctoPrint-PSUControl) sub-plugin for TP-Link Tapo smart plugs (tested with P110 on TPAP firmware).

## Requirements
- OctoPrint on **Python 3.11+** (`~/oprint/bin/python --version`)
- PSU Control installed
- Tapo app: **Me > Third-Party Services > Third-Party Compatibility = ON**

## Install
```
~/oprint/bin/pip install https://github.com/sudo-atharva/OctoPrint-PSUControl-Tapo/archive/main.zip
```
or paste that URL into OctoPrint Plugin Manager > Get More > from URL. Restart OctoPrint.

## Setup
1. Settings > **PSU Control - Tapo**: enter Tapo email + password, click **Auto-detect**, pick your plug, Save.
2. Settings > **PSU Control**: set Switching and Sensing to `psucontrol_tapo`.

Uses an unreleased python-kasa build ([PR #1592](https://github.com/python-kasa/python-kasa/pull/1592)) because released python-kasa does not support TPAP firmware yet.

`tapo_test.py` is a standalone CLI test: `python tapo_test.py <ip> status|on|off` (credentials via `TAPO_USERNAME` / `TAPO_PASSWORD` env vars).
