# phone-cli

CLI tool for AI-powered phone automation via ADB (Android), HDC (HarmonyOS) and iOS (tidevice + WDA).

## Installation

```bash
# Basic installation (Android & HarmonyOS)
pip install -e ".[dev]"

# With iOS support
pip install -e ".[ios]"

# Full installation (iOS + dev tools)
pip install -e ".[ios,dev]"
```

### iOS Prerequisites

iOS automation requires a Mac with the following:

1. **Xcode** and command-line tools installed
2. **WebDriverAgent** built and deployed to the target device — see [appium/WebDriverAgent](https://github.com/appium/WebDriverAgent)
3. Python dependencies (`tidevice` and `facebook-wda`) are installed automatically via `pip install phone-cli[ios]`

## Usage

```bash
# Check version
phone-cli version

# ── Android (default) ────────────────────────────
phone-cli start                          # Start daemon (ADB)
phone-cli devices                        # List connected Android devices

# ── HarmonyOS ────────────────────────────────────
phone-cli start --device-type hdc        # Start daemon (HDC)

# ── iOS ──────────────────────────────────────────
phone-cli start --device-type ios        # Start daemon (iOS via tidevice + WDA)
phone-cli devices                        # List connected iOS devices

# ── Common commands (all platforms) ──────────────
phone-cli screenshot                     # Capture screenshot
phone-cli tap 500 500                    # Tap at coordinates (0-999 relative)
phone-cli swipe 500 800 500 200          # Swipe gesture
phone-cli home                           # Press home button
phone-cli back                           # Back navigation (iOS: left-edge swipe)
phone-cli launch 微信                     # Launch app by name
phone-cli launch Settings                # Launch app (English name)
phone-cli get-current-app                # Get foreground app
phone-cli ui-tree                        # Dump UI accessibility tree
phone-cli type "Hello"                   # Type text into focused field
phone-cli stop                           # Stop daemon
```

## Supported Platforms

| Platform   | Connection | Device Control       | Notes                                    |
|------------|------------|----------------------|------------------------------------------|
| Android    | ADB        | `input` shell cmds   | Default; supports USB, WiFi, TCP/IP      |
| HarmonyOS  | HDC        | `uitest` shell cmds  | Huawei devices                           |
| iOS        | tidevice   | WDA HTTP API         | Requires WebDriverAgent on device        |

## Architecture

```
phone_cli/
├── cli/                  # CLI entry point & daemon
│   ├── main.py           # Click CLI definition
│   ├── commands.py       # Command dispatch & handlers
│   ├── daemon.py         # Background daemon lifecycle
│   └── output.py         # JSON response formatting
├── adb/                  # Android implementation
│   ├── connection.py     # ADB device discovery & connection
│   ├── device.py         # Tap, swipe, home, back, launch …
│   ├── input.py          # ADB Keyboard text input
│   └── screenshot.py     # screencap + pull
├── hdc/                  # HarmonyOS implementation
│   ├── connection.py
│   ├── device.py
│   ├── input.py
│   └── screenshot.py
├── ios/                  # iOS implementation
│   ├── connection.py     # tidevice wdaproxy + wda.Client cache
│   ├── device.py         # WDA tap, swipe, home, launch …
│   ├── input.py          # WDA send_keys / clear_text
│   └── screenshot.py     # WDA screenshot → PIL → base64
└── config/
    ├── apps.py           # Android package name mapping
    ├── apps_harmonyos.py # HarmonyOS bundle name mapping
    ├── apps_ios.py       # iOS bundle ID mapping
    ├── i18n.py           # Internationalization
    └── timing.py         # Timing / delay configuration
```

## Development

```bash
# Run unit tests (no device needed)
pytest tests/cli/ -v --ignore=tests/cli/test_e2e.py

# Run E2E tests (requires connected device)
pytest tests/cli/test_e2e.py -v
```
