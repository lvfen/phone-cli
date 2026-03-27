---
name: phone-automation
description: AI-powered phone automation via `phone-cli` across Android (ADB), HarmonyOS (HDC), and iOS real devices, iOS Simulator, and iOS App on Mac. Use when the user asks to operate a phone, test an app, take screenshots, click, swipe, type, open apps, or automate mobile flows on real devices, emulators, simulators, or `app_on_mac` targets.
---

# Phone Automation Skill

Automate phone operations via `phone-cli` daemon.

Supported targets:

- Android via `adb`
- HarmonyOS via `hdc`
- iOS real device via `tidevice + WDA`
- iOS Simulator via `simctl + host automation`
- iOS App on Mac via `open + Quartz + AX + host events`

## Architecture

phone-cli 有两层 daemon 架构：

1. **Per-device-type daemon**（现有）：通过 `phone-cli start --device-type adb|hdc|ios` 启动，每个平台一个实例，适合单 AI 会话操控单台设备。
2. **Central daemon**（新增）：通过 `phone-cli daemon start` 启动，统一管理所有设备的连接、端口和会话生命周期，支持多 AI 会话并行操控不同设备，动态端口分配，空闲超时自动释放。

**单会话场景**（大多数情况）：使用现有的 per-device-type daemon 即可，流程不变。
**多会话并行场景**：使用 central daemon，AI 通过 `PhoneClient` 或 `phone-cli daemon` 命令申请/释放设备。

## Trigger Conditions

Use this skill when the user mentions:
- Phone/mobile operations (截图, 点击, 滑动, 打开App)
- App testing on real devices, emulators, simulators, or `app_on_mac`
- ADB/HDC/iOS commands for device interaction
- Mobile UI automation tasks

## Step 0: Infer Platform And Runtime

1. Infer the target platform from the user's wording.
2. Treat explicit user wording as binding:
   - `Android` / `ADB` / `emulator` => Android
   - `HarmonyOS` / `鸿蒙` / `HDC` => HarmonyOS
   - `iPhone` / `iOS` / `bundle id` / `.app` / `Simulator` / `simctl` / `app_on_mac` / `App on Mac` => iOS
3. If the user explicitly asks for `device`, `simulator`, or `app_on_mac`, do not override it.
4. If the request is generic and no platform is implied:
   - Reuse the currently running connected daemon if it already matches the task
   - Otherwise default to Android (`adb`)

### ADB Port Conflict Recovery

If `adb devices` fails with "Address already in use" or "failed to start daemon":
1. Run `lsof -i :5037` to find the process occupying the ADB port
2. Kill the stale process: `kill <PID>`
3. Wait 2 seconds, then retry `adb devices`

Note: When using the central daemon, ADB server ports are dynamically allocated from range 5037-5099. If port 5037 is occupied, the daemon automatically uses the next available port. Manual recovery is only needed for the per-device-type daemon mode.

## Step 1: Startup And Target Selection

1. Run `phone-cli status`.
2. Parse the JSON output:
   - If `"status": "running"` and `"device_status": "connected"` and the daemon already matches the requested platform/runtime, reuse it
   - If `"device_status": "disconnected"`, stop and restart
   - If the daemon is running but on the wrong platform/runtime, stop and restart
   - If `"status": "stopped"` or the command fails, start the right platform flow from scratch

### Android Startup

1. Run `phone-cli stop` first to clean up stale state.
2. Run `phone-cli start --device-type adb`.
3. Wait 2 seconds, then run `phone-cli status`.
4. If it still fails:
   - Check if `phone-cli` is installed
   - Check if `adb` is available
   - Check if a device or emulator is connected

### HarmonyOS Startup

1. Run `phone-cli stop` first to clean up stale state.
2. Run `phone-cli start --device-type hdc`.
3. Wait 2 seconds, then run `phone-cli status`.
4. If it still fails:
   - Check if `phone-cli` is installed
   - Check if `hdc` is available
   - Check if a HarmonyOS device is connected

### iOS Startup

1. If the user explicitly specified `device`, `simulator`, or `app_on_mac`, keep that runtime preference.
2. Run:

```bash
phone-cli detect-runtimes --device-type ios
```

3. Parse the JSON output:
   - If there are no candidates:
     - Report the actual reasons returned by `detect-runtimes`
     - Suggest the relevant fix:
       - Real device: connect an iPhone and ensure `tidevice` can see it
       - Simulator: boot an iOS Simulator first
       - `app_on_mac`: install host dependencies, grant Accessibility / Screen Recording permissions, then restart the host app and rerun `detect-runtimes`
   - If there is exactly one candidate:
     - Auto-select it without asking the user
   - If there are multiple candidates:
     - Ask the user which runtime/target to use
     - Never auto-pick a candidate when multiple are available

4. If the user explicitly requested an iOS runtime:
   - Filter candidates to that runtime
   - If none match, tell the user that runtime is currently unavailable
   - If one matches, use it
   - If multiple match, ask which target ID to use

5. Start the daemon with an explicit runtime:

```bash
# Real device
phone-cli start --device-type ios --runtime device --device-id <udid>

# Simulator
phone-cli start --device-type ios --runtime simulator --device-id <sim_udid>

# App on Mac
phone-cli start --device-type ios --runtime app-on-mac
```

6. After startup, run:

```bash
phone-cli device-info
```

7. Verify:
   - `device_type == ios`
   - `ios_runtime` matches the selected runtime
   - `device_status == connected`
   - `target_id` is present for `device` / `simulator`, or `local-mac` for `app_on_mac`

## Step 1.5: Target Check

### Android / HarmonyOS

1. Run `phone-cli devices`
2. Parse the device list
3. If no devices:
   - For Android, first check `adb devices`
   - For HarmonyOS, check `hdc list targets`
4. If multiple targets exist, ask the user which one to use
5. After selecting a target, always run `phone-cli set-device <ID>`

### iOS

1. If the daemon was just started from `detect-runtimes`, the selected runtime/target is already bound
2. If the user wants to switch to another real device or Simulator target later, run `phone-cli set-device <ID>`
3. For `app_on_mac`, treat `local-mac` as the bound target unless future multi-target support is added

### Emulator Auto-Start

If no device is connected and the user wants to use an emulator:
1. Run `emulator -list-avds` to list available AVDs
2. If AVDs exist, ask the user which one to use
3. Start the emulator — **MUST follow these rules**:
   - **Always run from SDK directory**: `cd $ANDROID_HOME/emulator && ./emulator -avd <name> ...` (running from other directories causes path resolution failures)
   - **NEVER use `-no-window` flag** — headless mode causes `adb screencap` to return all-black images
   - **NEVER use `-no-snapshot-load` unless troubleshooting** — cold boot takes 60+ seconds vs ~10s for snapshot
   - Recommended flags: `./emulator -avd <name> -no-audio -no-boot-anim`
4. Wait for boot: `adb wait-for-device && adb shell 'while [[ -z $(getprop sys.boot_completed) ]]; do sleep 2; done'`
5. Verify boot: `adb shell getprop sys.boot_completed` should return `1`

### Emulator Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `screencap` returns all-black PNG | Emulator started with `-no-window` (headless mode) | Kill emulator, restart WITHOUT `-no-window` |
| Screenshots black after snapshot restore | Renderer mismatch between snapshot and current session | Kill emulator, restart with `-no-snapshot-load` for a cold boot |
| `qemu-system not found` error | Emulator started from wrong working directory | Always `cd $ANDROID_HOME/emulator` before running `./emulator` |
| Emulator process exists but no ADB device | ADB port conflict or daemon crash | Kill old ADB (`lsof -i :5037`), then `adb kill-server && adb start-server` |
| `kill <PID>` doesn't stop emulator | Emulator ignores SIGTERM gracefully | Use `kill -9 <PID>` on the `qemu-system-*` process |

## Step 2: Device Sanity Check (before any real work)

**After device is connected, verify device responsiveness before proceeding:**

1. Run `phone-cli ui-tree` to check if the UI node tree is available
2. If UI tree returns valid nodes → device is responsive, proceed to Step 3
3. If `UI_TREE_UNAVAILABLE`, fall back to screenshot check:
   a. Run `phone-cli check-screen` to check screen health
   b. If `screen_state` is `all_black` or `all_white`:
      - First press Home: `phone-cli home`, wait 2 seconds, re-check
      - For Android emulators, try: kill emulator, restart with `-no-snapshot-load`
      - For iOS Simulator / `app_on_mac`, treat this as a runtime or host issue first, not an app bug
      - If still abnormal → tell the user the target environment itself is unhealthy
   c. If `screen_state` is `normal` → proceed to Step 3

**This step prevents wasting time debugging issues that are actually device/emulator problems.**

**Important iOS note:**

- On `ios-simulator`, `ui-tree` being unavailable is expected in MVP. Fall back to `check-screen` and screenshots.
- On `app_on_mac`, AX tree may be sparse. If nodes are low quality, prefer screenshot + coordinates.

## Step 3: Task Classification

Classify the user's request:

| Type | Criteria | Examples | Action |
|------|----------|----------|--------|
| Simple | Single operation, no screenshot analysis needed | "截图", "回主页", "查看当前App" | Execute directly via `phone-cli` in main session |
| Medium | 2-5 steps, clear linear flow | "打开掌上穿越火线截个图", "输入文字并点击发送" | Execute sequentially via `phone-cli` in main session |
| Complex | Multi-step, needs dynamic decisions based on screen content | "在App中搜索XXX并筛选评分最高的", "完成签到流程" | Brainstorming → Subagent |

## Step 4 (Complex Tasks): Brainstorming

Invoke the brainstorming workflow to work with the user:

1. Clarify the final goal and success criteria
2. Decompose into ordered steps, each with:
   - `action`: what to do
   - `success_criteria`: how to verify it worked
3. Identify sensitive operations: sending messages, submitting forms, payments
4. Identify login/auth requirements:
   - Android emulators may be limited for apps requiring real-device login
   - iOS Simulator may be limited for flows that depend on real-device entitlements
   - `app_on_mac` may expose sparse accessibility info for some apps
5. User confirms the plan

Output a structured task plan for the subagent.

## Step 5: Execution

### Simple/Medium Tasks

Execute `phone-cli` commands directly in main session via Bash:

```bash
# Example: observe screen state via UI node tree (preferred)
phone-cli ui-tree
# Parse node text/bounds to understand current screen and locate elements

# Example: take a screenshot (only when visual verification needed)
phone-cli screenshot --resize 720
# Read the screenshot file path from JSON output, then use Read tool to view it

# Example: tap at position
phone-cli tap 500 300
```

**Observation priority:** Always use `phone-cli ui-tree` first, then evaluate node quality:
- **Nodes usable** (≥15% have text or meaningful resource_id): use ui-tree for positioning and verification
- **Nodes unusable** (<15% useful, typical of Flutter/game/WebView/Canvas): fall back to screenshots
- **Simulator UI tree unavailable** (`UI_TREE_UNAVAILABLE`): this is expected in MVP, fall back to screenshots
- **App on Mac AX tree sparse**: use screenshots for positioning, treat ui-tree as supplemental only
- **App on Mac post-launch check**: after `launch`, always cross-check `wait-for-app` with one screenshot or `ui-tree` before trusting the target window
- Need visual verification (colors, images, layout): take screenshot regardless

All commands output JSON. Parse `status` field to check success.

### App Launch & Verification

When launching an app:
1. Prefer the platform-native launch path:
   - Android: `phone-cli install <apk> --launch` or `phone-cli launch <app_name>`
   - iOS real device / Simulator / `app_on_mac`: `phone-cli launch --bundle-id <bundle_id>`
   - For local iOS `.app` bundles on Simulator / `app_on_mac`: `phone-cli launch --app-path "/path/to/App.app"`
2. Wait for readiness:
   - Android: `phone-cli wait-for-app <package> --timeout 10`
   - iOS: `phone-cli wait-for-app --bundle-id <bundle_id> --timeout 10`
3. Verify foreground state:
   - Android: `phone-cli app-state --package <package>`
   - iOS: `phone-cli app-state --bundle-id <bundle_id>`
4. If the app is still not foreground:
   - It may have redirected, crashed, or not finished activating
   - Use `phone-cli get-current-app`
   - Then inspect UI tree or screenshot
5. `app_on_mac` special handling:
   - If `wait-for-app` times out but screenshot or `ui-tree` already shows the expected target window, treat it as focus-detection lag and continue
   - If screenshot or `ui-tree` clearly shows another app window after `launch`, rerun the same `phone-cli launch --bundle-id <bundle_id>` once to refresh window binding, then retry observation
   - If `app-state` / `get-current-app` and screenshot / `ui-tree` disagree, trust the bound window evidence first, then refresh once by relaunching the same bundle
6. Take a screenshot only when visual verification is needed

### Diagnosing Black/Blank Screens

When UI tree shows no meaningful elements or screenshot shows a black/empty screen **after confirming the device works (Step 2)**:

1. Check app state:
   - Android: `phone-cli app-state --package <package>`
   - iOS: `phone-cli app-state --bundle-id <bundle_id>`
2. Check the current foreground app:
   ```bash
   phone-cli get-current-app
   ```
3. If Android:
   - Check for crashes: `phone-cli app-log --package <package> --filter crash`
   - Trace lifecycle: `phone-cli app-log --package <package> --filter lifecycle`
4. If iOS:
   - Prefer `phone-cli screenshot --resize 720`
   - For Simulator, remember `ui-tree` unavailability is expected in MVP
   - For `app_on_mac`, sparse AX data is expected for some UIKit / Flutter / custom-rendered views
   - For `app_on_mac`, if the captured window belongs to the wrong app, relaunch the same bundle once to refresh window binding before deeper debugging
   - `app-log` is not yet supported for iOS runtimes
5. Common causes:
   - App requires login or entitlements unavailable on emulator / simulator
   - App briefly launches and exits
   - The page is visually dark but not actually broken
   - The target runtime itself is unhealthy or missing required permissions

### Complex Tasks

Launch a subagent via the Agent tool with:
- `subagent_type`: use default (general-purpose)
- Prompt: load `prompts/subagent.md` template, inject the task steps and rules from `prompts/rules_zh.md`
- The subagent runs the observe→think→act loop autonomously

### Sensitive Operation Handling

The subagent prompt includes a "confirm" tier for operations like sending messages or submitting forms. When the subagent encounters these, it must:

1. Stop execution and return a confirmation request with details of the pending action
2. The main session presents this to the user for approval
3. On approval, re-dispatch the subagent to continue from that step
4. On rejection, skip the step or abort the task

## Step 6: Result Report

After execution:
- Report results to the user (step-by-step status, key screenshots)
- On failure: analyze cause, ask user whether to retry or re-plan

## phone-cli Command Reference

| Command | Usage | Description |
|---------|-------|-------------|
| `phone-cli status` | Status check | Returns daemon state as JSON |
| `phone-cli start` | Start daemon | `--device-type adb\|hdc\|ios`; iOS also supports `--runtime device\|simulator\|app-on-mac` |
| `phone-cli detect-runtimes` | Detect iOS runtime candidates | `--device-type ios` |
| `phone-cli stop` | Stop daemon | |
| `phone-cli devices` | List devices | |
| `phone-cli set-device ID` | Set target device | |
| `phone-cli device-info` | Current device info | |
| `phone-cli screenshot` | Take screenshot | `--resize 720`, `--task-id`, `--step` |
| `phone-cli tap X Y` | Tap | 0-999 relative coordinates |
| `phone-cli double-tap X Y` | Double tap | |
| `phone-cli long-press X Y` | Long press | |
| `phone-cli swipe X1 Y1 X2 Y2` | Swipe | |
| `phone-cli type "text"` | Type text | Auto-clears existing text first |
| `phone-cli back` | Press back | |
| `phone-cli home` | Press home | |
| `phone-cli launch APP` | Launch app by name | Use app name from config |
| `phone-cli launch --bundle-id ID` | Launch app by bundle ID | Preferred for iOS |
| `phone-cli launch --app-path PATH` | Launch app by `.app` path | iOS Simulator / `app_on_mac` local builds |
| `phone-cli get-current-app` | Current app | |
| `phone-cli ui-tree` | UI hierarchy | For precise element location |
| `phone-cli clean-screenshots` | Clean old screenshots | `--all` to remove all |
| `phone-cli log` | View logs | `--tail N`, `--task ID` |
| `phone-cli app-state` | App foreground state | Android: `--package PKG`; iOS: `--bundle-id ID` |
| `phone-cli wait-for-app` | Wait for app ready | Android: positional package; iOS: `--bundle-id ID`; `--timeout`, `--state resumed\|running` |
| `phone-cli check-screen` | Screen health check | `--threshold 0.95` (all-black/white detect) |
| `phone-cli app-log` | App logs via logcat | Android-only |
| `phone-cli install APK` | Install APK | Android-only |
| `phone-cli version` | Show version | |
| `phone-cli daemon start` | Start central daemon | `--foreground` to run in foreground. Manages multi-session device access with dynamic port allocation |
| `phone-cli daemon stop` | Stop central daemon | Terminates all device subprocesses and releases ports |
| `phone-cli daemon status` | Central daemon status | Shows active sessions, devices, ports, and idle times |

## ADB Diagnostic Command Reference

These commands help diagnose issues beyond what phone-cli provides:

| Command | Purpose |
|---------|---------|
| `adb shell dumpsys activity top \| grep "ACTIVITY\|mResumed"` | Check which activity is in foreground |
| `adb logcat -d --pid=$(adb shell pidof <pkg>) \| tail -30` | View app's recent logs |
| `adb logcat -d \| grep -iE "crash\|exception\|fatal"` | Find crashes |
| `adb shell am force-stop <pkg>` | Force stop an app |
| `adb shell am start -n <pkg>/<activity>` | Start a specific activity |
| `adb shell pm list packages \| grep <keyword>` | Find installed packages |
| `aapt2 dump badging <apk>` | Get APK package name and launcher activity |
| `adb shell getprop sys.boot_completed` | Check if device has finished booting |
| `lsof -i :5037` | Find process using ADB port |
