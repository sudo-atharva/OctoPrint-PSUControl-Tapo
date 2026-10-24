# coding=utf-8
import asyncio
import socket
import threading

import flask
import octoprint.plugin
from kasa import AuthenticationError, Credentials, Device, DeviceConfig, Discover
from kasa import DeviceConnectionParameters, DeviceEncryptionType, DeviceFamily

# Newer Tapo firmware (P110 1.4+). Connecting with these params skips UDP discovery,
# which some networks/hosts (e.g. OctoPi) never get a reply to.
TPAP = DeviceConnectionParameters(DeviceFamily.SmartTapoPlug, DeviceEncryptionType.Tpap,
                                  login_version=2, http_port=80)


async def connect(host, creds):
    try:
        return await Device.connect(config=DeviceConfig(host, credentials=creds, connection_type=TPAP, timeout=10))
    except AuthenticationError:
        raise
    except Exception as direct:
        # older firmware (KLAP/AES): let UDP discovery pick the protocol
        try:
            return await Discover.discover_single(host, credentials=creds, timeout=5)
        except Exception as udp:
            raise Exception("direct TPAP: %s: %s | UDP discovery: %s" % (type(direct).__name__, direct, udp)) from direct


async def port_open(ip, port=80):
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(ip, port), 2)
        w.close()
        return True
    except Exception:
        return False


class TapoPlugin(octoprint.plugin.SettingsPlugin,
                 octoprint.plugin.TemplatePlugin,
                 octoprint.plugin.AssetPlugin,
                 octoprint.plugin.EventHandlerPlugin,
                 octoprint.plugin.SimpleApiPlugin):

    def __init__(self):
        # kasa is async; one long-lived loop keeps the plug session alive between calls
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._dev = None
        self._off_timer = None

    def get_settings_defaults(self):
        return dict(host="", username="", password="", auto_off=False, auto_off_delay=2)

    # ---- auto-off after print ----

    def on_event(self, event, payload):
        if event == "PrintStarted":
            self._cancel_auto_off()
        elif event == "PrintDone" and self._settings.get_boolean(["auto_off"]):
            minutes = max(0.0, float(self._settings.get(["auto_off_delay"]) or 0))
            self._cancel_auto_off()
            self._off_timer = threading.Timer(minutes * 60, self._auto_off)
            self._off_timer.daemon = True
            self._off_timer.start()
            self._logger.info("Print done, plug turns off in %s min", minutes)

    def _cancel_auto_off(self):
        if self._off_timer:
            self._off_timer.cancel()
            self._off_timer = None
            self._logger.info("Auto-off cancelled")

    def _auto_off(self):
        self._off_timer = None
        # re-check at fire time: user may have disabled it or started another print meanwhile
        if not self._settings.get_boolean(["auto_off"]) or self._printer.is_printing():
            return
        try:
            self._run(self._control("off"))
            self._logger.info("Auto-off: plug turned off")
        except Exception:
            self._logger.exception("Auto-off failed")

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
                self._dev = await connect(self._settings.get(["host"]), self._credentials())
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
        # Tapo plugs serve HTTP on 80; only try a (slow) login where that port is open
        if not await port_open(ip):
            return None
        dev = None
        try:
            dev = await Device.connect(config=DeviceConfig(ip, credentials=creds, connection_type=TPAP, timeout=10))
            return dict(host=ip, alias=dev.alias, model=dev.model, note="")
        except Exception as e:
            if isinstance(e, AuthenticationError) or getattr(getattr(e, "error_code", None), "name", "") == "ACCOUNT_ERROR":
                return dict(host=ip, alias="?", model="Tapo", note="login failed - check email/password")
            self._logger.info("Probe %s (port 80 open): %s: %s", ip, type(e).__name__, e)
            return None
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
