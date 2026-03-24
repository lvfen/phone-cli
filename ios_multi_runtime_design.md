# phone-cli iOS 多运行时设计方案

## 1. 背景

当前 `phone-cli` 的 iOS 支持，实质上只有一条真机链路：`tidevice + WebDriverAgent`。这条链路适合 USB 连接的真实 iPhone，但无法覆盖以下两类本地调试场景：

- iOS Simulator
- Apple Silicon Mac 上的 `iOS App on Mac`

本方案的目标是：**仅修改 `phone-cli`，不修改 `GameHelperiOS` 工程，不新增 App 内测试桩，也不引入 Mac Catalyst 方案**，让 `phone-cli` 能在同一套 CLI 接口下支持三种 iOS 运行时：

- `ios-device`
- `ios-simulator`
- `ios-app-on-mac`


## 2. 约束与边界

### 2.1 必须满足

- 不修改 `GameHelperiOS` 工程配置、target、Info.plist、Podfile 或业务代码
- 保持 `phone-cli` 的 JSON 输出格式和现有命令习惯
- 现有真机能力不能回退
- 本地调试时允许通过 `bundle id` 或 `.app` 路径直接启动应用

### 2.2 明确不做

- 不将方案改造成 `Mac Catalyst`
- 不要求业务 App 集成额外自动化 SDK
- 不在第一阶段追求三种运行时完全一致的能力集合
- 不承诺 Simulator 与 `iOS App on Mac` 在 `ui-tree` 能力上达到真机 WDA 同等级别


## 3. 当前问题

### 3.1 iOS 后端只有真机实现

当前 `phone-cli` 的 `ios` 目录直接绑定 `tidevice + WDA`，天然要求：

- 存在 USB 连接的真机
- `tidevice` 可识别设备
- 设备上有可工作的 `WebDriverAgent`

因此：

- Simulator 无法工作
- `iOS App on Mac` 无法工作

### 3.2 CLI 层对 iOS 运行时抽象不足

当前 CLI 只有 `adb | hdc | ios` 三种 `device_type`，没有 iOS 运行时细分：

- 真机
- 模拟器
- `iOS App on Mac`

导致 iOS 内部无法按运行环境选择不同 backend。

### 3.3 多个命令仍然是 ADB-only

以下命令当前只支持 ADB：

- `app-state`
- `wait-for-app`
- `check-screen`
- `app-log`
- `install`

这会让 iOS 端体验在功能面上明显缺口。

### 3.4 `launch` 入口过于依赖固定映射

当前 `launch` 主要依赖预置 `app_name -> bundle id` 映射，问题是：

- 本地测试包名称未必在映射表中
- `iOS App on Mac` 本地调试时，应用可能以 `.app` 文件形式存在于 `DerivedData`
- 同一个应用在不同环境下更适合使用 `bundle id` 或 `app_path` 启动


## 4. 目标

### 4.1 功能目标

在不改业务工程的前提下，让下面这些命令对 iOS 三种运行时尽量统一：

- `start`
- `devices`
- `set-device`
- `device-info`
- `launch`
- `get-current-app`
- `app-state`
- `wait-for-app`
- `screenshot`
- `tap`
- `double-tap`
- `long-press`
- `swipe`
- `type`
- `ui-tree`
- `check-screen`
- 在开始自动化前自动发现当前可用的 iOS runtime
- 当仅发现一个可用 runtime 时自动选中并继续
- 当同时发现多个可用 runtime 时，返回候选列表，并由上层 skill 询问用户选择

### 4.2 架构目标

- 继续保留 `device_type=ios`
- 在 iOS 内部新增 `runtime` 路由，不影响 Android/HarmonyOS
- 将“启动、截图、点击、输入、获取前台应用”等能力抽象成统一接口
- 允许不同 runtime 返回不同能力矩阵，并在不支持时明确报错
- 增加独立于 daemon 启动流程的 runtime discovery 能力，供 CLI 和 skill 共同复用


## 5. 总体设计

### 5.1 设计原则

- 外部命令保持稳定，内部做多 runtime 分发
- 真机优先复用现有实现，尽量减少回归风险
- Simulator 和 `iOS App on Mac` 优先打通 MVP 闭环，再逐步补齐高级能力
- 对不支持的操作返回结构化错误，而不是静默失败

### 5.2 新的模型

在 `device_type=ios` 下新增 `ios_runtime` 概念：

- `device`
- `simulator`
- `app_on_mac`

daemon state 中新增以下字段：

```json
{
  "device_type": "ios",
  "ios_runtime": "app_on_mac",
  "device_id": null,
  "target_id": "local-mac",
  "bundle_id": "com.tencent.gamehelper",
  "window_id": 12345,
  "device_status": "connected",
  "screen_size": [1512, 982],
  "capabilities": {
    "launch": true,
    "screenshot": true,
    "tap": true,
    "type": true,
    "ui_tree": true,
    "install": false,
    "home": false,
    "back": false,
    "app_log": false
  }
}
```

### 5.3 运行时自动发现与选择

在 iOS 自动化真正开始前，不能再假设默认走真机，而是需要先做 runtime discovery。

#### 发现来源

- `device`：通过 `tidevice list --json` 检查当前已连接真机
- `simulator`：通过 `xcrun simctl list --json devices` 检查当前处于 `Booted` 状态的 Simulator
- `app_on_mac`：检查当前宿主是否满足 `iOS App on Mac` 自动化前提：
  - 运行环境为 macOS
  - CPU 架构为 Apple Silicon
  - `pyobjc` 宿主依赖可导入
  - Accessibility / Screen Recording 权限满足最小要求，或可在启动前完成预检查

#### 发现结果模型

建议 discovery 返回统一候选结构，例如：

```json
{
  "candidates": [
    {
      "runtime": "device",
      "target_id": "00008110-001234560E12801E",
      "label": "Longquan's iPhone",
      "status": "available"
    },
    {
      "runtime": "simulator",
      "target_id": "A1B2C3D4-E5F6-7890-1234-56789ABCDE00",
      "label": "iPhone 16 Pro (Booted)",
      "status": "available"
    },
    {
      "runtime": "app_on_mac",
      "target_id": "local-mac",
      "label": "Local Apple Silicon Mac",
      "status": "available"
    }
  ]
}
```

#### 选择策略

- 未发现任何候选时：返回结构化错误，提示当前缺少真机、Booted Simulator 或 `app_on_mac` 运行前提
- 仅发现 1 个候选时：自动选中该 runtime，并继续启动自动化
- 发现多个候选时：**不做隐式优先级选择**，而是返回候选列表，由上层 skill 询问用户使用哪一项

这样可以避免在真机和模拟器同时存在时，系统偷偷选错目标。


## 6. 模块重构方案

### 6.1 新目录结构

建议将现有 `phone_cli/ios/` 改造为门面层，并新增 runtime 子目录：

```text
phone_cli/
└── ios/
    ├── __init__.py
    ├── runtime/
    │   ├── base.py
    │   ├── router.py
    │   ├── device_backend.py
    │   ├── simulator_backend.py
    │   └── app_on_mac_backend.py
    ├── connection.py
    ├── device.py
    ├── input.py
    └── screenshot.py
```

其中：

- `device_backend.py` 主要复用现有 `tidevice + WDA`
- `simulator_backend.py` 负责 `simctl` 相关能力
- `app_on_mac_backend.py` 负责 macOS 宿主能力接入
- `router.py` 根据 daemon state 选择 backend

### 6.2 统一后端接口

定义 `IOSBackend` 抽象接口，建议最少包含：

```python
class IOSBackend(Protocol):
    def list_targets(self) -> list[DeviceInfo]: ...
    def get_capabilities(self) -> dict[str, bool]: ...
    def get_screen_size(self, target_id: str | None = None) -> tuple[int, int]: ...

    def launch_app(
        self,
        app_name: str | None = None,
        bundle_id: str | None = None,
        app_path: str | None = None,
        target_id: str | None = None,
    ) -> dict: ...

    def get_current_app(self, target_id: str | None = None) -> dict: ...
    def get_app_state(
        self,
        bundle_id: str | None = None,
        target_id: str | None = None,
    ) -> dict: ...
    def wait_for_app(
        self,
        bundle_id: str,
        timeout: int = 30,
        state: str = "running",
        target_id: str | None = None,
    ) -> dict: ...

    def get_screenshot(self, target_id: str | None = None) -> Screenshot: ...
    def tap(self, x: int, y: int, target_id: str | None = None) -> None: ...
    def double_tap(self, x: int, y: int, target_id: str | None = None) -> None: ...
    def long_press(self, x: int, y: int, duration_ms: int = 3000, target_id: str | None = None) -> None: ...
    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int | None = None, target_id: str | None = None) -> None: ...
    def type_text(self, text: str, target_id: str | None = None) -> None: ...
    def clear_text(self, target_id: str | None = None) -> None: ...
    def ui_tree(self, target_id: str | None = None) -> dict: ...
    def check_screen(self, threshold: float = 0.95, target_id: str | None = None) -> dict: ...
```


## 7. 三种运行时设计

### 7.1 `ios-device`

#### 实现方式

- 复用当前 `tidevice + WDA`
- 基础能力继续走：
  - `tidevice list`
  - `tidevice wdaproxy`
  - `wda.Client`

#### 能力范围

- `launch`
- `get-current-app`
- `app-state`
- `wait-for-app`
- `screenshot`
- `tap/swipe/type`
- `ui-tree`

#### 处理原则

- 尽量只做封装迁移，不改现有行为
- 将现有 `phone_cli/ios/*.py` 封装为 `device_backend` 的底层实现

### 7.2 `ios-simulator`

#### 实现方式

Simulator 相关生命周期优先走 `xcrun simctl`：

- `simctl list --json devices`
- `simctl boot <udid>`
- `simctl install <udid> <app_path>`
- `simctl launch <udid> <bundle_id>`
- `simctl io <udid> screenshot <path>`

#### 输入方案

第一阶段不依赖业务 App 改造，也不要求业务工程增加测试 target，因此输入优先走宿主侧事件注入：

- 找到 Simulator.app 当前窗口
- 获取设备画面在窗口中的渲染区域
- 将 `0-999` 相对坐标映射到渲染区域
- 用 macOS 事件注入完成 `tap/swipe/type`

#### `ui-tree` 策略

第一阶段允许 `ui-tree` 返回 `UI_TREE_UNAVAILABLE`，理由：

- 纯 `simctl` 不直接提供 Accessibility 树
- 在不改业务工程的前提下，短期不引入 XCTest runner

第二阶段如需补齐，可评估：

- WDA on Simulator
- XCTest UI Automation helper

### 7.3 `ios-app-on-mac`

#### 实现方式

该运行时不使用 `tidevice`，也不使用 `simctl`，直接走 macOS 宿主能力：

- 启动应用：`open -b <bundle_id>` 或 `open "<app_path>"`
- 查找前台应用：`NSWorkspace`
- 窗口识别与截图：Quartz
- 输入事件：`CGEvent`
- 界面树：macOS Accessibility API

#### 为什么这是正确路线

`iOS App on Mac` 本质上是 iOS App 在 Apple Silicon Mac 上作为宿主应用运行，不是 iOS 设备，也不是 Simulator。因此：

- 无法走 `tidevice`
- 无法走 `simctl`
- 最合理的方案是基于 macOS 的窗口、输入、Accessibility 能力实现自动化

#### 启动方式

支持三种优先级：

1. `--bundle-id`
2. `--app-path`
3. `app_name` 映射

推荐测试时优先使用：

```bash
phone-cli launch --bundle-id com.tencent.xxx
```

或：

```bash
phone-cli launch --app-path "/path/to/App.app"
```

注意：对 `iOS App on Mac`，`app_path` 通常来自 Xcode 本地构建产物或已存在的 `.app` 包；本方案不负责构建，只负责启动和自动化。

#### `ui-tree` 策略

通过 AX tree 读取目标应用窗口下的元素树，输出兼容现有 `ui-tree` 的结构化数据：

- `role`
- `title`
- `description`
- `value`
- `x`
- `y`
- `width`
- `height`
- `enabled`
- `focused`

需要接受的现实边界：

- UIKit/Flutter 页面在 Mac 上不一定暴露完整 Accessibility 语义
- `ui-tree` 质量可能不如真机 WDA
- 当 AX tree 稀疏时，需要退回截图 + 坐标流


## 8. CLI 设计调整

### 8.1 `start`

新增参数：

```bash
phone-cli start --device-type ios --runtime device
phone-cli start --device-type ios --runtime simulator --device-id <sim_udid>
phone-cli start --device-type ios --runtime app-on-mac
```

建议兼容逻辑：

- 指定 `--runtime` 时，按显式 runtime 启动
- 未指定 `--runtime` 时，先执行 runtime discovery
- 若 discovery 仅返回 1 个候选，则自动选择该 runtime，并自动填充 `device_id` / `target_id`
- 若 discovery 返回多个候选，则返回 `RUNTIME_SELECTION_REQUIRED`
- `app-on-mac` 在内部 state 中归一化为 `app_on_mac`

### 8.2 `launch`

在保留原 `app_name` 参数的同时新增：

- `--bundle-id`
- `--app-path`

优先级建议：

1. `bundle_id`
2. `app_path`
3. `app_name`

### 8.3 `device-info`

返回更多运行时字段：

- `device_type`
- `ios_runtime`
- `target_id`
- `bundle_id`
- `screen_size`
- `device_status`
- `capabilities`

### 8.4 `devices`

返回值按 runtime 区分：

- `device`：真机列表
- `simulator`：模拟器列表
- `app_on_mac`：返回宿主目标，例如 `local-mac`

### 8.5 `detect-runtimes`

为了解决 “daemon 启动前就需要知道应该选哪个 iOS runtime” 的问题，建议新增独立命令：

```bash
phone-cli detect-runtimes --device-type ios
```

返回值建议包含：

- `candidates`
- `auto_selectable`
- `selection_required`
- `reasons`

这样上层 skill 可以在 `phone-cli start` 之前先探测环境，再决定是否需要询问用户。

### 8.6 skill 协同策略

`phone-automation` skill 在处理 iOS 自动化任务时，建议新增如下前置流程：

1. 若用户明确指定了真机 / 模拟器 / `app_on_mac`，则直接按用户指定执行
2. 若用户未指定，则先调用 `phone-cli detect-runtimes --device-type ios`
3. 若没有候选，则告诉用户当前未检测到可用 iOS runtime，并给出排查建议
4. 若只有一个候选，则 skill 直接使用该 runtime 启动 `phone-cli`
5. 若存在多个候选，则 skill 必须先询问用户，例如：

```text
检测到多个可用的 iOS 目标：
1. 真机：Longquan's iPhone
2. 模拟器：iPhone 16 Pro (Booted)
3. App on Mac：Local Apple Silicon Mac

这次想使用哪一种？
```

6. 用户选择后，再执行对应的：
   - `phone-cli start --device-type ios --runtime device --device-id <udid>`
   - `phone-cli start --device-type ios --runtime simulator --device-id <sim_udid>`
   - `phone-cli start --device-type ios --runtime app-on-mac`

这样可以把“环境发现”和“交互决策”分层：

- `phone-cli` 负责准确发现候选
- skill 负责在多候选时进行自然语言交互
- 当只有单候选时，skill 不打断用户，直接继续自动化流程


## 9. 能力矩阵

| 能力 | ios-device | ios-simulator | ios-app-on-mac |
|---|---|---|---|
| `devices` | 支持 | 支持 | 支持 |
| `launch` | 支持 | 支持 | 支持 |
| `get-current-app` | 支持 | 支持 | 支持 |
| `app-state` | 支持 | 支持 | 支持 |
| `wait-for-app` | 支持 | 支持 | 支持 |
| `screenshot` | 支持 | 支持 | 支持 |
| `tap` | 支持 | 支持 | 支持 |
| `swipe` | 支持 | 支持 | 支持 |
| `type` | 支持 | 支持 | 支持 |
| `ui-tree` | 支持 | MVP 可缺失 | 支持，但质量依赖 AX |
| `check-screen` | 支持 | 支持 | 支持 |
| `install` | 非必须 | 支持 | MVP 不支持 |
| `home/back` | 支持 | 部分支持 | 不保证等价 |
| `app-log` | 可选 | 可选 | MVP 不支持 |


## 10. 文件级改造建议

### 10.1 新增文件

- `phone_cli/ios/runtime/base.py`
- `phone_cli/ios/runtime/router.py`
- `phone_cli/ios/runtime/discovery.py`
- `phone_cli/ios/runtime/device_backend.py`
- `phone_cli/ios/runtime/simulator_backend.py`
- `phone_cli/ios/runtime/app_on_mac_backend.py`

### 10.2 修改文件

- `phone_cli/ios/__init__.py`
  - 改为统一门面层
- `phone_cli/cli/main.py`
  - 增加 `--runtime`
  - 增加 `--bundle-id`
  - 增加 `--app-path`
  - 增加 `detect-runtimes`
- `phone_cli/cli/commands.py`
  - 将 ADB-only 能力抽象到跨 runtime 分发
  - `ui-tree` 改为由 iOS backend 自己负责
- `phone_cli/cli/daemon.py`
  - state 中新增 `ios_runtime`、`target_id`、`bundle_id`、`capabilities`
  - `start()` 在未显式指定 iOS runtime 时复用 discovery 结果
- `phone_cli/cli/output.py`
  - 新增错误码
- `setup.py`
  - 增加 macOS 宿主自动化依赖
- `.claude/skills/phone-automation/SKILL.md`
  - 增加 iOS runtime discovery 与多候选询问逻辑


## 11. 新增错误码

建议增加以下错误码：

- `UNSUPPORTED_OPERATION`
- `TARGET_NOT_SELECTED`
- `APP_NOT_BOUND`
- `ACCESSIBILITY_PERMISSION_REQUIRED`
- `WINDOW_NOT_FOUND`
- `BUNDLE_ID_REQUIRED`
- `NO_AVAILABLE_IOS_RUNTIME`
- `RUNTIME_SELECTION_REQUIRED`
- `RUNTIME_NOT_SUPPORTED`

使用原则：

- 不支持的能力要明确告诉调用方
- 不要把“未实现”和“执行失败”混为同一类错误


## 12. 依赖建议

### 12.1 保留

- `tidevice`
- `facebook-wda`

### 12.2 新增

用于 `ios-simulator` 和 `ios-app-on-mac` 的宿主能力接入：

- `pyobjc-framework-AppKit`
- `pyobjc-framework-Quartz`
- `pyobjc-framework-ApplicationServices`

### 12.3 运行前提

需要在 macOS 系统层授予：

- Accessibility 权限
- Screen Recording 权限

否则以下能力会失败：

- 窗口级截图
- 鼠标点击/拖拽
- 键盘事件注入
- AX tree 读取


## 13. 分阶段实施计划

### Phase 1：iOS 后端重构

目标：

- 建立 `ios_runtime` 概念
- 建立 runtime discovery 能力
- 建立 backend router
- 将现有真机逻辑迁移到 `device_backend`
- `launch` 支持 `bundle_id`

验收标准：

- 现有 `phone-cli start --device-type ios` 行为保持兼容
- 当只存在 1 个 iOS runtime 时可自动完成选择
- 当存在多个 runtime 时可返回候选并要求上层选择
- 真机链路不回归

### Phase 2：Simulator MVP

目标：

- `devices`
- `launch`
- `app-state`
- `wait-for-app`
- `screenshot`
- `tap/swipe/type`
- `check-screen`

暂缓：

- 高质量 `ui-tree`
- 完整日志能力

验收标准：

- 能在模拟器中启动目标 App
- 能截图并完成基础交互

### Phase 3：`iOS App on Mac` MVP

目标：

- `launch`
- `get-current-app`
- `app-state`
- `wait-for-app`
- `screenshot`
- `tap/swipe/type`
- `ui-tree`

暂缓：

- `install`
- `home/back` 的强语义兼容
- `app-log`

验收标准：

- 在 M1 Mac 上通过 `bundle id` 或 `app_path` 启动应用
- 能截图
- 能点击
- 能输入
- 能识别当前前台 App

### Phase 4：能力补齐

目标：

- Simulator `ui-tree`
- 更准确的窗口坐标换算
- `app-log` 与崩溃诊断
- 更稳定的多窗口处理


## 14. 验证计划

### 14.1 单元测试

为以下模块补测试：

- runtime 路由
- runtime discovery
- daemon state 读写
- CLI 参数解析
- 能力矩阵分发
- 错误码返回

### 14.2 集成测试

分别准备 3 组环境：

- 真机环境
- 至少 1 个 booted Simulator
- 1 台 Apple Silicon Mac，已授权 Accessibility/Screen Recording

每组至少验证：

1. `start`
2. `detect-runtimes`
3. `devices`
4. `launch`
5. `screenshot`
6. `tap`
7. `type`
8. `get-current-app`
9. `app-state`

### 14.3 回归重点

- 真机现有命令是否保持兼容
- 坐标换算是否仍基于 `0-999`
- `launch` 新参数是否不影响旧命令
- JSON 返回结构是否未破坏现有调用方


## 15. 风险与应对

### 15.1 `iOS App on Mac` 的 AX tree 可能不完整

风险：

- Flutter 或自绘界面在 Mac 宿主下可能只暴露有限 Accessibility 信息

应对：

- 允许 `ui-tree` 稀疏
- 在自动化层优先使用截图 + 相对坐标

### 15.2 Simulator 输入注入的稳定性

风险：

- 如果通过宿主事件注入，需要准确识别 Simulator 渲染区域

应对：

- 先做固定前台窗口 MVP
- 后续补窗口缩放、边框、状态栏偏移修正

### 15.3 多窗口问题

风险：

- `iOS App on Mac` 与 Simulator 都可能存在多个窗口或多个实例

应对：

- daemon state 记录 `window_id`
- 默认操作最近一次 `launch` 绑定的目标窗口

### 15.4 权限问题

风险：

- macOS 未授予 Accessibility 或 Screen Recording 权限

应对：

- 在 `start` 或首次执行时做预检查
- 返回 `ACCESSIBILITY_PERMISSION_REQUIRED`

### 15.5 自动发现误判

风险：

- `app_on_mac` 可能满足宿主前提，但当前并没有目标应用可操作
- 真机已连接，但 WDA 尚不可用
- 存在多个候选时，如果系统静默默认某一个，很容易打到错误目标

应对：

- 将“运行时可用”与“目标 App 已就绪”拆成两个阶段校验
- discovery 阶段只负责发现候选，不隐式决定优先级
- 多候选时强制由 skill 向用户确认


## 16. 推荐落地顺序

建议严格按以下顺序推进：

1. 抽象 iOS backend 接口
2. 将真机实现迁移到 `device_backend`
3. `launch`、`app-state`、`wait-for-app` 改为统一分发
4. 做 Simulator MVP
5. 做 `iOS App on Mac` MVP
6. 最后补齐 `ui-tree`、日志与异常诊断

这样可以把风险拆开，避免一次性重构导致真机链路回归。


## 17. 结论

在“不修改 `GameHelperiOS` 工程”的约束下，`phone-cli` 仍然可以通过多 runtime backend 的方式支持：

- 真机
- 模拟器
- `iOS App on Mac`

推荐的最终形态是：

- 对外仍然是一个 `phone-cli`
- 对内在 `device_type=ios` 下细分 `runtime`
- 真机走 `tidevice + WDA`
- 模拟器走 `simctl + 宿主自动化`
- `iOS App on Mac` 走 `open + Quartz + AX + CGEvent`

这条路径不依赖业务工程改造，能够最大程度满足本地调试与自动化操作诉求，同时把回归风险控制在 `phone-cli` 仓库内部。
