# phone-cli iOS 多运行时后续 Backlog

## 1. 目的

记录当前 MVP 明确暂不处理、但后续很可能继续推进的能力，避免需求在发布后丢失。

## 2. 高优先级

### Simulator 高质量 `ui-tree`

现状：

- `ios-simulator` 在 MVP 中明确返回 `UI_TREE_UNAVAILABLE`

后续方向：

1. 评估基于 XCTest / accessibility dump 的可行路径
2. 给出与真机 / `app-on-mac` 更一致的 `ui-tree` 输出
3. 为 WebView / Flutter / Canvas 页面定义降级策略

### iOS `app-log`

现状：

- Android 已有 `app-log`
- iOS 三种 runtime 尚无统一日志能力

后续方向：

1. 真机：评估 `idevicesyslog` / `tidevice syslog`
2. Simulator：评估 `log stream` / `simctl spawn log`
3. `app-on-mac`：评估 `log show` / `log stream` 按 bundle 过滤
4. 对外统一为 `phone-cli app-log` 的 runtime-aware 语义

### 多窗口增强

现状：

- `app-on-mac` 默认绑定最近一次 `launch` 命中的窗口
- 多窗口 App 存在窗口漂移风险

后续方向：

1. 增加窗口列表与窗口切换能力
2. 在 daemon state 中保存更稳定的窗口标识
3. 为窗口消失 / 重建设计自动重新绑定策略

### 更精确的坐标换算

现状：

- Simulator 与 `app-on-mac` 使用宿主窗口映射
- 在窗口缩放、安全区、刘海、标题栏变化下仍可能出现偏移

后续方向：

1. 细化渲染区域识别
2. 引入安全区 / notch / 缩放因子修正
3. 为不同窗口尺寸建立回归样本

## 3. 中优先级

### Runtime 级能力矩阵对外暴露

后续方向：

1. 让 `device-info` 或 `detect-runtimes` 更直接返回 capability 差异
2. 让 skill 可以在复杂任务前更早做降级判断

### `app-on-mac` AX tree 质量提升

后续方向：

1. 增加 role / title / value 的归一化
2. 改进树裁剪与扁平化策略
3. 对 UIKit、Flutter、自绘视图分别定义兼容行为

### 更完整的本地调试支持

后续方向：

1. Simulator 的 `.app` 安装 / 启动体验再收口
2. 为 `app-on-mac` 的 `.app` 路径启动补更多错误提示
3. 对 bundle id 与 `.app` path 的优先级冲突给出更清晰提示

## 4. 低优先级

### 自动恢复与自愈

后续方向：

1. `app-on-mac` 窗口丢失后的自动重绑
2. Simulator 目标重启后的自动重连
3. 更细粒度的 host 权限缺失修复建议

### 更完整的 E2E 覆盖

后续方向：

1. 增加真机 / Simulator / `app-on-mac` 三类环境的自动化 smoke
2. 为 skill 增加更系统的人工验收场景
3. 把关键回归路径固化到 CI 可执行脚本

## 5. 暂不做的事项

以下内容在本次 MVP 不进入实现范围：

1. Simulator 完整 `ui-tree`
2. iOS 统一 `app-log`
3. `app-on-mac` 高级多窗口管理
4. 跨 runtime 完全一致的 `app-state` 细粒度语义
5. 非 macOS 主机上的 iOS 自动化支持
