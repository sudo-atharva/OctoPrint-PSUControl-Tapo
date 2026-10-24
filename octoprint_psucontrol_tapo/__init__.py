# coding=utf-8
import asyncio
import socket
import threading

import flask
import octoprint.plugin
import octoprint.settings
from octoprint.util import RepeatedTimer
from kasa import AuthenticationError, Credentials, Device, DeviceConfig, Discover
from kasa import DeviceConnectionParameters, DeviceEncryptionType, DeviceFamily

# Tapo plugs speak one of these over HTTP :80 depending on firmware/settings (the same P110
# switched TPAP -> KLAP after toggling Third-Party Compatibility). Trying them directly
# skips UDP discovery, which some hosts (e.g. OctoPi) never get a reply to.
PROTOCOLS = [DeviceConnectionParameters(DeviceFamily.SmartTapoPlug, enc, login_version=lv, http_port=80)
             for enc, lv in ((DeviceEncryptionType.Tpap, 2), (DeviceEncryptionType.Klap, 2),
                             (DeviceEncryptionType.Aes, 2))]


def is_auth_error(e):
    return isinstance(e, AuthenticationError) or \
        getattr(getattr(e, "error_code", None), "name", "") == "ACCOUNT_ERROR"


async def connect(host, creds):
    errors = []
    for params in PROTOCOLS:
        try:
            return await Device.connect(config=DeviceConfig(host, credentials=creds, connection_type=params, timeout=10))
        except Exception as e:
            if is_auth_error(e):
                raise  # wrong login: stop, repeated attempts lock the plug for minutes
            errors.append("%s: %s" % (params.encryption_type.value, e))
    try:
        return await Discover.discover_single(host, credentials=creds, timeout=5)
    except Exception as e:
        if is_auth_error(e):
            raise
        errors.append("UDP discovery: %s" % e)
    raise Exception(" | ".join(errors))


async def port_open(ip, port=80):
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(ip, port), 2)
        w.close()
        return True
    except Exception:
        return False


class TapoPlugin(octoprint.plugin.StartupPlugin,
                 octoprint.plugin.SettingsPlugin,
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
        self._last_on = None

    def get_settings_defaults(self):
        return dict(host="", username="", password="", auto_off=False, auto_off_delay=2,
                    auto_connect=True, auto_connect_delay=15)

    # ---- auto-connect when the plug turns on (from OctoPrint, the Tapo app or the button) ----

    def on_after_startup(self):
        # ponytail: 15 s poll, so switching on from the Tapo app is noticed within ~15 s
        RepeatedTimer(15, self._poll, daemon=True).start()

    def _poll(self):
        if self._settings.get(["host"]) and self._settings.get_boolean(["auto_connect"]):
            try:
                self._run(self._control("status"))
            except Exception as e:
                self._logger.debug("Poll failed: %s", e)

    def _on_state(self, is_on):
        was, self._last_on = self._last_on, is_on
        if was is False and is_on and self._settings.get_boolean(["auto_connect"]):
            delay = max(0.0, float(self._settings.get(["auto_connect_delay"]) or 0))
            self._logger.info("Plug turned on, connecting printer in %s s", delay)
            t = threading.Timer(delay, self._auto_connect)
            t.daemon = True
            t.start()

    def _auto_connect(self):
        if not self._printer.is_closed_or_error():
            return
        s = octoprint.settings.settings()
        port, baud = s.get(["serial", "port"]), s.getInt(["serial", "baudrate"])
        self._logger.info("Auto-connect: port=%s baudrate=%s", port or "AUTO", baud or "AUTO")
        self._printer.connect(port=port, baudrate=baud)

    # ---- optional PSU Control backend: OctoDash, OctoApp etc. switch power through PSU Control ----

    def on_startup(self, host, port):
        helpers = self._plugin_manager.get_helpers("psucontrol", "register_plugin")
        if helpers:
            helpers["register_plugin"](self)
            self._logger.info("Registered with PSU Control")

    def turn_psu_on(self):
        self._run(self._control("on"))

    def turn_psu_off(self):
        self._run(self._control("off"))

    def get_psu_state(self):
        try:
            return bool(self._run(self._control("status")))
        except Exception as e:
            self._logger.error("Tapo state read failed: %s", e)
            return False

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
                if action == "off" and self._printer.is_operational() and not self._printer.is_printing():
                    self._printer.disconnect()  # clean disconnect instead of a serial error
                await (self._dev.turn_on() if action == "on" else self._dev.turn_off())
                await self._dev.update()
            self._on_state(self._dev.is_on)
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
            dev = await connect(ip, creds)
            return dict(host=ip, alias=dev.alias, model=dev.model, note="")
        except Exception as e:
            if is_auth_error(e):
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
