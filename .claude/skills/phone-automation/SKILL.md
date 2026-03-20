---
name: phone-automation
description: AI-powered phone automation via ADB/HDC/iOS. Use when the user asks to operate a phone, test an app, take phone screenshots, or automate mobile tasks.
---

# Phone Automation Skill

Automate phone operations via `phone-cli` daemon. Supports Android (ADB), HarmonyOS (HDC), and iOS (XCTest).

## Trigger Conditions

Use this skill when the user mentions:
- Phone/mobile operations (截图, 点击, 滑动, 打开App)
- App testing on real devices or emulators
- ADB/HDC commands for device interaction
- Mobile UI automation tasks

## Step 0: CLI Startup Check

1. Run `phone-cli status` via Bash
2. Parse the JSON output:
   - If `"status": "running"` AND `"device_status": "connected"`: proceed to Step 1
   - If `"device_status": "disconnected"`: stop and restart daemon (see below)
   - If `"status": "stopped"` or command fails:
     a. Run `phone-cli stop` first (clean up stale state)
     b. Run `phone-cli start --device-type adb`
     c. Wait 2 seconds
     d. Run `phone-cli status` again
     e. If still not running, tell the user:
        - Check if phone-cli is installed: `pip install -e ~/development/code/phone-cli`
        - Check if ADB is available: `adb devices`
        - Check if a device is connected

### ADB Port Conflict Recovery

If `adb devices` fails with "Address already in use" or "failed to start daemon":
1. Run `lsof -i :5037` to find the process occupying the ADB port
2. Kill the stale process: `kill <PID>`
3. Wait 2 seconds, then retry `adb devices`

## Step 1: Device Check

1. Run `phone-cli devices`
2. Parse JSON output for device list
3. If no devices:
   - First check `adb devices` directly to rule out daemon issues
   - If ADB sees no devices either: guide user to connect a device
4. If multiple devices: ask user which one to use
5. **IMPORTANT**: Always run `phone-cli set-device <ID>` after selecting a device

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

## Step 1.5: Device Sanity Check (before any real work)

**After device is connected, verify device responsiveness before proceeding:**

1. Run `phone-cli ui-tree` to check if UI node tree is available
2. If UI tree returns valid nodes → device is responsive, proceed to Step 2
3. If `UI_TREE_UNAVAILABLE`, fall back to screenshot check:
   a. Run `phone-cli check-screen` to check screen health
   b. If `screen_state` is `all_black` or `all_white`:
      - First press Home: `phone-cli home`, wait 2 seconds, re-check
      - If still abnormal → emulator rendering issue, not app problem
      - Try: kill emulator, restart with `-no-snapshot-load` (cold boot)
      - If still abnormal → tell user: recommend using a real device
   c. If `screen_state` is `normal` → proceed to Step 2

**This step prevents wasting time debugging issues that are actually device/emulator problems.**

## Step 2: Task Classification

Classify the user's request:

| Type | Criteria | Examples | Action |
|------|----------|----------|--------|
| Simple | Single operation, no screenshot analysis needed | "截图", "回主页", "查看当前App" | Execute directly via `phone-cli` in main session |
| Medium | 2-5 steps, clear linear flow | "打开掌上穿越火线截个图", "输入文字并点击发送" | Execute sequentially via `phone-cli` in main session |
| Complex | Multi-step, needs dynamic decisions based on screen content | "在App中搜索XXX并筛选评分最高的", "完成签到流程" | Brainstorming → Subagent |

## Step 3 (Complex Tasks): Brainstorming

Invoke `superpowers:brainstorming` to work with the user:

1. Clarify the final goal and success criteria
2. Decompose into ordered steps, each with:
   - `action`: what to do
   - `success_criteria`: how to verify it worked
3. Identify sensitive operations (sending messages, submitting forms, payments)
4. **Identify login/auth requirements** — if the app requires login (QQ, WeChat, etc.), warn the user that emulator testing may be limited
5. User confirms the plan

Output a structured task plan for the subagent.

## Step 4: Execution

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
- **Nodes unusable** (<15% useful, typical of Flutter/game/WebView/Canvas): fall back to screenshots for all operations on this page
- UI tree unavailable (`UI_TREE_UNAVAILABLE`): fall back to screenshots
- Need visual verification (colors, images, layout): take screenshot regardless

All commands output JSON. Parse `status` field to check success.

### App Launch & Verification

When launching an app:
1. Find the correct package name and launcher activity:
   - If you have the APK: `phone-cli install <apk> --launch` (extracts package info and launches automatically)
   - If already installed: `adb shell cmd package resolve-activity --brief <package>`
2. Launch: `adb shell am start -n <package>/<activity>` or use `phone-cli launch <app_name>`
3. Wait for app to be ready: `phone-cli wait-for-app <package> --timeout 10`
4. **Verify app is in foreground**: `phone-cli app-state --package <package>`
   - Check `resumed=true` in the output
5. If `resumed=false` or `stopped=true`:
   - The app may have redirected to login or another screen
   - Check logs: `phone-cli app-log --package <package> --filter crash`
6. Take screenshot only if visual verification is needed

### Diagnosing Black/Blank Screens

When UI tree shows no meaningful elements or screenshot shows a black/empty screen **after confirming the device works (Step 1.5)**:

1. **Check app state**:
   ```bash
   phone-cli app-state --package <package>
   ```
2. **Check for crashes**:
   ```bash
   phone-cli app-log --package <package> --filter crash
   ```
3. **Trace activity navigation** (understand where the app went):
   ```bash
   phone-cli app-log --package <package> --filter lifecycle
   ```
4. **Common causes**:
   - App requires login (QQ/WeChat SDK) → Activity opens but stops when login SDK fails silently
   - App calls `finish()` quickly → splash screen disappears, login screen is not-exported
   - App theme is dark/black background → screen looks blank but UI elements exist (try `phone-cli ui-tree` or `adb shell uiautomator dump`)

### Complex Tasks

Launch a Haiku subagent via the Agent tool with:
- `subagent_type`: use default (general-purpose)
- Prompt: load `prompts/subagent.md` template, inject the task steps and rules from `prompts/rules_zh.md`
- The subagent runs the observe→think→act loop autonomously

### Model Upgrade Mechanism

When dispatching a Haiku subagent for complex tasks, the skill tracks step failures:

1. **Default**: Use Haiku model for subagent (`model: haiku`)
2. **Upgrade trigger**: If a step fails 3 consecutive times (same screenshot after operation), re-dispatch a NEW subagent for that step with Sonnet model
3. **Fallback**: After Sonnet succeeds, subsequent steps resume with Haiku
4. **Hard fail**: If Sonnet also fails the step, stop execution and report to user

The main session (skill) tracks this — the subagent itself just reports success/failure per step.

### Sensitive Operation Handling

The subagent prompt includes a "confirm" tier for operations like sending messages or submitting forms. When the subagent encounters these, it must:

1. Stop execution and return a confirmation request with details of the pending action
2. The main session presents this to the user for approval
3. On approval, re-dispatch the subagent to continue from that step
4. On rejection, skip the step or abort the task

## Step 5: Result Report

After execution:
- Report results to the user (step-by-step status, key screenshots)
- On failure: analyze cause, ask user whether to retry or re-plan

## phone-cli Command Reference

| Command | Usage | Description |
|---------|-------|-------------|
| `phone-cli status` | Status check | Returns daemon state as JSON |
| `phone-cli start` | Start daemon | `--device-type adb\|hdc\|ios` |
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
| `phone-cli launch APP` | Launch app | Use app name from config |
| `phone-cli get-current-app` | Current app | |
| `phone-cli ui-tree` | UI hierarchy | For precise element location |
| `phone-cli clean-screenshots` | Clean old screenshots | `--all` to remove all |
| `phone-cli log` | View logs | `--tail N`, `--task ID` |
| `phone-cli app-state` | App foreground state | `--package PKG` (no screenshot needed) |
| `phone-cli wait-for-app PKG` | Wait for app ready | `--timeout 30`, `--state resumed\|running` |
| `phone-cli check-screen` | Screen health check | `--threshold 0.95` (all-black/white detect) |
| `phone-cli app-log` | App logs via logcat | `--package PKG`, `--filter crash\|lifecycle\|all`, `--lines N` |
| `phone-cli install APK` | Install APK | `--launch` to auto-start after install |
| `phone-cli version` | Show version | |

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
