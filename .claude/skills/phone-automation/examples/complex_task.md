# Complex Task Example: Search and Filter in App

**User request:** "在掌上穿越火线App中查看我的战绩"

**Classification:** Complex (multi-step, needs screen content analysis)

**Brainstorming output:**

```yaml
task: "在掌上穿越火线中查看我的战绩"
device_type: adb
steps:
  - id: 1
    action: "启动掌上穿越火线 App"
    success_criteria: "屏幕显示掌上穿越火线首页"
  - id: 2
    action: "点击底部'我的'或个人中心Tab"
    success_criteria: "进入个人页面"
  - id: 3
    action: "找到并点击'战绩'入口"
    success_criteria: "显示战绩页面"
  - id: 4
    action: "截图记录战绩信息"
    success_criteria: "截图保存成功"
max_retries_per_step: 5
total_max_steps: 30
```

**Subagent dispatch:**

The main session launches a Haiku subagent with the steps injected into the subagent.md template, along with rules_zh.md content.

**Result:**

```
## 执行结果
- 步骤 1: 成功 - 掌上穿越火线已启动，显示首页
- 步骤 2: 成功 - 已进入个人中心页面
- 步骤 3: 成功 - 找到战绩入口并点击
- 步骤 4: 成功 - 截图已保存到 /Users/xxx/.phone-cli/screenshots/task_abc/step_4.png
总结: 全部步骤执行成功
```
