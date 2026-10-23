$(function () {
    function PSUControlTapoViewModel(parameters) {
        var self = this;
        self.settingsViewModel = parameters[0];
        self.settings = undefined;
        self.devices = ko.observableArray([]);
        self.scanning = ko.observable(false);
        self.message = ko.observable("");

        self.onBeforeBinding = function () {
            self.settings = self.settingsViewModel.settings.plugins.psucontrol_tapo;
        };

        self.discover = function () {
            self.scanning(true);
            self.devices([]);
            self.message("Scanning network...");
            OctoPrint.simpleApiCommand("psucontrol_tapo", "discover", {
                username: self.settings.username(),
                password: self.settings.password()
            }).done(function (r) {
                self.devices(r.devices);
                self.message(r.devices.length ? "Click a plug to use it:" : "No Tapo plug found.");
            }).fail(function () {
                self.message("Scan failed, see octoprint.log.");
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
        construct: PSUControlTapoViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_psucontrol_tapo"]
    });
});
