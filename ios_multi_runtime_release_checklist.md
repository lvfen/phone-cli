# phone-cli iOS 多运行时发布与回滚清单

## 1. 发布前检查

### 代码与测试

1. `tests/ios/` 与 `tests/cli/` 单测全部通过
2. `README.md` 已覆盖 `device` / `simulator` / `app-on-mac` 的安装与使用示例
3. `.claude/skills/phone-automation/SKILL.md` 已更新为 runtime-aware 控制流
4. `ios_multi_runtime_smoke_runbook.md` 的三条 runtime smoke 均已执行

### 行为一致性

1. `phone-cli start --device-type ios --runtime device` 保持可用
2. `phone-cli start --device-type ios` 在单候选时自动启动
3. `phone-cli start --device-type ios` 在多候选时返回 `RUNTIME_SELECTION_REQUIRED`
4. `phone-cli launch --bundle-id` / `--app-path` 已验证
5. JSON 输出结构未破坏现有消费者

### 环境与依赖

1. `pip install -e ".[ios]"` 可安装 `tidevice`、`facebook-wda` 和 PyObjC 依赖
2. 在 macOS 上可成功导入 `AppKit`、`Quartz`、`ApplicationServices`
3. `app-on-mac` 环境已验证 Accessibility / Screen Recording 权限提示或报错清晰

## 2. 首发建议

1. 首发阶段保留显式 runtime 逃生路径：
   - `--runtime device`
   - `--runtime simulator`
   - `--runtime app-on-mac`
2. 对外说明优先推荐：
   - 用户已知目标时，显式传 `--runtime`
   - 仅在不确定目标时使用自动发现
3. 将 Simulator 的 `ui-tree` 状态明确标注为 MVP 限制
4. 将 iOS `app-log` 尚未支持写入发布说明

## 3. 发布后观察项

重点观察以下反馈：

1. 自动发现是否误判可用性
2. 多候选场景是否经常让用户困惑
3. `app-on-mac` 的 AX tree 质量是否明显不足
4. Simulator 坐标映射是否在不同缩放下漂移
5. 真机链路是否出现回归

## 4. 回滚优先级

如果出现问题，按下面顺序处理：

### A. 发现误判，但显式 runtime 仍正常

1. 优先让用户临时使用显式 runtime：
   - `phone-cli start --device-type ios --runtime device --device-id <udid>`
   - `phone-cli start --device-type ios --runtime simulator --device-id <udid>`
   - `phone-cli start --device-type ios --runtime app-on-mac`
2. 如有必要，先回退 skill 中的“自动继续”文案，改为总是先确认
3. 保留 backend，不立即回退底层实现

### B. 某个新 runtime 不稳定，但真机正常

1. 暂停推荐对应 runtime
2. 文档中标记为实验能力
3. 允许用户继续通过显式 `--runtime device` 使用真机
4. 如需回滚代码，优先回退对应 backend 与 discovery provider，不动真机链路

### C. 真机链路回归

1. 最高优先级处理
2. 优先回退 iOS facade / router 层，让真机重新走稳定路径
3. 不要先回退 Android / HarmonyOS 代码
4. 回滚后立即重跑真机 smoke

## 5. 手工绕过说明

在发布说明或故障通知中，给出以下临时绕过方式：

1. 跳过自动发现：

```bash
phone-cli start --device-type ios --runtime device --device-id <udid>
```

2. 强制使用 Simulator：

```bash
phone-cli start --device-type ios --runtime simulator --device-id <sim_udid>
```

3. 强制使用 App on Mac：

```bash
phone-cli start --device-type ios --runtime app-on-mac
```

4. 先看 discovery 输出再决定：

```bash
phone-cli detect-runtimes --device-type ios
```

## 6. 发布完成标准

同时满足以下条件后，可认为本次发布完成：

1. 发布前检查项全部通过
2. 三类 runtime 至少各完成一次 smoke
3. 已准备好显式 runtime 的用户绕过说明
4. 已明确回滚优先级和责任人
