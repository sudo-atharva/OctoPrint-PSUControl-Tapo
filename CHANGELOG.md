# Changelog

## 1.0.0
- First stable release
- OctoPrint Software Update support: new GitHub releases show up in OctoPrint
- Plugin metadata (description, author, license) shown in Plugin Manager
- README with screenshots and troubleshooting, AGPLv3 license

## 0.2.0
- Auto-off N minutes after a print finishes
- Auto-connect printer when the plug turns on; clean disconnect before off
- OctoDash / OctoApp support (answers PSU Control's API, no extra plugin)
- Tries TPAP, KLAP and AES directly over HTTP; UDP discovery only as fallback
- Stops on wrong password to avoid the plug's login lockout

## 0.1.0
- First release: navbar toggle, settings page with auto-detect, TPAP firmware support
