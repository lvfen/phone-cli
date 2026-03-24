# phone-cli iOS 多运行时冒烟 Runbook

## 1. 目的

在发布 `device` / `simulator` / `app-on-mac` 三种 iOS runtime 之前，使用一份统一 runbook 做最小人工验证，覆盖：

- CLI runtime discovery
- `start` 自动选择与显式指定
- `launch` / `wait-for-app` / `app-state`
- 截图与基础交互
- skill 在单候选 / 多候选下的行为

## 2. 环境前提

1. 在 macOS 上执行
2. 已安装依赖：

```bash
pip install -e ".[ios,dev]"
```

3. 若验证真机：
   - 设备已连接并被 `tidevice list` 识别
   - WebDriverAgent 已可用
4. 若验证 Simulator：
   - 至少 1 个 iOS Simulator 处于 Booted
5. 若验证 `app-on-mac`：
   - Apple Silicon Mac
   - Shell / Python 已获得 Accessibility 和 Screen Recording 权限

## 3. 通用预检查

先执行：

```bash
phone-cli stop
phone-cli detect-runtimes --device-type ios
```

确认输出满足以下之一：

1. 无候选时：
   - 返回 `NO_AVAILABLE_IOS_RUNTIME` 或空候选结果
   - `reasons` 中能看出是缺真机、缺 Booted Simulator，还是宿主权限 / 依赖不足
2. 单候选时：
   - 结果中能明确看到唯一 `runtime` 和 `target_id`
3. 多候选时：
   - 结果中能列出多个候选
   - 不应静默默认某个 runtime

## 4. 真机 smoke

```bash
phone-cli stop
phone-cli start --device-type ios --runtime device --device-id <udid>
phone-cli device-info
phone-cli launch --bundle-id com.apple.Preferences
phone-cli wait-for-app --bundle-id com.apple.Preferences --timeout 10
phone-cli app-state --bundle-id com.apple.Preferences
phone-cli screenshot
phone-cli tap 500 500
```

检查点：

1. `device-info` 中 `ios_runtime=device`
2. `target_id` 为传入的 `udid`
3. `wait-for-app` 成功
4. `app-state` 中前台状态正确
5. 截图非空，点击后界面有可观察变化

## 5. Simulator smoke

```bash
phone-cli stop
phone-cli start --device-type ios --runtime simulator --device-id <sim_udid>
phone-cli device-info
phone-cli launch --bundle-id com.apple.Preferences
phone-cli wait-for-app --bundle-id com.apple.Preferences --timeout 10
phone-cli app-state --bundle-id com.apple.Preferences
phone-cli screenshot
phone-cli tap 500 500
phone-cli type "hello simulator"
phone-cli check-screen
```

检查点：

1. `device-info` 中 `ios_runtime=simulator`
2. `target_id` 为 Booted Simulator 的 UDID
3. `launch` / `wait-for-app` / `app-state` 正常
4. 截图正常，`check-screen` 不是 `all_black` / `all_white`
5. `ui-tree` 若返回不可用，视为 MVP 预期，不记为失败

## 6. app-on-mac smoke

```bash
phone-cli stop
phone-cli start --device-type ios --runtime app-on-mac
phone-cli device-info
phone-cli launch --bundle-id com.example.demo
phone-cli wait-for-app --bundle-id com.example.demo --timeout 10
phone-cli app-state --bundle-id com.example.demo
phone-cli screenshot
phone-cli tap 500 500
phone-cli type "hello mac"
phone-cli ui-tree
```

如果没有稳定的 bundle id，可改为：

```bash
phone-cli launch --app-path "/path/to/Demo.app"
```

检查点：

1. `device-info` 中 `ios_runtime=app_on_mac`
2. `target_id=local-mac`
3. `launch` 后能拿到绑定窗口
4. 截图正常
5. `ui-tree` 至少返回稳定根节点结构
6. 若 AX 节点很少，只记为“质量一般”，不记为失败

## 7. 自动选择 smoke

目标：验证 `phone-cli start --device-type ios` 的自动决策。

### 场景 A：仅 1 个候选

前提：当前机器只保留一个可用候选。

```bash
phone-cli stop
phone-cli start --device-type ios
phone-cli device-info
```

检查点：

1. 启动成功
2. `device-info` 中 runtime 与唯一候选一致

### 场景 B：多个候选

前提：同时具备至少 2 个可用候选，例如真机 + Booted Simulator。

```bash
phone-cli stop
phone-cli start --device-type ios
```

检查点：

1. 返回 `RUNTIME_SELECTION_REQUIRED`
2. 不应偷偷默认 `device` 或 `simulator`

## 8. Skill smoke

目标：验证 `.claude/skills/phone-automation/SKILL.md` 的控制流与 CLI 一致。

### 场景 A：用户显式指定 runtime

示例输入：

- “用 iOS 模拟器打开设置页并截图”
- “用 app on mac 跑这个 bundle id”

检查点：

1. skill 会先做 `detect-runtimes`
2. 但只在指定 runtime 内判断候选
3. 若该 runtime 下仅 1 个候选，不会额外追问

### 场景 B：用户未指定 runtime，只有 1 个候选

示例输入：

- “帮我在 iPhone 上打开设置页”

检查点：

1. skill 会先做 `detect-runtimes`
2. 发现只有 1 个候选后直接继续
3. 启动命令会显式带 `--runtime`

### 场景 C：用户未指定 runtime，存在多个候选

示例输入：

- “帮我在 iOS 上打开设置页”

检查点：

1. skill 必须先询问用户使用哪个 runtime / target
2. 询问前不能直接启动 daemon

## 9. 失败分诊

| 现象 | 优先判断 | 处理方式 |
|---|---|---|
| `NO_AVAILABLE_IOS_RUNTIME` | 当前没有任何可用 iOS 候选 | 连接真机 / 启动 Simulator / 修复 host 依赖与权限 |
| `RUNTIME_SELECTION_REQUIRED` | 候选过多，未选择 | 让用户明确指定 runtime 或 `device_id` |
| `TARGET_NOT_SELECTED` | 同一 runtime 下有多个 target | 重新用 `--device-id` 启动 |
| `ACCESSIBILITY_PERMISSION_REQUIRED` | 宿主权限未授权 | 去系统设置授予 Accessibility |
| 截图全黑 / 全白 | runtime 或渲染异常 | 先排查环境，不要先怪业务 App |

## 10. 退出标准

满足以下条件后，视为 iOS 多运行时可以进入发布阶段：

1. 真机 smoke 通过
2. 至少 1 台 Booted Simulator smoke 通过
3. 至少 1 台 Apple Silicon Mac 的 `app-on-mac` smoke 通过
4. 自动选择与多候选报错行为符合预期
5. skill 在显式 runtime、单候选、多候选三类场景下行为正确
