# coding=utf-8
import asyncio
import socket
import threading

import flask
import octoprint.plugin
from kasa import AuthenticationError, Credentials, Discover


class PSUControl_Tapo(octoprint.plugin.StartupPlugin,
                      octoprint.plugin.SettingsPlugin,
                      octoprint.plugin.TemplatePlugin,
                      octoprint.plugin.AssetPlugin,
                      octoprint.plugin.SimpleApiPlugin,
                      octoprint.plugin.RestartNeedingPlugin):

    def __init__(self):
        # kasa is async; one long-lived loop keeps the plug session alive between polls
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._dev = None

    def on_startup(self, host, port):
        psucontrol_helpers = self._plugin_manager.get_helpers("psucontrol")
        if not psucontrol_helpers or "register_plugin" not in psucontrol_helpers:
            self._logger.warning("The version of PSUControl that is installed does not support plugin registration.")
            return
        psucontrol_helpers["register_plugin"](self)

    def get_settings_defaults(self):
        return dict(host="", username="", password="")

    def get_settings_restricted_paths(self):
        return dict(admin=[["username"], ["password"]])

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._run(self._drop_device())

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=True)]

    def get_assets(self):
        return dict(js=["js/psucontrol_tapo.js"])

    # ---- PSUControl sub-plugin API ----

    def turn_psu_on(self):
        self._control("on")

    def turn_psu_off(self):
        self._control("off")

    def get_psu_state(self):
        try:
            return self._control("status")
        except Exception as e:
            self._logger.error("Tapo state read failed: %s", e)
            return False

    def _run(self, coro, timeout=60):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _credentials(self, username=None, password=None):
        return Credentials(username or self._settings.get(["username"]),
                           password or self._settings.get(["password"]))

    def _control(self, action):
        return self._run(self._control_async(action))

    async def _control_async(self, action):
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

    # ---- Auto-detect ----

    def get_api_commands(self):
        return dict(discover=[])

    def on_api_command(self, command, data):
        creds = self._credentials(data.get("username"), data.get("password"))
        return flask.jsonify(devices=self._run(self._scan(creds)))

    async def _scan(self, creds):
        # ponytail: probes the local /24 only (broadcast discovery is unreliable on some networks); widen if plug lives on another subnet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        base = s.getsockname()[0].rsplit(".", 1)[0]
        s.close()
        found = await asyncio.gather(*(self._probe("%s.%d" % (base, i), creds) for i in range(1, 255)))
        return [d for d in found if d]

    async def _probe(self, ip, creds):
        try:
            dev = await Discover.discover_single(ip, credentials=creds, timeout=3)
        except AuthenticationError:
            return dict(host=ip, alias="(login failed - check email/password)", model="Tapo")
        except Exception:
            return None
        try:
            await dev.update()
            return dict(host=ip, alias=dev.alias, model=dev.model)
        except AuthenticationError:
            return dict(host=ip, alias="(login failed - check email/password)", model=dev.model)
        except Exception:
            return None
        finally:
            await dev.disconnect()


__plugin_name__ = "PSU Control - Tapo"
__plugin_pythoncompat__ = ">=3.11,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = PSUControl_Tapo()
