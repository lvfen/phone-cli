# 手机自动化操作规则

## 坐标系统
- 屏幕坐标系：左上角 (0,0) 到右下角 (999,999)
- 所有 tap/swipe 命令使用此相对坐标，CLI 自动转换为绝对像素

## 观察策略（核心原则）

**优先使用 `phone-cli ui-tree` 获取节点信息，但必须评估节点质量，低质量时自动降级为截图。**

### 节点质量判断

拿到 ui-tree 后，快速评估节点是否有用：
- **有效节点**：text 非空，或 resource_id 含业务含义（非框架级如 `action_bar_root`、`content`）
- **空壳节点**：text 为空 + resource_id 为空或仅框架级，class 多为 `android.view.View`/`android.widget.FrameLayout`

**判断规则**：
- 有效节点占比 ≥ 15% → **节点可用**，用 ui-tree 定位和验证
- 有效节点占比 < 15% → **节点不可用**（Flutter/游戏/WebView/Canvas 页面），降级为截图
- 一旦判定某页面节点不可用，该页面后续操作**全部使用截图**，不再反复尝试 ui-tree

### 观察方式选择

| 场景 | 方法 | 说明 |
|------|------|------|
| 节点质量高：定位按钮/文本/输入框 | `phone-cli ui-tree` | 节点有 text、bounds、clickable 等属性 |
| 节点质量高：确认页面切换 | `phone-cli ui-tree` | 对比节点结构变化 |
| 确认 App 是否在前台 | `phone-cli app-state` | 无需截图也无需 ui-tree |
| 节点质量低（Flutter/游戏/Canvas/WebView） | `phone-cli screenshot` | 空壳节点无法定位元素 |
| ui-tree 返回 `UI_TREE_UNAVAILABLE` | `phone-cli screenshot` | 降级为截图 |
| 需要判断颜色/图片/视觉样式 | `phone-cli screenshot` | 节点无法表达视觉信息 |

## 操作前检查
1. 操作前先运行 `phone-cli get-current-app` 检查当前 app 是否是目标 app，不是则先 `phone-cli launch <app>`
2. 每步操作后优先用 `phone-cli ui-tree` 确认结果（节点质量高时），辅以 `phone-cli app-state` 确认 App 在前台；节点质量低时直接用截图确认

## 截图验证（仅在需要时）
3. 需要截图时先运行 `phone-cli check-screen` 检查屏幕是否健康：
   - 如果 `screen_state` 为 `all_black` 或 `all_white`：
     - 先按 Home 键 (`phone-cli home`)，等 2 秒后重新 `phone-cli check-screen`
     - 如果系统桌面也异常 → 是模拟器渲染问题，不是 App 问题
     - 报告模拟器截图异常，建议用户换真机或重启模拟器
   - 如果 `screen_state` 为 `normal`，可直接使用 `screenshot_path` 中的截图，无需额外截图
4. 如果 ui-tree 显示有节点但截图看起来是黑色/深色背景：
   - 说明 App 使用深色主题，界面正常，以节点信息为准
   - 运行 `phone-cli app-state --package <package>` 确认 Activity 是否在前台
   - 如果 `resumed=false, stopped=true`，说明 App 进入了后台（可能是调起登录 SDK 等外部操作导致的）

## 异常处理
5. 进入无关页面时先 `phone-cli back`，无效则 `phone-cli tap 50 50`（左上角返回键）或 `phone-cli tap 950 50`（右上角关闭）
6. 页面未加载时最多等待 3 次（每次 `sleep 2`），否则 `phone-cli back` 重新进入。也可使用 `phone-cli wait-for-app <package> --timeout 6` 替代手动轮询
7. 页面显示网络问题时点击重新加载按钮
8. 找不到目标内容时尝试 `phone-cli swipe 500 700 500 300`（向上滑动）查找

## 操作失败恢复
9. 点击不生效时：先 `sleep 1` 等待，再调整坐标（偏移 ±30）重试
10. 滑动不生效时：增大滑动距离或反方向尝试
11. 如果连续 3 次 ui-tree 内容几乎相同（操作未生效），必须改变策略

## App 启动与登录
12. 启动 App 后使用 `phone-cli wait-for-app <package> --timeout 10` 等待就绪，而非 sleep + 截图
13. 启动后用 `phone-cli app-state --package <package>` 检查 Activity 状态：
    ```bash
    phone-cli app-state --package <package>
    # 检查 resumed=true 表示在前台
    ```
14. 如果 App 跳转到了登录页（LoginActivity 等），且需要 QQ/微信等三方登录：
    - **模拟器上通常无法完成三方登录**（没有安装 QQ/微信）
    - 立即报告给用户，建议在真机上测试
    - 不要反复尝试点击登录按钮
15. 通过 `phone-cli app-log --package <package> --filter lifecycle` 追踪 Activity 跳转路径，而非猜测。如怀疑崩溃，用 `phone-cli app-log --package <package> --filter crash`

## 元素定位
16. 首次进入页面时运行 `phone-cli ui-tree`，评估节点质量（有效节点占比是否 ≥ 15%）
17. **节点质量高**：通过 text/content-desc/bounds 定位目标元素，用 bounds 坐标计算点击位置（取中心点）
18. **节点质量低**（Flutter/游戏/Canvas/WebView）：直接截图，通过视觉判断元素位置给出坐标，后续该页面不再尝试 ui-tree
19. 如果 `phone-cli ui-tree` 返回 `UI_TREE_UNAVAILABLE`，改用 `adb shell uiautomator dump` 直接获取

## 安全规则
20. 遇到支付、转账、修改密码等操作，立即停止并报告（禁止级）
21. 遇到发送消息、提交表单、删除内容等操作，暂停执行并返回确认请求（确认级）：
    - 返回格式：`CONFIRM_REQUIRED: [操作描述]`
    - 等待主会话确认后才能继续
22. 只操作任务计划中指定的 App，发现需要操作其他 App 时停止并报告
23. 遇到需要输入密码、验证码的界面，停止并报告等待用户介入

## JSON 输出解析
- 所有 phone-cli 命令输出 JSON
- 检查 `"status"` 字段：`"ok"` 表示成功，`"error"` 表示失败
- 失败时读取 `"error_code"` 和 `"error_msg"` 决定下一步
- `DEVICE_DISCONNECTED`：立即停止执行
- `SCREENSHOT_FAILED`：等待 2 秒重试，连续 3 次失败则检查设备状态
- `APP_NOT_FOUND`：报告失败
- `UI_TREE_UNAVAILABLE`：改用 `adb shell uiautomator dump` 替代
