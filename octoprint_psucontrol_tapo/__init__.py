# coding=utf-8
import asyncio
import socket
import threading

import flask
import octoprint.plugin
from kasa import AuthenticationError, Credentials, Discover


class TapoPlugin(octoprint.plugin.SettingsPlugin,
                 octoprint.plugin.TemplatePlugin,
                 octoprint.plugin.AssetPlugin,
                 octoprint.plugin.SimpleApiPlugin):

    def __init__(self):
        # kasa is async; one long-lived loop keeps the plug session alive between calls
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._dev = None

    def get_settings_defaults(self):
        return dict(host="", username="", password="")

    def get_settings_restricted_paths(self):
        return dict(admin=[["username"], ["password"]])

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._run(self._drop_device())

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=True),
                dict(type="navbar", custom_bindings=True)]

    def get_assets(self):
        return dict(js=["js/psucontrol_tapo.js"])

    # ---- API: GET = state, POST on/off/discover ----

    def get_api_commands(self):
        return dict(on=[], off=[], discover=[])

    def on_api_get(self, request):
        return self._state_response("status")

    def on_api_command(self, command, data):
        if command == "discover":
            creds = self._credentials(data.get("username"), data.get("password"))
            return flask.jsonify(devices=self._run(self._scan(creds)))
        return self._state_response(command)

    def _state_response(self, action):
        if not self._settings.get(["host"]):
            return flask.jsonify(on=None, error="No plug IP set (Settings > Tapo Plug)")
        try:
            return flask.jsonify(on=self._run(self._control(action)), error=None)
        except Exception as e:
            self._logger.exception("Tapo %s failed", action)
            return flask.jsonify(on=None, error="%s: %s" % (type(e).__name__, e))

    # ---- plug control ----

    def _run(self, coro, timeout=60):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _credentials(self, username=None, password=None):
        return Credentials(username or self._settings.get(["username"]),
                           password or self._settings.get(["password"]))

    async def _control(self, action):
        try:
            if self._dev is None:
                self._dev = await Discover.discover_single(
                    self._settings.get(["host"]), credentials=self._credentials(), timeout=10)
            await self._dev.update()
            if action != "status":
                await (self._dev.turn_on() if action == "on" else self._dev.turn_off())
                await self._dev.update()
            return self._dev.is_on
        except Exception:
            await self._drop_device()
            raise

    async def _drop_device(self):
        dev, self._dev = self._dev, None
        if dev:
            try:
                await dev.disconnect()
            except Exception:
                pass

    # ---- auto-detect ----

    async def _scan(self, creds):
        # ponytail: probes the local /24 only (broadcast discovery is unreliable on some networks); widen if plug lives on another subnet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        me = s.getsockname()[0]
        s.close()
        base = me.rsplit(".", 1)[0]
        self._logger.info("Scanning %s.1-254 for Tapo plugs", base)
        found = await asyncio.gather(*(self._probe("%s.%d" % (base, i), creds) for i in range(1, 255)))
        return [d for d in found if d]

    async def _probe(self, ip, creds):
        dev = None
        try:
            dev = await Discover.discover_single(ip, credentials=creds, timeout=3)
            await dev.update()
            return dict(host=ip, alias=dev.alias, model=dev.model, note="")
        except AuthenticationError:
            return dict(host=ip, alias="?", model=getattr(dev, "model", "Tapo"), note="login failed - check email/password")
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            # anything that answered discovery but failed later is still worth showing
            if dev is None and "Timed out" in str(e):
                return None
            self._logger.info("Probe %s: %s", ip, e)
            return dict(host=ip, alias="?", model="?", note=str(e)[:150])
        finally:
            if dev:
                try:
                    await dev.disconnect()
                except Exception:
                    pass


__plugin_name__ = "Tapo Plug"
__plugin_pythoncompat__ = ">=3.11,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = TapoPlugin()
