# Simple Task Example: Take a Screenshot

**User request:** "帮我截个手机屏幕的图"

**Classification:** Simple (single operation, no dynamic decision)

**Execution:**

```bash
# Step 0: Check CLI
phone-cli status
# → {"status": "ok", "data": {"status": "running", ...}}

# Step 1: Take screenshot
phone-cli screenshot --resize 720
# → {"status": "ok", "data": {"path": "/Users/xxx/.phone-cli/screenshots/default/screenshot_abc123.png", "width": 720, "height": 1560}}
```

Then use Read tool to view the screenshot at the returned path.
