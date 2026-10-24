$(function () {
    function TapoPlugViewModel(parameters) {
        var self = this;
        var PLUGIN = "psucontrol_tapo";
        self.settingsViewModel = parameters[0];
        self.loginState = parameters[1];
        self.settings = undefined;
        self.devices = ko.observableArray([]);
        self.scanning = ko.observable(false);
        self.message = ko.observable("");
        self.isOn = ko.observable(null);
        self.error = ko.observable(null);
        self.navTitle = ko.pureComputed(function () {
            if (self.error()) return "Tapo: " + self.error();
            return self.isOn() === null ? "Tapo: unknown" : "Tapo plug is " + (self.isOn() ? "ON" : "OFF");
        });

        self.onBeforeBinding = function () {
            self.settings = self.settingsViewModel.settings.plugins.psucontrol_tapo;
        };

        function apply(r) {
            self.isOn(r.on);
            self.error(r.error);
        }

        self.refresh = function () {
            if (!self.loginState.isUser()) return;
            OctoPrint.simpleApiGet(PLUGIN).done(apply);
        };

        self.send = function (cmd) {
            self.error(null);
            OctoPrint.simpleApiCommand(PLUGIN, cmd).done(apply);
        };
        self.turnOn = function () { self.send("on"); };
        self.turnOff = function () { self.send("off"); };

        self.toggle = function () {
            if (self.isOn() && !confirm("Turn the printer plug OFF?")) return;
            self.send(self.isOn() ? "off" : "on");
        };

        self.onStartupComplete = function () {
            self.refresh();
            setInterval(self.refresh, 15000);
        };
        self.onUserLoggedIn = self.refresh;
        self.onSettingsHidden = self.refresh;

        self.discover = function () {
            self.scanning(true);
            self.devices([]);
            self.message("Scanning network (about 10 s)...");
            OctoPrint.simpleApiCommand(PLUGIN, "discover", {
                username: self.settings.username(),
                password: self.settings.password()
            }).done(function (r) {
                self.devices(r.devices);
                self.message(r.devices.length ? "Click a plug to use it, then Save:" : "No Tapo plug found. Check octoprint.log.");
            }).fail(function (x) {
                self.message("Scan failed: " + (x.responseText || x.statusText));
            }).always(function () {
                self.scanning(false);
            });
        };

        self.pick = function (dev) {
            self.settings.host(dev.host);
            self.devices([]);
            self.message("Selected " + dev.host + ". Click Save.");
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: TapoPlugViewModel,
        dependencies: ["settingsViewModel", "loginStateViewModel"],
        elements: ["#settings_plugin_psucontrol_tapo", "#navbar_plugin_psucontrol_tapo"]
    });
});
