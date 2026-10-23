import setuptools

setuptools.setup(
    name="OctoPrint-PSUControl-Tapo",
    version="0.1.0",
    description="PSU Control sub-plugin for TP-Link Tapo smart plugs (P110 etc.)",
    packages=["octoprint_psucontrol_tapo"],
    package_data={"octoprint_psucontrol_tapo": ["templates/*", "static/js/*"]},
    python_requires=">=3.11",
    # TPAP firmware support is only in this unmerged python-kasa PR; switch to "python-kasa>=X" once released
    install_requires=["python-kasa @ git+https://github.com/python-kasa/python-kasa.git@refs/pull/1592/head"],
    entry_points={"octoprint.plugin": ["psucontrol_tapo = octoprint_psucontrol_tapo"]},
)
