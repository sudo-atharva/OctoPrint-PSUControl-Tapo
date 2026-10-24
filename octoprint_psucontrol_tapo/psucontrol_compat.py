# coding=utf-8
"""Answers PSU Control's API (/api/plugin/psucontrol) so OctoDash, OctoApp and other apps
with PSU Control support can switch the Tapo plug. Don't install the real PSU Control alongside."""
import flask
import octoprint.plugin

ACTIONS = dict(turnPSUOn="on", turnPSUOff="off", togglePSU="toggle", getPSUState="status")


class PSUControlCompat(octoprint.plugin.SettingsPlugin,  # SettingsPlugin: apps detect psucontrol via /api/settings
                       octoprint.plugin.SimpleApiPlugin):

    def get_settings_defaults(self):
        return dict(provider="psucontrol_tapo")

    def get_api_commands(self):
        return {k: [] for k in ACTIONS}

    def on_api_get(self, request):
        return self.on_api_command("getPSUState", {})

    def on_api_command(self, command, data):
        tapo = self._plugin_manager.get_plugin_info("psucontrol_tapo", require_enabled=True)
        if not tapo:
            return flask.make_response("Tapo Plug plugin not enabled", 503)
        return flask.jsonify(isPSUOn=tapo.implementation.switch(ACTIONS[command]))


__plugin_name__ = "Tapo Plug - PSU Control API"
__plugin_pythoncompat__ = ">=3.11,<4"
__plugin_implementation__ = PSUControlCompat()
