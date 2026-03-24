# phone-cli iOS 多运行时 P0 决策记录

## 1. 范围

本记录对应以下任务：

- `P0-01` 固化 runtime candidate 数据模型
- `P0-02` 固化 runtime selection 规则
- `P0-03` 验证真机 discovery provider
- `P0-04` 验证 Simulator discovery provider
- `P0-05` 验证 `app_on_mac` 宿主支持判定
- `P0-06` 冻结宿主共享层边界


## 2. 本机验证结果

本次验证环境：

- OS：`Darwin`
- 架构：`arm64`
- Python：`3.10.17`

### 2.1 真机 discovery

执行：

```bash
tidevice list --json
```

结果：

- 返回 `[]`
- 结论：当前环境未检测到已连接真机

### 2.2 Simulator discovery

执行：

```bash
xcrun simctl list --json devices
```

筛选结果：

- `booted_count = 0`
- 结论：当前环境存在 CoreSimulator 数据，但没有 Booted Simulator

### 2.3 `app_on_mac` 宿主依赖探测

执行 import 验证：

- `AppKit`: `ok`
- `Quartz`: `ModuleNotFoundError`
- `ApplicationServices`: `ModuleNotFoundError`

结论：

- 当前机器满足 macOS + Apple Silicon 条件
- 但宿主自动化依赖未完整安装
- 因此当前环境 **不应** 认为 `app_on_mac` 可用


## 3. 已冻结的数据模型

### 3.1 `RuntimeCandidate`

用于表示“当前可直接使用”的 runtime 候选。

固定字段：

- `runtime`
- `target_id`
- `label`
- `status`
- `metadata`

说明：

- `status` 当前固定为 `available`
- `metadata` 保留，用于承载 provider 特有信息，避免后续反复改顶层 schema
- 不把失败原因塞进 candidate，而是单独放进 `reasons`

示例：

```json
{
  "runtime": "simulator",
  "target_id": "A1B2-C3D4",
  "label": "iPhone 16 Pro (Booted)",
  "status": "available",
  "metadata": {
    "source": "simctl",
    "runtime_version": "com.apple.CoreSimulator.SimRuntime.iOS-18-2"
  }
}
```

### 3.2 `DiscoveryReason`

用于表示“某个 runtime 当前为什么不可用或无法验证”。

固定字段：

- `runtime`
- `code`
- `message`
- `details`

说明：

- `reasons` 与 `candidates` 并存
- `candidates` 只表示可用项
- `reasons` 用于解释未发现真机、未启动模拟器、依赖缺失、权限不足等情况

### 3.3 `RuntimeDiscoveryResult`

固定输出结构：

- `candidates`
- `auto_selectable`
- `selection_required`
- `reasons`


## 4. 已冻结的选择规则

固定规则如下：

- `0` 个候选：返回 `NO_AVAILABLE_IOS_RUNTIME`
- `1` 个候选：自动选中
- `>1` 个候选：返回 `RUNTIME_SELECTION_REQUIRED`

额外约束：

- CLI 不允许静默默认某个 runtime
- skill 在多候选时必须询问用户
- 用户显式指定 runtime 时，不走自动选择


## 5. provider 级决策

### 5.1 真机 provider

发现方式：

- `tidevice list --json`

结果解释规则：

- 命令缺失：`tidevice_unavailable`
- 命令执行失败：`device_provider_failed`
- 返回空数组：`no_connected_devices`
- 有结果但缺少可用 `udid`：`device_provider_empty`

### 5.2 Simulator provider

发现方式：

- `xcrun simctl list --json devices`

结果解释规则：

- 仅把 `state == Booted` 的 Simulator 视为可用候选
- 已安装但未启动的模拟器不算候选
- 没有 Booted 项时返回 `no_booted_simulators`

### 5.3 `app_on_mac` provider

当前冻结的“可用”定义如下：

1. 运行在 `macOS`
2. 架构为 `Apple Silicon`
3. 必需依赖可导入：
   - `AppKit`
   - `Quartz`
   - `ApplicationServices`
4. Accessibility 权限已授予
5. Screen Recording 权限已授予

重要决策：

- 权限不足时，`app_on_mac` 视为 **候选不可用**
- “宿主支持 `app_on_mac`” 不等于“目标 App 已经启动”
- 因此 discovery 只负责判断 runtime 是否可进入自动化，不负责判断具体 App 是否已就绪


## 6. 宿主共享层边界

P0 冻结后的共享层如下：

- `phone_cli/ios/host/permissions.py`
  - 负责依赖探测、Accessibility 检查、Screen Recording 检查
- `phone_cli/ios/host/windows.py`
  - 负责窗口模型、窗口定位、渲染区域坐标映射
- `phone_cli/ios/host/events.py`
  - 负责点击、双击、长按、拖拽、键盘输入注入接口
- `phone_cli/ios/host/screenshots.py`
  - 负责窗口截图接口
- `phone_cli/ios/host/ax_tree.py`
  - 负责 Accessibility tree 模型与读取接口

冻结原则：

- `simulator` 和 `app_on_mac` 必须复用这层，不各自重复造一套宿主能力
- P0 只冻结接口和职责，不在此阶段实现完整宿主能力


## 7. 对后续阶段的影响

### 对 P1 的影响

- `runtime/discovery.py` 可以直接复用本阶段冻结的数据模型
- `router` 和 `facade` 可以依赖统一 discovery 输出，而不需要再定 schema

### 对 P2 的影响

- `detect-runtimes` 的 JSON 结构已经固定
- `start` 的自动选择规则已经固定
- 错误码命名已经固定

### 对 P3 / P4 的影响

- `simulator` 与 `app_on_mac` 后续都必须接到 `ios/host/*`
- `app_on_mac` 的“可用”判定必须包含权限和依赖，不再简化为“只要是 M 系列 Mac 就算支持”


## 8. 当前未决项

- Screen Recording 权限在不同 macOS 版本上的预检查 API 兼容性，需要在 P3/P4 实装时再做一次实机验证
- Simulator `app_state` 的最小语义需要在 P3 中进一步确认
- `app_on_mac` 的 AX tree 质量需要在真实目标 App 上做实测
