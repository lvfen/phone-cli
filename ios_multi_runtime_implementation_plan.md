# phone-cli iOS 多运行时实施计划

## 1. 目标

本计划用于把 `ios_multi_runtime_design.md` 落成可执行开发任务，重点解决以下问题：

- 在 `device_type=ios` 下支持 `device`、`simulator`、`app_on_mac` 三种 runtime
- 在自动化开始前自动发现可用 runtime
- 当仅有一个可用 runtime 时自动选中
- 当存在多个可用 runtime 时，由上层 skill 询问用户选择
- 保证现有真机 `tidevice + WDA` 链路不回归


## 2. 实施原则

- 先重构骨架，再补新 runtime，避免一次性改太多导致真机回归
- 每个阶段结束后都要有可独立验收的输出
- 任何时刻都保留显式指定 runtime 的逃生路径
- 宿主能力尽量做共享层，避免 `simulator` 和 `app_on_mac` 重复实现窗口、权限、输入注入逻辑
- skill 负责和用户交互，`phone-cli` 负责发现与执行


## 3. 里程碑总览

| 里程碑 | 目标 | 主要输出 | 依赖 |
|---|---|---|---|
| Phase 0 | 技术验证与边界冻结 | discovery 结果模型、宿主权限预检查方案、共享模块边界 | 无 |
| Phase 1 | iOS runtime 基础骨架 | `base.py`、`router.py`、`discovery.py`、`device_backend.py` | Phase 0 |
| Phase 2 | CLI / daemon / 命令路由改造 | `start`/`detect-runtimes`/`launch` 参数扩展，state 扩展，错误码扩展 | Phase 1 |
| Phase 3 | `ios-simulator` MVP | `devices`、`launch`、`app-state`、`wait-for-app`、`screenshot`、`tap/swipe/type`、`check-screen` | Phase 2 |
| Phase 4 | `ios-app-on-mac` MVP | `launch`、`get-current-app`、`app-state`、`wait-for-app`、`screenshot`、`tap/swipe/type`、`ui-tree` | Phase 2 |
| Phase 5 | skill 联动与稳定性收口 | `phone-automation` skill 更新、测试补齐、发布回归 | Phase 3、Phase 4 |


## 4. 模块拆分建议

建议在现有设计上再补一层宿主共享能力，避免后续重复代码：

```text
phone_cli/
├── cli/
├── ios/
│   ├── __init__.py
│   ├── runtime/
│   │   ├── base.py
│   │   ├── router.py
│   │   ├── discovery.py
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
```

建议职责如下：

- `runtime/discovery.py`：发现真机、Booted Simulator、`app_on_mac` 宿主候选
- `runtime/router.py`：根据 daemon state 选择 backend
- `ios/host/permissions.py`：检测 Accessibility / Screen Recording 权限
- `ios/host/windows.py`：查找窗口、定位渲染区域、记录 `window_id`
- `ios/host/events.py`：统一鼠标点击、拖拽、键盘输入注入
- `ios/host/screenshots.py`：窗口级截图
- `ios/host/ax_tree.py`：读取 macOS Accessibility tree


## 5. Phase 0：技术验证与边界冻结

### 5.1 目标

- 冻结 runtime discovery 的候选结构
- 明确宿主共享层的最小边界
- 提前验证最容易卡住的权限和 API 能力

### 5.2 任务

- 验证 `tidevice list --json` 可稳定列出真机
- 验证 `xcrun simctl list --json devices` 可稳定识别 Booted Simulator
- 在 Apple Silicon Mac 上验证 `pyobjc` 依赖可正常导入
- 验证 Accessibility / Screen Recording 的检测方式
- 确认 `app_on_mac` 的“可用”只表示宿主能力满足，不表示目标 App 一定已启动
- 统一 discovery 输出结构，确定 `runtime`、`target_id`、`label`、`status` 字段

### 5.3 交付物

- 一版稳定的 `RuntimeCandidate` 数据模型
- 一版权限预检查策略说明
- 一版宿主共享层文件结构说明

### 5.4 验收标准

- 在一台 M 系列 Mac 上能稳定输出 discovery 候选结果
- 能区分“没有真机”“没有 Booted Simulator”“宿主不支持 `app_on_mac`”
- 能明确说明哪些场景该报错，哪些场景只是候选为空


## 6. Phase 1：iOS runtime 基础骨架

### 6.1 目标

- 建立统一 backend 接口
- 把当前真机能力迁移为 `device_backend`
- 把 runtime discovery 和 runtime router 接好

### 6.2 任务

- 新增 `phone_cli/ios/runtime/base.py`
- 新增 `phone_cli/ios/runtime/router.py`
- 新增 `phone_cli/ios/runtime/discovery.py`
- 新增 `phone_cli/ios/runtime/device_backend.py`
- 将现有 `phone_cli/ios/connection.py`、`device.py`、`input.py`、`screenshot.py` 封装进真机 backend
- 调整 `phone_cli/ios/__init__.py`，从“直接导出具体函数”改成“统一 facade + router 分发”
- 补充 runtime capability 返回结构

### 6.3 关键决策

- `device_backend` 第一阶段不改行为，只做搬运和封装
- router 只根据 daemon state 工作，不自己做 discovery
- discovery 单独暴露，供 `start` 和 skill 调用

### 6.4 验收标准

- 显式指定 `--runtime device` 时，现有真机能力与改造前行为一致
- `phone_cli.ios` 层不再硬编码只依赖 WDA
- 可以通过 router 返回正确 backend，并拿到 capability 信息


## 7. Phase 2：CLI / daemon / 命令路由改造

### 7.1 目标

- 把 runtime 维度接入 CLI 和 daemon
- 打通“自动发现 -> 自动选择 / 询问用户 -> 启动”的控制流
- 把 iOS 仍然 ADB-only 的命令改造成 backend 分发

### 7.2 任务

- 修改 `phone_cli/cli/main.py`
- 为 `start` 增加 `--runtime`
- 为 `launch` 增加 `--bundle-id` 和 `--app-path`
- 新增 `detect-runtimes` 命令
- 修改 `phone_cli/cli/daemon.py`
- state 增加 `ios_runtime`、`target_id`、`bundle_id`、`window_id`、`capabilities`
- `start()` 在 iOS 且未显式指定 runtime 时复用 discovery
- heartbeat 改成 runtime-aware，避免 `app_on_mac` 误判为 disconnected
- 修改 `phone_cli/cli/commands.py`
- `devices`、`device-info` 按 runtime 返回更多字段
- `launch` 支持 `bundle_id > app_path > app_name`
- `app_state`、`wait_for_app`、`check_screen` 改为由 backend 自己决定实现
- `ui_tree` 改为 iOS backend 自己负责，而不是命令层内嵌 `WDA source`
- 修改 `phone_cli/cli/output.py`
- 增加 `NO_AVAILABLE_IOS_RUNTIME`
- 增加 `RUNTIME_SELECTION_REQUIRED`
- 增加 `RUNTIME_NOT_SUPPORTED`
- 增加 `TARGET_NOT_SELECTED`
- 修改 `setup.py`
- 为宿主自动化增加 `pyobjc` 依赖组

### 7.3 推荐行为

- `phone-cli start --device-type ios`：
  - 0 个候选：返回 `NO_AVAILABLE_IOS_RUNTIME`
  - 1 个候选：自动选择并写入 state
  - 多个候选：返回 `RUNTIME_SELECTION_REQUIRED`
- `phone-cli start --device-type ios --runtime <x>`：
  - 跳过自动选择
  - 仅校验该 runtime 是否可用

### 7.4 验收标准

- `detect-runtimes` 能返回稳定 JSON
- `device-info` 能返回 `ios_runtime`、`target_id`、`capabilities`
- `launch` 新参数不会破坏现有 `app_name` 用法
- 当存在多个候选时，CLI 不会偷偷默认选一个 runtime


## 8. Phase 3：`ios-simulator` MVP

### 8.1 目标

- 在不改业务工程的前提下，打通 Simulator 的基础自动化闭环

### 8.2 MVP 范围

- `devices`
- `launch`
- `app-state`
- `wait-for-app`
- `screenshot`
- `tap`
- `swipe`
- `type`
- `check-screen`

### 8.3 任务

- `simulator_backend.list_targets()` 基于 `simctl list --json devices`
- `launch` 支持 `simctl launch`
- 如后续需要安装本地包，再补 `simctl install`
- `screenshot` 使用 `simctl io <udid> screenshot`
- 引入宿主共享层，查找 Simulator 窗口和渲染区域
- 统一 `0-999` 坐标到渲染区域像素坐标映射
- 使用宿主事件注入完成 `tap/swipe/type`
- `check-screen` 先复用截图结果实现
- `ui-tree` 在 MVP 阶段明确返回 `UI_TREE_UNAVAILABLE`

### 8.4 技术风险

- 渲染区域识别可能受窗口缩放、刘海、安全区影响
- `app-state` 的精确语义可能难以与真机完全一致

### 8.5 风险应对

- Phase 3 只先支持前台单窗口 Simulator
- `app-state` 先提供 `running` / `foreground` 最小语义
- 多窗口和高精度 `ui-tree` 放到后续阶段

### 8.6 验收标准

- 能在 Booted Simulator 中启动目标 App
- 能截图、点击、滑动、输入
- `wait-for-app` 能用于替代固定 `sleep`
- 截图和点击坐标能稳定命中前台窗口内容区域


## 9. Phase 4：`ios-app-on-mac` MVP

### 9.1 目标

- 在 Apple Silicon Mac 上支持基于宿主窗口的 `iOS App on Mac` 自动化

### 9.2 MVP 范围

- `launch`
- `get-current-app`
- `app-state`
- `wait-for-app`
- `screenshot`
- `tap`
- `swipe`
- `type`
- `ui-tree`

### 9.3 任务

- `app_on_mac_backend.launch_app()` 支持 `open -b <bundle_id>` 和 `open <app_path>`
- 基于 `NSWorkspace` 查找前台应用和 bundle id
- 基于 Quartz 获取窗口列表、窗口 bounds、窗口截图
- 基于 `CGEvent` 做点击、拖拽、键盘输入
- 基于 AX tree 读取窗口元素结构
- 将 AX tree 映射为现有 `ui-tree` 兼容输出
- 在 state 中记录最近一次绑定的 `window_id`

### 9.4 技术风险

- UIKit / Flutter / 自绘界面在 Mac 上暴露的 AX 信息可能很少
- 多窗口场景下，窗口绑定可能漂移

### 9.5 风险应对

- 优先保证截图 + 坐标流可用
- `ui-tree` 允许质量不高，但结构必须稳定
- 默认绑定最近一次 `launch` 命中的窗口

### 9.6 验收标准

- 可以通过 `bundle_id` 或 `app_path` 启动目标 App
- 能截图、点击、输入
- 能识别当前前台应用
- `ui-tree` 至少能返回根节点和部分基础字段


## 10. Phase 5：skill 联动与稳定性收口

### 10.1 目标

- 让上层 skill 能正确利用 runtime discovery
- 补齐自动化前置决策和回归验证

### 10.2 任务

- 更新 `.claude/skills/phone-automation/SKILL.md`
- iOS 任务开始前先调用 `phone-cli detect-runtimes --device-type ios`
- 单候选时自动选择
- 多候选时询问用户
- 用户已明确指定 runtime 时不再重复询问
- 保持 Android / HarmonyOS 逻辑不受影响
- 为 skill 补手工验证脚本
- 补充文档示例：
  - 真机
  - Simulator
  - `app_on_mac`
  - 多候选交互

### 10.3 验收标准

- 用户未指定 runtime 且只有一个候选时，自动化任务可直接继续
- 用户未指定 runtime 且有多个候选时，skill 一定会先询问
- 用户明确指定 runtime 时，skill 不会额外打断


## 11. 测试计划

### 11.1 单元测试

- `tests/cli/test_commands.py`
  - runtime discovery 结果分发
  - `start` 自动选择逻辑
  - `launch` 参数优先级
  - 错误码返回
- `tests/cli/test_daemon.py`
  - state 新字段持久化
  - runtime-aware heartbeat
- 新增 `tests/ios/test_runtime_router.py`
- 新增 `tests/ios/test_runtime_discovery.py`
- 新增 `tests/ios/test_capabilities.py`

### 11.2 集成测试

- 真机环境
  - `start --runtime device`
  - `launch`
  - `screenshot`
  - `tap`
  - `type`
- Simulator 环境
  - `detect-runtimes`
  - `start --runtime simulator`
  - `launch`
  - `wait-for-app`
  - `screenshot`
  - `tap`
- Apple Silicon Mac 环境
  - `detect-runtimes`
  - `start --runtime app-on-mac`
  - `launch --bundle-id`
  - `launch --app-path`
  - `get-current-app`
  - `ui-tree`

### 11.3 回归重点

- `phone-cli start --device-type ios --runtime device` 必须持续可用
- 原有真机 `launch`、`screenshot`、`tap`、`type` 结果不变
- JSON 输出结构保持兼容
- 多 runtime 引入后，Android / HarmonyOS 命令行为不受影响


## 12. 发布与回滚策略

- 首发阶段始终保留显式 runtime 参数
- 一旦 discovery 出现误判，用户仍可通过 `--runtime device|simulator|app-on-mac` 强制绕过自动选择
- 若宿主能力不稳定，可只发布 Phase 1 + Phase 2，把新 runtime backend 先保留为实验能力
- 任何阶段如发现真机回归，优先回退 router facade，不回退底层真机实现


## 13. 粗估工期

以下估时按 1 名熟悉仓库的工程师全职投入估算：

| 阶段 | 估时 |
|---|---|
| Phase 0 | 0.5 - 1 天 |
| Phase 1 | 1 - 1.5 天 |
| Phase 2 | 1 - 1.5 天 |
| Phase 3 | 2 - 3 天 |
| Phase 4 | 2 - 3 天 |
| Phase 5 | 1 天 |
| 合计 | 7.5 - 11 天 |


## 14. 建议执行顺序

1. 先完成 Phase 0，冻结 discovery 结果模型和权限检查方式
2. 再完成 Phase 1，把真机实现迁入 `device_backend`
3. 接着完成 Phase 2，让 CLI、daemon、router、错误码全部打通
4. 然后优先做 Phase 3，因为 Simulator 更容易成为日常调试主路径
5. 再做 Phase 4，复用宿主共享层能力
6. 最后完成 Phase 5，把 skill 和测试收口


## 15. 下一步建议

实施计划确定后，建议继续拆成开发任务清单，至少细化为：

- P0 技术验证任务
- P1 基础骨架任务
- P2 CLI / daemon 任务
- P3 Simulator 任务
- P4 App on Mac 任务
- P5 skill / 测试 / 文档任务

这样就可以直接进入逐项开发。
