# Emulator Task Example: Install and Launch App on Emulator

**User request:** "在模拟器上安装并启动刚编译的 APK，验证是否正常"

**Classification:** Medium (sequential steps, but needs diagnostic logic)

**Execution flow:**

```bash
# Step 0: Check CLI status
phone-cli status
# → If disconnected or stopped, restart:
phone-cli stop && sleep 1 && phone-cli start --device-type adb

# Step 1: Check for connected devices
phone-cli devices
# → {"status": "ok", "data": {"devices": []}}
# No devices — need to start emulator

# Step 2: Start emulator (MUST cd to SDK dir first)
cd $ANDROID_HOME/emulator && ./emulator -avd Pixel_7_Pro -no-audio -no-boot-anim &
# ⚠️ NEVER use -no-window — screencap returns all-black images
# Wait for boot completion
adb wait-for-device
adb shell 'while [[ -z $(getprop sys.boot_completed) ]]; do sleep 2; done'

# Step 3: Set device
phone-cli set-device emulator-5554

# Step 4: CRITICAL — Verify screenshot works BEFORE app testing
phone-cli screenshot --resize 720
# → View the image with Read tool
# → If all black: emulator rendering broken, try cold boot:
#    kill -9 <emu_pid> && cd $ANDROID_HOME/emulator && ./emulator -avd Pixel_7_Pro -no-snapshot-load -no-audio -no-boot-anim &
# → If shows home screen: proceed ✓

# Step 5: Install APK
adb install -r /path/to/your.apk
# → Check output for "Success"

# Step 6: Find package name and launcher activity
aapt2 dump badging /path/to/your.apk | grep -E "package:|launchable-activity:"
# → package: name='com.example.app'
# → launchable-activity: name='com.example.app.MainActivity'

# Step 7: Launch app
adb shell am start -n com.example.app/.MainActivity
# Wait for initialization
sleep 8

# Step 8: Verify app state (don't trust screenshot alone!)
adb shell dumpsys activity top | grep -E "ACTIVITY|mResumed"
# → If mResumed=true: app is in foreground ✓
# → If mResumed=false, mStopped=true: app went to background (login redirect?)

# Step 9: Check logcat if something seems wrong
adb logcat -d --pid=$(adb shell pidof com.example.app) | grep -iE "activity|login|exception|crash" | tail -20

# Step 10: Take screenshot
phone-cli screenshot --resize 720
```

**Common pitfall — the "black screen" trap:**

In one real session, every screenshot returned all-black. After extensive debugging:
- The app was actually running fine (logcat showed normal Activity lifecycle)
- The app redirected to LoginActivity (needs QQ login, unavailable on emulator)
- **Root cause: emulator was started with `-no-window`, causing `adb screencap` to fail**
- Even the system home screen was black — this was the key clue that the emulator, not the app, was broken

**Lesson:** Always verify system home screen screenshot works before debugging app issues.
