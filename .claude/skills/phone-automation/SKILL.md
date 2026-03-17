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
   - If `"status": "running"`: record device info, proceed to Step 1
   - If `"status": "stopped"` or command fails:
     a. Run `phone-cli start --device-type adb`
     b. Wait 2 seconds
     c. Run `phone-cli status` again
     d. If still not running, tell the user:
        - Check if phone-cli is installed: `pip install -e ~/development/code/phone-cli`
        - Check if ADB is available: `adb devices`
        - Check if a device is connected

## Step 1: Device Check

1. Run `phone-cli devices`
2. Parse JSON output for device list
3. If no devices: guide user to connect a device
4. If multiple devices: ask user which one to use

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
4. User confirms the plan

Output a structured task plan for the subagent.

## Step 4: Execution

### Simple/Medium Tasks

Execute `phone-cli` commands directly in main session via Bash:

```bash
# Example: take a screenshot
phone-cli screenshot --resize 720
# Read the screenshot file path from JSON output, then use Read tool to view it

# Example: tap at position
phone-cli tap 500 300
```

All commands output JSON. Parse `status` field to check success.

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
| `phone-cli version` | Show version | |
