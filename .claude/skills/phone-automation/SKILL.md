---
name: phone-automation
description: AI-powered phone automation via `phone-cli` across Android (ADB), HarmonyOS (HDC), and iOS real devices, iOS Simulator, and iOS App on Mac. Use when the user asks to operate a phone, test an app, take screenshots, click, swipe, type, open apps, or automate mobile flows on real devices, emulators, simulators, or `app_on_mac` targets.
---

# Phone Automation Skill

Automate phone operations via `phone-cli` daemon.

Supported targets: Android (adb), HarmonyOS (hdc), iOS real device (tidevice + WDA), iOS Simulator (simctl), App on Mac (AX + host events).

## Architecture

phone-cli 有两层 daemon 架构：

1. **Per-device-type daemon**：`phone-cli start --device-type adb|hdc|ios`，每个平台一个实例，适合单 AI 会话操控单台设备。
2. **Central daemon**：`phone-cli daemon start`，统一管理多设备多会话，动态端口分配。

大多数情况使用 per-device-type daemon。

### Android Accessibility-First（强制规则）

⚠️ **Android 平台所有操作必须优先通过 Companion 无障碍服务执行，这是强制要求，不是建议。**

**强制优先级（不可跳过）：**

| 操作类型 | 优先级 1（必须先尝试） | 优先级 2（仅当优先级 1 失败时） | 优先级 3（最后手段） |
|---------|---------------------|-------------------------------|---------------------|
| 手势（tap/swipe/back/home/type 等） | Companion 无障碍服务 | ADB shell (`--type adb`) | — |
| 页面观察 & 元素定位 | Companion ui-tree (`source: companion`) | uiautomator (`source: uiautomator`) | 截图 (`screenshot`) |

**回退条件：只有以下情况才允许回退到下一优先级：**
- Companion 返回错误或超时
- `companion_status` 不是 `"ready"`
- ui-tree 节点质量持续低（<15% 有 text，连续 3+ 次）

**禁止行为：**
- ❌ 不得在 companion 可用时主动使用 `--type adb`
- ❌ 不得在 ui-tree 有效时跳过直接用截图
- ❌ 不得在未尝试 companion 的情况下直接使用 ADB

### Platform-Specific Constraints

| 平台 | UI Tree | 注意事项 |
|------|---------|---------|
| Android | Companion 优先，uiautomator 回退 | Flutter/游戏/WebView 节点质量低，回退截图 |
| HarmonyOS | 完整 | — |
| iOS real device | 完整（WDA） | — |
| iOS Simulator | MVP 暂不可用 | 始终用截图 |
| App on Mac | AX 树可能稀疏 | 截图为主，ui-tree 为辅 |

## Trigger Conditions

User mentions: phone/mobile operations, app testing, ADB/HDC/iOS commands, mobile UI automation.

## Step 1: Infer Platform

1. Explicit wording is binding: `Android`/`ADB`/`emulator` => Android; `HarmonyOS`/`鸿蒙`/`HDC` => HarmonyOS; `iPhone`/`iOS`/`bundle id`/`.app`/`Simulator`/`app_on_mac` => iOS
2. Generic request: reuse running daemon if it matches, otherwise default to Android

## Step 2: Startup & Target Selection

Run `phone-cli status`. If running + connected + correct platform:
- **Android**: 检查返回值中 `companion_status` 字段。如果不是 `"ready"`，运行 `phone-cli companion-setup` 初始化无障碍服务（详见下方第 6 步）
- 其他平台：直接 reuse

Otherwise stop and restart.

### Android / HarmonyOS Startup

1. **Android 必须优先运行启动脚本**：
   - `python3 .claude/skills/phone-automation/scripts/android_startup.py`
   - 如需指定模拟器：`PHONE_CLI_ANDROID_AVD="<avd>" python3 .claude/skills/phone-automation/scripts/android_startup.py`
   - 这个脚本会一次性完成：检查 `adb devices`、ADB 无响应时 kill 现有 ADB 进程并重启 server、无真机时检查模拟器是否已启动且可响应、无响应则杀掉模拟器并重启、未启动则自动拉起模拟器、最后启动 `phone-cli` daemon 并尝试 `companion-setup`
   - **除非脚本明确失败或需要用户选择 AVD，否则不要让 AI 手动逐条执行 `adb devices` / `adb kill-server` / `emulator -list-avds` / `phone-cli start`**
2. **HarmonyOS**：`hdc list targets` → 有设备则 `phone-cli stop` → `phone-cli start --device-type hdc` → `phone-cli status`
3. **无设备**（HarmonyOS）→ 告知用户无设备，建议检查连接
4. **（Android）初始化 Companion 无障碍服务**：脚本默认会在 daemon 启动后尝试 `phone-cli companion-setup`
   - 完整流程：检查 APK 是否存在 → 不存在则编译（`gradlew assembleDebug`，需 ANDROID_HOME + Java 17+）→ 安装到设备 → 启用无障碍权限 → 建立端口转发
   - **首次运行**会触发 Gradle 编译，耗时 1-3 分钟，后续运行 APK 已存在直接安装
   - 返回 `"available": true` → Companion 就绪，后续手势/ui-tree 自动走无障碍服务
   - **编译失败时**（`error_code: COMPANION_BUILD_FAILED`）：**必须将 `error_msg` 原文展示给用户**，让用户自行修复编译环境。常见原因：
     - `ANDROID_HOME` 或 `ANDROID_SDK_ROOT` 未设置或路径无效
     - Java 17+ 未安装或版本过低
     - `android-companion` 项目目录缺失
     - Gradle 编译错误（依赖下载失败、SDK 版本不匹配等）
   - 编译失败不阻塞使用，手势回退 ADB shell，ui-tree 退化为 uiautomator

### iOS Startup

1. `phone-cli detect-runtimes --device-type ios`
2. No candidates: report reasons. One: auto-select. Multiple: ask user.
3. Start: `phone-cli start --device-type ios --runtime device|simulator|app-on-mac [--device-id <id>]`
4. Verify: `phone-cli device-info`

### Multi-Device Selection

- Android/HarmonyOS: `phone-cli devices` → `phone-cli set-device <ID>`
- iOS: already bound from detect-runtimes; switch via `phone-cli set-device <ID>`

### Emulator Auto-Start

默认由 `scripts/android_startup.py` 负责，不要手动展开。只有在脚本失败且需要人工兜底时才使用下面流程：

1. `emulator -list-avds`, ask user which AVD
2. **Always** `cd $ANDROID_HOME/emulator && ./emulator -avd <name> -no-audio -no-boot-anim`
3. **NEVER** use `-no-window`（黑屏）or `-no-snapshot-load`（慢）
4. Wait: `adb wait-for-device && adb shell 'while [[ -z $(getprop sys.boot_completed) ]]; do sleep 2; done'`

## Step 3: Device Sanity Check

1. `phone-cli ui-tree` — valid nodes → proceed
2. `UI_TREE_UNAVAILABLE` → `phone-cli check-screen`:
   - `all_black`/`all_white`: `phone-cli home`, wait 2s, re-check; emulator may need restart with `-no-snapshot-load`
   - `normal` → proceed

## Step 4: Task Classification

| Type | Criteria | Action |
|------|----------|--------|
| Simple | Single operation | Execute directly |
| Medium | 2-5 steps, linear flow | Execute sequentially |
| Complex | Multi-step, dynamic decisions | Brainstorming → Subagent |

## Step 5 (Complex Tasks): Brainstorming

1. Clarify goal and success criteria
2. Decompose into steps with `action` + `success_criteria`
3. Identify sensitive operations and login/auth limitations
4. User confirms plan → output structured task plan for subagent

## Step 6: Execution

### Simple/Medium Tasks

```bash
# Android 首选：通过节点树观察和定位（快速、精确、无需视觉推理）
phone-cli ui-tree
# 解析节点 text/bounds/resource_id 定位目标元素，取 bounds 中心点坐标

# 操作
phone-cli tap 500 300

# 仅在需要视觉确认时才截图（颜色、图片、动画、Flutter/游戏页面）
phone-cli screenshot --resize 720
```

### 每步方案标注（强制）

Android 平台每执行一个操作，**必须在输出中标注该步使用的方案**，格式：

**标注格式：**
- `[Companion]` — 通过辅助服务执行（绿色通道，正常情况）
- `[ADB]` — 通过 ADB shell 执行（回退方案，需说明原因）
- `[Screenshot]` — 通过截图视觉识别（最后手段，需说明原因）

**示例输出：**
```
步骤 1: [Companion] 获取 ui-tree，找到"WLAN"按钮 (352, 1395)
步骤 2: [Companion] tap 点击 WLAN (source: companion)
步骤 3: [Companion] 获取 ui-tree 验证页面跳转成功
步骤 4: [Screenshot] 截图确认页面布局（原因：需要视觉确认颜色/图标）
```

**回退标注示例：**
```
步骤 5: [ADB] tap 点击确认按钮 (source: adb) ⚠️ Companion 超时，回退 ADB
步骤 6: [Screenshot] 截图观察页面 ⚠️ ui-tree 返回 UI_TREE_UNAVAILABLE
```

**规则：**
1. 每步必须有 `[Companion]`/`[ADB]`/`[Screenshot]` 前缀标签
2. 回退时必须附带 ⚠️ 和原因说明
3. 验证 `phone-cli` 返回的 `source` 字段，确保与标注一致
4. 如果连续 2+ 步回退为 ADB，主动检查 companion 状态并尝试恢复

### Observation & Verification

**Android / HarmonyOS 观察策略（Accessibility-First）：**

`phone-cli ui-tree` 是 Android 下的**主力观察和验证工具**，不是备选。节点树返回完整的文本、bounds、clickable/editable 属性，能直接用于：
- **定位元素**：通过 text/content-desc 找到按钮、输入框，取 bounds 中心点坐标
- **验证页面状态**：检查预期文本是否出现、页面标题是否切换、列表内容是否加载
- **确认操作结果**：输入后检查 editable 节点文本、点击后检查新页面节点

**⚠️ 强制检查 source 字段**：每次调用 `phone-cli ui-tree` 或手势命令后，必须检查返回 JSON 中的 `source` 字段：
- `source: "companion"` → 正常，继续
- `source: "uiautomator"` 或 `source: "adb"` → 标注为回退，记录原因
- 如果预期 companion 但实际回退，运行 `phone-cli status` 检查 `companion_status`

**截图仅在以下场景使用：**
- 节点质量低（Flutter/游戏/WebView/Canvas —— 多数节点无 text 和有意义的 resource_id）
- 需要视觉信息（颜色、图片内容、动画状态、布局样式）
- ui-tree 返回 `UI_TREE_UNAVAILABLE`
- iOS Simulator（ui-tree 暂不可用）

**ui-tree 质量退化规则**：当前任务中 ui-tree 已使用 3+ 次且有效率持续偏低（<15% 节点有 text 或有意义的 resource_id），后续该任务直接用截图。页面切换到新 App 或全新页面类型时可重新评估。

**是否需要验证**：根据操作自行判断。页面导航、app 启动、表单提交等需验证；简单 `back`/`home`、已知流程中的中间点击通常无需验证。

### App Launch

1. Android: `phone-cli launch <app>` → `phone-cli wait-for-app <pkg> --timeout 10` → `phone-cli app-state --package <pkg>`
2. iOS: `phone-cli launch --bundle-id <id>` → `phone-cli wait-for-app --bundle-id <id> --timeout 10`
3. Not foreground: `phone-cli get-current-app`, then inspect ui-tree or screenshot
4. `app_on_mac`: timeout but screenshot shows correct window → focus-detection lag, continue

### Diagnosing Black/Blank Screens

1. `phone-cli app-state` + `phone-cli get-current-app`
2. Android: `phone-cli app-log --package <pkg> --filter crash|lifecycle`
3. iOS: screenshot only (`app-log` not yet supported)

### Complex Tasks

Launch subagent via Agent tool: load `prompts/subagent.md`, inject steps and `prompts/rules_zh.md`.

**Sensitive Operations**: subagent must stop and return `CONFIRM_REQUIRED` for messages/forms/payments; main session gets user approval before continuing.

## Step 7: Result Report

- Report step-by-step status and key screenshots
- **Android 平台必须包含方案统计**：
  - Companion 执行步数 / 总步数
  - 回退 ADB 的步骤及原因
  - 使用截图的步骤及原因
  - 示例：`方案统计：8/10 步通过 Companion，1 步 ADB（超时），1 步 Screenshot（Flutter 页面）`
- On failure: analyze cause, ask user to retry or re-plan

## Command Reference

Android gesture commands default to Companion accessibility service. Pass `--type adb` to force ADB.

| Command | Description | Options |
|---------|-------------|---------|
| `status` | Daemon state | |
| `start` | Start daemon | `--device-type adb\|hdc\|ios`, `--runtime`, `--device-id` |
| `stop` | Stop daemon | |
| `detect-runtimes` | iOS runtimes | `--device-type ios` |
| `devices` | List devices | |
| `set-device ID` | Bind target | |
| `device-info` | Device info | |
| `companion-setup` | Init Companion accessibility (Android) | Auto: install, enable, port-forward |
| `screenshot` | Screenshot | `--resize 720`, `--task-id`, `--step` |
| `tap X Y` | Tap (0-999) | `--type adb\|companion` |
| `double-tap X Y` | Double tap | `--type adb\|companion` |
| `long-press X Y` | Long press | `--type adb\|companion` |
| `swipe X1 Y1 X2 Y2` | Swipe | `--type adb\|companion` |
| `type "text"` | Type (auto-clear) | `--type adb\|companion` |
| `back` | Back | `--type adb\|companion` |
| `home` | Home | `--type adb\|companion` |
| `launch` | Launch app | `APP`, `--bundle-id`, `--app-path` |
| `get-current-app` | Foreground app | |
| `ui-tree` | UI hierarchy | |
| `app-state` | App state | `--package` or `--bundle-id` |
| `wait-for-app` | Wait ready | `PKG`/`--bundle-id`, `--timeout` |
| `check-screen` | Screen health | `--threshold` |
| `app-log` | Logs (Android) | `--package`, `--filter` |
| `install APK` | Install (Android) | `--launch` |
| `clean-screenshots` | Clean files | `--all` |
| `log` | Daemon logs | `--tail`, `--task` |
| `version` | Version | |
| `daemon start\|stop\|status` | Central daemon | `--foreground` |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| screencap 全黑 | 勿用 `-no-window`，重启模拟器 |
| snapshot 恢复后黑屏 | 用 `-no-snapshot-load` 冷启动 |
| `qemu-system not found` | 先 `cd $ANDROID_HOME/emulator` |
| 模拟器存在但无 ADB 设备 | `lsof -i :5037` → kill → `adb kill-server && adb start-server` |
