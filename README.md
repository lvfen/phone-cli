# phone-cli

CLI tool for AI-powered phone automation via ADB (Android), HDC (HarmonyOS), and iOS multi-runtime backends:

- `device`: iPhone / iPad real device via `tidevice + WDA`
- `simulator`: iOS Simulator via `simctl + host automation`
- `app-on-mac`: iOS App on Mac via macOS host automation

## Installation

```bash
# Basic installation (Android + HarmonyOS + dev tools)
pip install -e ".[dev]"

# iOS support (real device + Simulator + App on Mac)
pip install -e ".[ios]"

# Full installation
pip install -e ".[ios,dev]"
```

### iOS Prerequisites

iOS automation requires macOS.

General requirements:

1. Xcode and command-line tools installed
2. `pip install -e ".[ios]"` to install `tidevice`, `facebook-wda`, and PyObjC host automation dependencies

Runtime-specific requirements:

1. `device`
   - A connected iPhone / iPad trusted by the Mac
   - WebDriverAgent built and deployed to the device
2. `simulator`
   - At least one Booted iOS Simulator
3. `app-on-mac`
   - Apple Silicon Mac
   - Accessibility and Screen Recording permissions granted to the shell / Python host

## Usage

```bash
# Check version
phone-cli version

# Android (default)
phone-cli start
phone-cli devices

# HarmonyOS
phone-cli start --device-type hdc

# iOS: inspect available runtimes first
phone-cli detect-runtimes --device-type ios

# iOS: auto-select when only one candidate exists
phone-cli start --device-type ios

# iOS: explicit runtime selection
phone-cli start --device-type ios --runtime device --device-id <udid>
phone-cli start --device-type ios --runtime simulator --device-id <sim_udid>
phone-cli start --device-type ios --runtime app-on-mac

# Launch apps
phone-cli launch 微信
phone-cli launch --bundle-id com.apple.Preferences
phone-cli launch --app-path "/path/to/Demo.app"

# Common commands
phone-cli device-info
phone-cli screenshot
phone-cli tap 500 500
phone-cli swipe 500 800 500 200
phone-cli type "Hello"
phone-cli get-current-app
phone-cli ui-tree
phone-cli app-state --bundle-id com.apple.Preferences
phone-cli wait-for-app --bundle-id com.apple.Preferences --timeout 10
phone-cli stop
```

### Parallel Android + iOS Instances

`phone-cli` now supports independent daemon instances per platform family, so Android / HarmonyOS / iOS can run side by side.

If only one instance is running, bare commands like `phone-cli status` still work.
If multiple instances are running at the same time, use `--instance adb|hdc|ios` to target the right one.

```bash
# Start Android and iOS independently
phone-cli --instance adb start --device-type adb
phone-cli --instance ios start --device-type ios --runtime simulator --device-id <sim_udid>

# Target each instance explicitly
phone-cli --instance adb status
phone-cli --instance ios status
phone-cli --instance adb screenshot
phone-cli --instance ios screenshot

# Stop one instance or all of them
phone-cli --instance ios stop
phone-cli stop --all
```

### iOS Runtime Selection Rules

`phone-cli start --device-type ios` behaves as follows:

1. `0` candidates: returns `NO_AVAILABLE_IOS_RUNTIME`
2. `1` candidate: auto-selects it and starts directly
3. `2+` candidates: returns `RUNTIME_SELECTION_REQUIRED`

If you already know which runtime you want, pass `--runtime` explicitly to skip auto-selection.

### Example iOS Workflows

#### Real device

```bash
phone-cli detect-runtimes --device-type ios
phone-cli start --device-type ios --runtime device --device-id <udid>
phone-cli launch --bundle-id com.tencent.xin
phone-cli wait-for-app --bundle-id com.tencent.xin --timeout 10
```

#### Simulator

```bash
phone-cli detect-runtimes --device-type ios
phone-cli start --device-type ios --runtime simulator --device-id <sim_udid>
phone-cli launch --bundle-id com.apple.Preferences
phone-cli screenshot
```

#### App on Mac

```bash
phone-cli detect-runtimes --device-type ios
phone-cli start --device-type ios --runtime app-on-mac
phone-cli launch --bundle-id com.example.demo
phone-cli ui-tree
```

## Supported Platforms

| Platform | Transport / Driver | Interaction Model | Notes |
|---|---|---|---|
| Android | `adb` | shell input + screenshot | Default; supports USB, WiFi, TCP/IP |
| HarmonyOS | `hdc` | `uitest` + screenshot | Huawei devices |
| iOS device | `tidevice + WDA` | WDA HTTP API | Full legacy real-device path |
| iOS simulator | `simctl + host events` | screenshot + mapped host interaction | `ui-tree` unavailable in MVP |
| iOS app-on-mac | `open + Quartz + AX` | window screenshot + host interaction | AX quality depends on app implementation |

## Architecture

```text
phone_cli/
├── cli/                  # CLI entry point, commands, daemon, JSON output
├── adb/                  # Android implementation
├── hdc/                  # HarmonyOS implementation
├── ios/
│   ├── __init__.py       # iOS facade
│   ├── runtime/
│   │   ├── base.py       # Shared backend protocol and capabilities
│   │   ├── discovery.py  # device / simulator / app_on_mac candidate discovery
│   │   ├── router.py     # Runtime -> backend dispatch
│   │   ├── device_backend.py
│   │   ├── simulator_backend.py
│   │   └── app_on_mac_backend.py
│   └── host/
│       ├── permissions.py
│       ├── windows.py
│       ├── events.py
│       ├── screenshots.py
│       └── ax_tree.py
└── config/
    ├── apps.py
    ├── apps_harmonyos.py
    ├── apps_ios.py
    ├── i18n.py
    └── timing.py
```

## Development

```bash
# Run unit tests (no device needed)
pytest tests/cli/ -v --ignore=tests/cli/test_e2e.py

# Run E2E tests (requires connected target)
pytest tests/cli/test_e2e.py -v
```
