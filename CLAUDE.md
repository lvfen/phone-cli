# phone-cli

CLI tool for AI-powered phone automation via ADB (Android), HDC (HarmonyOS), and iOS (tidevice + WDA).

## Skills

When the user asks to operate a phone, test an app, take phone screenshots, or automate mobile tasks, load the skill file at `.claude/skills/phone-automation/SKILL.md` via the Read tool, then follow its instructions.

Trigger keywords: 手机操作, 截图, 点击, 滑动, 打开App, ADB, HDC, iOS automation, phone-cli

## Project Structure

```
phone_cli/
├── cli/          # CLI entry point, commands, daemon
├── adb/          # Android (ADB) implementation
├── hdc/          # HarmonyOS (HDC) implementation
├── ios/          # iOS (tidevice + WDA) implementation
└── config/       # App mappings, i18n, timing
```

## Dev Commands

**Important Rule**: 
`phone-cli` operates on a client-daemon architecture. **Whenever you modify the Python source code** of `phone-cli` (e.g. `phone_cli/adb/device.py`, etc.), the daemon holding the older code in memory will NOT automatically reload. You **MUST restart the daemon** (`phone-cli stop && phone-cli start --device-type <platform>`) before testing your changes!

```bash
# Restart daemon to apply code changes
phone-cli stop && phone-cli start --device-type adb # or hdc / ios
```

```bash
# Run unit tests
pytest tests/cli/ -v --ignore=tests/cli/test_e2e.py

# Run E2E tests (requires connected device)
pytest tests/cli/test_e2e.py -v

# Install with iOS support
pip install -e ".[ios]"
```
