"""Test control of a Tapo P110 plug over local network.

Setup:
    pip install python-kasa

Credentials = your Tapo app account (email + password), set as env vars:
    PowerShell:  $env:TAPO_USERNAME="you@example.com"; $env:TAPO_PASSWORD="secret"

Usage:
    python tools/tapo_test.py 192.168.1.50 status
    python tools/tapo_test.py 192.168.1.50 on
    python tools/tapo_test.py 192.168.1.50 off
"""
import argparse
import asyncio
import os
import sys

from kasa import Credentials, Discover


async def main(host, action):
    user, pw = os.environ.get("TAPO_USERNAME"), os.environ.get("TAPO_PASSWORD")
    if not user or not pw:
        sys.exit("Set TAPO_USERNAME and TAPO_PASSWORD env vars first.")

    dev = await Discover.discover_single(host, credentials=Credentials(user, pw))
    try:
        await dev.update()
        if action == "on":
            await dev.turn_on()
        elif action == "off":
            await dev.turn_off()
        await dev.update()

        print(f"{dev.alias} ({dev.model}) is {'ON' if dev.is_on else 'OFF'}")
        energy = dev.modules.get("Energy")
        if energy:
            print(f"Power now: {energy.current_consumption} W")
    finally:
        await dev.disconnect()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("host", help="plug IP address (see router or Tapo app > device info)")
    p.add_argument("action", choices=["on", "off", "status"])
    a = p.parse_args()
    asyncio.run(main(a.host, a.action))
