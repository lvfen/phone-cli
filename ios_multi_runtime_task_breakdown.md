# phone-cli iOS 多运行时开发任务清单

## 1. 说明

本清单是在 `ios_multi_runtime_design.md` 和 `ios_multi_runtime_implementation_plan.md` 基础上继续细化出的开发任务列表，目标是把实施计划落成可以逐项执行的 `P0-P5` 任务。

建议使用方式：

- `P0-P2` 作为架构与控制流主线，必须优先完成
- `P3` 与 `P4` 可以在 `P2` 结束后并行推进
- `P5` 作为 skill、测试、发布收口
- 每项任务尽量对应一个清晰的提交边界
- 如某阶段中间发现真机能力回归，优先停止新 runtime 开发，先修复 `device` 链路

建议任务状态字段：

- `TODO`
- `DOING`
- `BLOCKED`
- `DONE`


## 2. 关键路径

最小可交付路径如下：

1. `P0-01` ~ `P0-05`
2. `P1-01` ~ `P1-06`
3. `P2-01` ~ `P2-10`
4. `P3-01` ~ `P3-10`
5. `P4-01` ~ `P4-09`
6. `P5-01` ~ `P5-07`

并行建议：

- `P3` 和 `P4` 可并行
- `P5-04` 文档示例可与 `P5-05` 测试补齐并行
- 宿主共享层任务优先复用，不要在 `simulator` 和 `app_on_mac` 各写一套


## 3. P0：技术验证与边界冻结

### P0-01 固化 runtime candidate 数据模型

- 目标：确定 discovery 输出结构，避免后续 CLI、daemon、skill 各自定义字段
- 影响范围：
  - `phone_cli/ios/runtime/discovery.py`
  - `ios_multi_runtime_design.md`
  - `ios_multi_runtime_implementation_plan.md`
- 输出：
  - `RuntimeCandidate` 模型
  - discovery JSON 样例
- 完成标准：
  - 至少固定 `runtime`、`target_id`、`label`、`status`
  - 明确是否需要 `reason`、`metadata` 字段
  - CLI 和 skill 均可直接消费

### P0-02 固化 runtime selection 规则

- 目标：明确“0 候选 / 1 候选 / 多候选”时的系统行为
- 影响范围：
  - `ios_multi_runtime_design.md`
  - `ios_multi_runtime_implementation_plan.md`
  - `phone_cli/cli/output.py`
- 输出：
  - 选择规则说明
  - 错误码清单
- 完成标准：
  - 0 候选返回 `NO_AVAILABLE_IOS_RUNTIME`
  - 1 候选自动选择
  - 多候选返回 `RUNTIME_SELECTION_REQUIRED`
  - 不允许 CLI 静默默认某个 runtime

### P0-03 验证真机 discovery provider

- 目标：确认 `tidevice list --json` 能稳定发现真机，并产出统一候选
- 影响范围：
  - `phone_cli/ios/runtime/discovery.py`
- 输出：
  - 真机 discovery provider 原型
- 完成标准：
  - 能识别 0 台、1 台、多台真机
  - 候选 `label` 可读
  - 失败时不抛裸异常，返回空候选或明确 reason

### P0-04 验证 Simulator discovery provider

- 目标：确认 `xcrun simctl list --json devices` 可稳定识别 `Booted` 模拟器
- 影响范围：
  - `phone_cli/ios/runtime/discovery.py`
- 输出：
  - Simulator discovery provider 原型
- 完成标准：
  - 仅返回 `Booted` 模拟器
  - 候选包含 `target_id=sim_udid`
  - 能区分“存在模拟器但未启动”和“命令执行失败”

### P0-05 验证 `app_on_mac` 宿主支持判定

- 目标：定义什么叫“支持 `app_on_mac`”
- 影响范围：
  - `phone_cli/ios/runtime/discovery.py`
  - 后续 `phone_cli/ios/host/permissions.py`
- 输出：
  - `app_on_mac` 支持判定条件清单
- 完成标准：
  - 至少验证 macOS、Apple Silicon、依赖可导入
  - 明确权限不足时是否视为“候选不可用”
  - 明确“宿主支持”不等于“目标 App 已启动”

### P0-06 冻结宿主共享层边界

- 目标：避免在 `simulator` 和 `app_on_mac` 中重复实现窗口、截图、输入逻辑
- 影响范围：
  - `phone_cli/ios/host/`
  - `ios_multi_runtime_implementation_plan.md`
- 输出：
  - 共享模块边界说明
- 完成标准：
  - 至少拆出 `permissions.py`、`windows.py`、`events.py`、`screenshots.py`、`ax_tree.py`
  - 明确每个模块对外接口

### P0-07 形成 P0 决策记录

- 目标：把技术验证结果沉淀为可执行约束，避免后续反复返工
- 影响范围：
  - `ios_multi_runtime_implementation_plan.md`
  - `ios_multi_runtime_task_breakdown.md`
- 输出：
  - 一版决策记录
- 完成标准：
  - 记录 discovery 字段
  - 记录选择规则
  - 记录宿主共享层职责
  - 记录已知未决项


## 4. P1：runtime 基础骨架

### P1-01 定义 `IOSBackend` 基础接口

- 目标：让三种 runtime 有统一能力抽象
- 影响范围：
  - `phone_cli/ios/runtime/base.py`
- 输出：
  - `IOSBackend` 协议或抽象基类
  - 能力矩阵模型
- 完成标准：
  - 至少覆盖 `list_targets`、`get_capabilities`、`launch_app`、`get_current_app`
  - 明确不支持能力的返回约定

### P1-02 定义 capability 与通用错误辅助

- 目标：统一 runtime 能力描述和不支持操作的错误输出
- 影响范围：
  - `phone_cli/ios/runtime/base.py`
  - `phone_cli/cli/output.py`
- 输出：
  - capability 字段清单
  - unsupported helper
- 完成标准：
  - `device`、`simulator`、`app_on_mac` 可返回各自 capability
  - 上层命令不再靠 `if device_type != "adb"` 这种硬编码判断

### P1-03 实现 discovery 聚合器骨架

- 目标：把真机、模拟器、`app_on_mac` 三个 provider 聚合为统一 discovery 入口
- 影响范围：
  - `phone_cli/ios/runtime/discovery.py`
- 输出：
  - `detect_ios_runtimes()` 之类的聚合入口
- 完成标准：
  - 返回统一候选数组
  - provider 失败时不影响其他 provider
  - 支持后续供 CLI 和 skill 复用

### P1-04 实现 runtime router

- 目标：根据 daemon state 选择正确 backend
- 影响范围：
  - `phone_cli/ios/runtime/router.py`
- 输出：
  - runtime -> backend 映射
- 完成标准：
  - state 为 `device` 时返回 `device_backend`
  - state 为 `simulator` 时返回 `simulator_backend`
  - state 为 `app_on_mac` 时返回 `app_on_mac_backend`
  - 未配置时有明确错误

### P1-05 迁移真机实现到 `device_backend`

- 目标：把当前 `tidevice + WDA` 封装成标准 backend
- 影响范围：
  - `phone_cli/ios/runtime/device_backend.py`
  - `phone_cli/ios/connection.py`
  - `phone_cli/ios/device.py`
  - `phone_cli/ios/input.py`
  - `phone_cli/ios/screenshot.py`
- 输出：
  - 真机 backend
- 完成标准：
  - 第一版只做封装，不改变真机行为
  - 真机 `launch`、`screenshot`、`tap`、`type` 与现状一致

### P1-06 重构 `phone_cli/ios/__init__.py` 为 facade

- 目标：把 `phone_cli.ios` 从“直连 WDA”改成“统一 facade + router”
- 影响范围：
  - `phone_cli/ios/__init__.py`
- 输出：
  - 对外稳定的统一入口
- 完成标准：
  - 现有 CLI 命令不需要一次性大改 import 路径
  - facade 内部已能按 runtime 分发

### P1-07 补齐 router / facade 单元测试

- 目标：在进入 CLI 重构前先锁住基础骨架行为
- 影响范围：
  - `tests/ios/test_runtime_router.py`
  - `tests/ios/test_capabilities.py`
- 输出：
  - router 和 capability 测试
- 完成标准：
  - router 返回正确 backend
  - 不支持能力时返回统一错误
  - 真机 backend 能被 facade 正确调用


## 5. P2：CLI / daemon / 控制流改造

### P2-01 扩展 `start` 参数

- 目标：让用户可以显式指定 iOS runtime
- 影响范围：
  - `phone_cli/cli/main.py`
- 输出：
  - `phone-cli start --device-type ios --runtime <x>`
- 完成标准：
  - 支持 `device`、`simulator`、`app-on-mac`
  - `app-on-mac` 内部归一化为 `app_on_mac`

### P2-02 扩展 `launch` 参数

- 目标：支持 `bundle_id` 和 `app_path`，不再仅依赖 `app_name`
- 影响范围：
  - `phone_cli/cli/main.py`
  - `phone_cli/cli/commands.py`
- 输出：
  - `--bundle-id`
  - `--app-path`
- 完成标准：
  - 参数优先级为 `bundle_id > app_path > app_name`
  - 旧的 `launch <app_name>` 仍兼容

### P2-03 新增 `detect-runtimes` 命令

- 目标：在 daemon 启动前独立探测 iOS runtime 候选
- 影响范围：
  - `phone_cli/cli/main.py`
  - `phone_cli/cli/commands.py`
  - `phone_cli/ios/runtime/discovery.py`
- 输出：
  - `phone-cli detect-runtimes --device-type ios`
- 完成标准：
  - 返回 `candidates`
  - 返回 `auto_selectable`
  - 返回 `selection_required`
  - 返回 `reasons`

### P2-04 扩展 daemon state 模型

- 目标：让 daemon 能保存 runtime 级别上下文
- 影响范围：
  - `phone_cli/cli/daemon.py`
- 输出：
  - 新 state 字段
- 完成标准：
  - state 至少包含 `ios_runtime`、`target_id`、`bundle_id`、`window_id`、`capabilities`
  - `device_id` 继续保留兼容字段

### P2-05 实现 `start` 的自动发现与自动选择

- 目标：打通“未指定 runtime 时自动发现”的主流程
- 影响范围：
  - `phone_cli/cli/daemon.py`
  - `phone_cli/ios/runtime/discovery.py`
- 输出：
  - iOS start 自动选择逻辑
- 完成标准：
  - 0 候选返回 `NO_AVAILABLE_IOS_RUNTIME`
  - 1 候选自动写入 state
  - 多候选返回 `RUNTIME_SELECTION_REQUIRED`

### P2-06 改造 `set-device` / `device-info` / `devices`

- 目标：让这些命令具备 runtime 语义
- 影响范围：
  - `phone_cli/cli/commands.py`
- 输出：
  - runtime-aware 的设备选择与信息查询
- 完成标准：
  - `devices` 按 runtime 返回列表
  - `device-info` 返回 `ios_runtime`、`target_id`、`capabilities`
  - `set-device` 对 simulator 也适用

### P2-07 改造 `launch` / `get-current-app` 分发逻辑

- 目标：让应用启动和前台应用获取都走 backend
- 影响范围：
  - `phone_cli/cli/commands.py`
  - `phone_cli/ios/__init__.py`
- 输出：
  - runtime-aware 的应用命令
- 完成标准：
  - iOS 命令层不再直接假定 WDA
  - 可以透传 `bundle_id` 和 `app_path`

### P2-08 改造 `app_state` / `wait_for_app` / `check_screen`

- 目标：移除 iOS 在命令层的 ADB-only 限制
- 影响范围：
  - `phone_cli/cli/commands.py`
  - `phone_cli/ios/__init__.py`
  - 各 runtime backend
- 输出：
  - backend 驱动的状态检查逻辑
- 完成标准：
  - iOS 下不会再直接返回 “only supported for ADB”
  - 未实现能力时返回 `UNSUPPORTED_OPERATION` 或约定错误

### P2-09 改造 `ui_tree` 分发逻辑

- 目标：让 iOS `ui-tree` 由 backend 自己负责
- 影响范围：
  - `phone_cli/cli/commands.py`
  - `phone_cli/ios/__init__.py`
- 输出：
  - runtime-aware 的 `ui_tree`
- 完成标准：
  - 真机仍走 WDA
  - Simulator MVP 可明确返回 `UI_TREE_UNAVAILABLE`
  - `app_on_mac` 预留 AX tree 接口

### P2-10 改造 heartbeat 为 runtime-aware

- 目标：避免 `app_on_mac` 或 simulator 被当作普通物理设备误判掉线
- 影响范围：
  - `phone_cli/cli/daemon.py`
- 输出：
  - 按 runtime 检查连通性的 heartbeat
- 完成标准：
  - `device` 仍基于真机列表
  - `simulator` 基于目标 Simulator 是否仍 Booted
  - `app_on_mac` 基于宿主可用性和窗口绑定状态做最小判定

### P2-11 扩展错误码与统一输出

- 目标：让新增控制流和新 runtime 错误可结构化返回
- 影响范围：
  - `phone_cli/cli/output.py`
- 输出：
  - 新错误码
- 完成标准：
  - 包含 `NO_AVAILABLE_IOS_RUNTIME`
  - 包含 `RUNTIME_SELECTION_REQUIRED`
  - 包含 `RUNTIME_NOT_SUPPORTED`
  - 包含 `TARGET_NOT_SELECTED`

### P2-12 更新 CLI / daemon 测试

- 目标：锁住控制流变化，防止后续回归
- 影响范围：
  - `tests/cli/test_main.py`
  - `tests/cli/test_commands.py`
  - `tests/cli/test_daemon.py`
- 输出：
  - CLI / daemon 新增测试
- 完成标准：
  - 覆盖 `detect-runtimes`
  - 覆盖 `start` 自动选择
  - 覆盖多候选错误返回
  - 覆盖 `launch` 参数优先级


## 6. P3：`ios-simulator` MVP

### P3-01 实现 Simulator 候选发现

- 目标：让 discovery 能输出 Booted Simulator 候选
- 影响范围：
  - `phone_cli/ios/runtime/discovery.py`
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - Simulator candidate provider
- 完成标准：
  - 候选包含 `runtime=simulator`
  - 候选包含 `target_id=udid`
  - 候选 `label` 含设备名

### P3-02 实现 `list_targets` / `get_capabilities`

- 目标：让 Simulator backend 具备最基础 target 与能力描述
- 影响范围：
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - target 列表与 capability 返回
- 完成标准：
  - `devices` 命令能返回 booted Simulator
  - capability 能反映 `ui_tree` 暂不可用

### P3-03 实现 `launch_app`

- 目标：支持通过 `bundle_id` 启动 Simulator 中的 App
- 影响范围：
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - `simctl launch`
- 完成标准：
  - 能对指定 `udid` 启动 App
  - 启动失败时返回结构化错误

### P3-04 调研并实现 `app_state`

- 目标：给 Simulator 定义最小可用的 app state 语义
- 影响范围：
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - `app_state` 实现
- 完成标准：
  - 至少能区分“未运行”和“已运行 / 前台”
  - 结果字段和真机尽量兼容
  - 语义限制要写进文档

### P3-05 实现 `wait_for_app`

- 目标：让 Simulator 可以替代固定 `sleep`
- 影响范围：
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - 基于 `app_state` 的轮询等待
- 完成标准：
  - 支持 `timeout`
  - 支持最小状态集
  - 超时返回明确错误

### P3-06 实现截图能力

- 目标：让 Simulator 完成截图闭环
- 影响范围：
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - `simctl io screenshot`
- 完成标准：
  - 能稳定输出 PNG
  - 结果能进入现有 screenshot 命令返回格式

### P3-07 实现宿主权限与窗口定位

- 目标：为后续点击、滑动、输入提供窗口基础能力
- 影响范围：
  - `phone_cli/ios/host/permissions.py`
  - `phone_cli/ios/host/windows.py`
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - Simulator 窗口查找与渲染区域识别
- 完成标准：
  - 能识别前台 Simulator 窗口
  - 能获取窗口 bounds 和渲染区域
  - 权限不足时返回结构化错误

### P3-08 实现坐标映射

- 目标：把 `0-999` 相对坐标稳定映射到 Simulator 渲染区域
- 影响范围：
  - `phone_cli/ios/host/windows.py`
  - `phone_cli/cli/commands.py`
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - 渲染区域坐标转换逻辑
- 完成标准：
  - 点击坐标不使用整窗 bounds 粗暴映射
  - 支持最小窗口缩放场景

### P3-09 实现 `tap` / `swipe` / `type`

- 目标：通过宿主事件注入打通基础交互
- 影响范围：
  - `phone_cli/ios/host/events.py`
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - 鼠标和键盘事件注入
- 完成标准：
  - `tap`、`swipe`、`type` 可用
  - 权限不足时返回明确错误

### P3-10 实现 `check_screen` 和 `ui_tree` 占位行为

- 目标：补齐 Simulator MVP 能力边界
- 影响范围：
  - `phone_cli/ios/runtime/simulator_backend.py`
- 输出：
  - `check_screen`
  - `ui_tree` 明确不可用
- 完成标准：
  - `check_screen` 基于截图实现
  - `ui_tree` 返回 `UI_TREE_UNAVAILABLE`

### P3-11 补齐 Simulator 测试

- 目标：锁住 MVP 行为，方便后续迭代
- 影响范围：
  - `tests/ios/test_runtime_discovery.py`
  - `tests/ios/test_simulator_backend.py`
  - `tests/cli/test_commands.py`
- 输出：
  - Simulator 单元测试和命令层测试
- 完成标准：
  - 覆盖 discovery
  - 覆盖 `launch`
  - 覆盖 `app_state` / `wait_for_app`
  - 覆盖 `ui_tree` 不可用分支


## 7. P4：`ios-app-on-mac` MVP

### P4-01 实现 `app_on_mac` 候选发现

- 目标：让 discovery 能识别宿主是否支持 `app_on_mac`
- 影响范围：
  - `phone_cli/ios/runtime/discovery.py`
- 输出：
  - `app_on_mac` candidate provider
- 完成标准：
  - 在 Apple Silicon Mac 上返回候选
  - 不支持时给出明确 reason

### P4-02 实现 `launch_app`

- 目标：支持 `bundle_id` 和 `app_path` 两种启动方式
- 影响范围：
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
- 输出：
  - `open -b`
  - `open <app_path>`
- 完成标准：
  - `bundle_id` 启动可用
  - `app_path` 启动可用
  - `app_name` 映射可作为最后兜底

### P4-03 实现 `get_current_app`

- 目标：获取当前前台宿主应用信息
- 影响范围：
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
  - 可能需要 `AppKit`
- 输出：
  - 当前前台应用查询
- 完成标准：
  - 能返回 bundle id
  - 可尽量映射为现有 app_name

### P4-04 实现 `app_state`

- 目标：定义 `app_on_mac` 的最小状态语义
- 影响范围：
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
- 输出：
  - 宿主进程 / 前台状态检查
- 完成标准：
  - 至少能区分“未启动”“已启动”“前台”
  - 与 `wait_for_app` 语义兼容

### P4-05 实现 `wait_for_app`

- 目标：让 `app_on_mac` 具备启动完成等待能力
- 影响范围：
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
- 输出：
  - 状态轮询等待
- 完成标准：
  - 支持 `timeout`
  - 支持 `running` / `foreground` 最小状态

### P4-06 实现窗口发现与绑定

- 目标：为截图和交互锁定目标窗口
- 影响范围：
  - `phone_cli/ios/host/windows.py`
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
  - `phone_cli/cli/daemon.py`
- 输出：
  - 窗口绑定逻辑
- 完成标准：
  - 能获取 `window_id`
  - 能把最近一次 `launch` 的窗口写回 state

### P4-07 实现截图和事件注入

- 目标：打通 `app_on_mac` 的基础视觉与交互能力
- 影响范围：
  - `phone_cli/ios/host/screenshots.py`
  - `phone_cli/ios/host/events.py`
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
- 输出：
  - 窗口截图
  - 点击 / 滑动 / 输入
- 完成标准：
  - 能截图
  - 能点击
  - 能输入

### P4-08 实现 AX tree 到 `ui-tree` 的映射

- 目标：让 `app_on_mac` 有一版结构稳定的 `ui-tree`
- 影响范围：
  - `phone_cli/ios/host/ax_tree.py`
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
- 输出：
  - AX -> `ui-tree` 兼容结构
- 完成标准：
  - 至少包含 `role`、`title`、`description`、`value`
  - 至少包含 `x`、`y`、`width`、`height`
  - 即使树稀疏，输出结构也稳定

### P4-09 处理最小多窗口策略

- 目标：在 MVP 阶段避免多窗口导致命中错误
- 影响范围：
  - `phone_cli/ios/host/windows.py`
  - `phone_cli/ios/runtime/app_on_mac_backend.py`
- 输出：
  - 最小多窗口绑定策略
- 完成标准：
  - 默认绑定最近一次 `launch` 命中的窗口
  - 若窗口消失，返回明确错误

### P4-10 补齐 `app_on_mac` 测试

- 目标：锁住 MVP 行为并验证结构兼容
- 影响范围：
  - `tests/ios/test_app_on_mac_backend.py`
  - `tests/ios/test_capabilities.py`
- 输出：
  - `app_on_mac` 单元测试
- 完成标准：
  - 覆盖 `launch`
  - 覆盖 `app_state` / `wait_for_app`
  - 覆盖 `ui_tree` 映射


## 8. P5：skill、测试、文档、发布收口

### P5-01 更新 `phone-automation` skill 的 iOS 前置流程

- 目标：让 skill 能在 iOS 场景下先做 runtime discovery
- 影响范围：
  - `.claude/skills/phone-automation/SKILL.md`
- 输出：
  - 新的 iOS 启动流程
- 完成标准：
  - iOS 任务开始前先调用 `phone-cli detect-runtimes --device-type ios`
  - Android / HarmonyOS 流程不受影响

### P5-02 实现单候选自动继续逻辑

- 目标：当只有一个可用 runtime 时，不打断用户
- 影响范围：
  - `.claude/skills/phone-automation/SKILL.md`
- 输出：
  - skill 自动选择逻辑
- 完成标准：
  - 单候选时直接启动对应 runtime
  - 启动命令带上显式 `--runtime`

### P5-03 实现多候选询问用户逻辑

- 目标：当同时有真机、Simulator、`app_on_mac` 候选时，skill 必须先问用户
- 影响范围：
  - `.claude/skills/phone-automation/SKILL.md`
- 输出：
  - 候选展示和提问模板
- 完成标准：
  - 询问文案清晰
  - 选择后能映射到具体启动命令

### P5-04 实现“用户已指定 runtime”直通逻辑

- 目标：避免 skill 多余打断
- 影响范围：
  - `.claude/skills/phone-automation/SKILL.md`
- 输出：
  - 显式指定 runtime 的直通分支
- 完成标准：
  - 用户明确说“用模拟器”时，不再走多候选询问
  - 直接启动对应 runtime

### P5-05 补齐文档示例与使用说明

- 目标：让后续调用者清楚知道三种 runtime 怎么用
- 影响范围：
  - `README.md`
  - `ios_multi_runtime_design.md`
  - `ios_multi_runtime_implementation_plan.md`
  - `ios_multi_runtime_task_breakdown.md`
- 输出：
  - 命令示例
  - skill 交互示例
- 完成标准：
  - 至少覆盖真机、Simulator、`app_on_mac`、多候选交互

### P5-06 补齐回归测试与冒烟脚本

- 目标：在交付前完成全链路回归
- 影响范围：
  - `tests/cli/`
  - `tests/ios/`
  - 手工验证脚本或 runbook
- 输出：
  - 回归测试清单
  - 冒烟 runbook
- 完成标准：
  - 真机链路回归通过
  - 至少验证一个 Booted Simulator
  - 至少验证一台 Apple Silicon Mac 的 `app_on_mac`

### P5-07 形成发布与回滚清单

- 目标：让首次发布可控
- 影响范围：
  - `ios_multi_runtime_implementation_plan.md`
  - 发布说明
- 输出：
  - 发布前检查项
  - 回滚动作
- 完成标准：
  - 明确保留 `--runtime` 逃生路径
  - 明确发现误判时的手工绕过方式
  - 明确真机回归时的优先回退点

### P5-08 形成后续 backlog

- 目标：把 MVP 未做项显式沉淀，避免丢需求
- 影响范围：
  - `ios_multi_runtime_design.md`
  - 后续 backlog 文档
- 输出：
  - Phase 2 backlog
- 完成标准：
  - 至少包含 Simulator 高质量 `ui-tree`
  - 至少包含 `app_log`
  - 至少包含多窗口增强
  - 至少包含更精确的坐标换算


## 9. 建议提交边界

建议按下面的提交粒度推进，避免单个提交过大：

1. `P0` 决策冻结与 discovery 模型
2. `P1` runtime 基础骨架与真机迁移
3. `P2` CLI / daemon / 错误码 / 自动选择
4. `P3` Simulator MVP
5. `P4` App on Mac MVP
6. `P5` skill、测试、文档、发布收口


## 10. 阶段退出标准

### P0 退出标准

- discovery 字段冻结
- 选择规则冻结
- 宿主共享层边界冻结

### P1 退出标准

- facade + router 已能稳定跑真机
- 真机行为未回归

### P2 退出标准

- `detect-runtimes` 可用
- `start` 自动选择逻辑可用
- 多候选时能返回结构化错误

### P3 退出标准

- Simulator 可完成 `launch -> screenshot -> tap/type -> wait_for_app` 闭环

### P4 退出标准

- `app_on_mac` 可完成 `launch -> screenshot -> tap/type -> ui_tree` 闭环

### P5 退出标准

- skill 行为与 CLI discovery 契合
- 文档和测试齐备
- 有发布和回滚预案


## 11. 建议下一步

当前最适合直接开工的是：

1. 先完成 `P0-01` 到 `P0-06`
2. 然后立刻进入 `P1-01` 到 `P1-05`
3. 在 `P2-03` 前先把 state 字段和错误码命名彻底冻结

这样后面的 `P3` 和 `P4` 才能并行推进，而不会反复改接口。
