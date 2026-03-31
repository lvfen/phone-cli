# 手机自动化操作规则

## 坐标系统
- 屏幕坐标：左上角 (0,0) 到右下角 (999,999)，CLI 自动转换为绝对像素

## 观察与定位（Android Accessibility-First）

**ui-tree 是 Android 下的主力工具，不是备选。**

1. 进入新页面时，先 `phone-cli ui-tree` 获取节点树
2. 评估节点质量：有效节点（text 非空或 resource_id 有业务含义）≥ 15% → **节点可用**
3. **节点可用时**：
   - 通过 text/content-desc 匹配目标元素
   - 取 bounds 中心点坐标作为点击位置
   - 操作后再次 `ui-tree` 验证页面变化（预期文本出现/消失、页面标题切换）
4. **节点不可用时**（Flutter/游戏/Canvas/WebView，<15% 有效）：回退截图，该页面后续不再尝试 ui-tree
5. **连续 3+ 次低质量** → 当前任务后续直接用截图；切换到新 App 时重新评估
6. `UI_TREE_UNAVAILABLE` → 直接回退截图

## 截图使用场景（补充手段）

仅在以下情况使用截图：
7. 节点质量低，已回退截图模式
8. 需要视觉信息（颜色、图片、动画、布局样式）
9. 截图前先 `phone-cli check-screen`：
   - `all_black`/`all_white`：`phone-cli home` → 等 2s → 重新检查 → 仍异常说明是模拟器问题
   - `normal`：直接用 `screenshot_path` 中的截图
10. ui-tree 有节点但截图深色背景：可能是深色主题，**以节点信息为准**

## 操作前检查
11. `phone-cli get-current-app` 确认是否在目标 app，不是则先 launch

## 异常处理
12. 进入无关页面：`phone-cli back`，无效则 `phone-cli tap 50 50`（左上返回）或 `phone-cli tap 950 50`（右上关闭）
13. 页面未加载：`phone-cli wait-for-app <package> --timeout 6`，超时则 back 重进
14. 网络问题：点击重新加载按钮
15. 找不到目标内容：`phone-cli swipe 500 700 500 300`（向上滑动）查找

## 操作失败恢复
16. 点击不生效：`sleep 1`，调整坐标（±30）重试
17. 滑动不生效：增大距离或反方向尝试
18. 连续 3 次 ui-tree 内容几乎相同（操作未生效）→ 必须改变策略

## App 启动与登录
19. 用 `phone-cli wait-for-app <package> --timeout 10` 等待就绪，非 sleep + 截图
20. `phone-cli app-state --package <package>` 检查 `resumed=true`
21. App 跳转到登录页且需三方登录：模拟器通常无法完成，立即报告用户
22. 用 `phone-cli app-log --package <pkg> --filter lifecycle|crash` 追踪 Activity 跳转

## 安全规则
23. 支付、转账、修改密码 → **立即停止**（禁止级）
24. 发送消息、提交表单、删除内容 → **暂停**，返回 `CONFIRM_REQUIRED: [操作描述]`，等待确认
25. 只操作任务指定的 App，需操作其他 App 时停止报告
26. 需要输入密码/验证码 → 停止等待用户介入

## JSON 输出解析
- `"status": "ok"` 成功，`"error"` 失败
- `DEVICE_DISCONNECTED`：立即停止
- `SCREENSHOT_FAILED`：等 2s 重试，3 次失败检查设备
- `APP_NOT_FOUND`：报告失败
- `UI_TREE_UNAVAILABLE`：回退截图
