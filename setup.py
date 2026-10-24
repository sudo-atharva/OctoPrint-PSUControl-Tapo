import setuptools

setuptools.setup(
    name="OctoPrint-PSUControl-Tapo",
    version="1.0.0",
    description="Switch a TP-Link Tapo smart plug (P110 etc.) from OctoPrint",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="sudo-atharva",
    url="https://github.com/sudo-atharva/OctoPrint-PSUControl-Tapo",
    license="AGPLv3",
    packages=["octoprint_psucontrol_tapo"],
    package_data={"octoprint_psucontrol_tapo": ["templates/*", "static/js/*"]},
    python_requires=">=3.11",
    # TPAP firmware support is only in this unmerged python-kasa PR; switch to "python-kasa>=X" once released
    install_requires=["python-kasa @ git+https://github.com/python-kasa/python-kasa.git@refs/pull/1592/head"],
    entry_points={"octoprint.plugin": ["psucontrol_tapo = octoprint_psucontrol_tapo",
                                       "psucontrol = octoprint_psucontrol_tapo.psucontrol_compat"]},
)
