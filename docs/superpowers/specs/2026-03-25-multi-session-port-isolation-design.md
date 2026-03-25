# 多会话端口隔离：中央守护进程设计

## 问题

phone-cli 目前为每个平台分配固定端口（iOS WDA: 8100，ADB TCP: 5555，HDC TCP: 5555）。当多个 AI 会话同时操作设备时，端口冲突和操作竞争使并行自动化无法实现。

## 决策

用一个全局守护进程替代按设备类型分实例的守护进程架构。全局守护进程统一管理所有设备连接、端口分配和会话生命周期。AI 会话作为无状态客户端，通过守护进程申请/释放设备。

## 架构

```
AI 会话 1 ──┐
AI 会话 2 ──┤──▶ 中央守护进程 ──▶ 设备 A (iOS, 端口 8100)
AI 会话 3 ──┘    (单进程)        设备 B (iOS, 端口 8101)
                                 设备 C (Android, ADB server :5038)
```

### 为什么选择中央守护进程

- 所有设备操作在同一进程内执行：每设备串行执行，无需加锁。
- 端口分配在进程内部完成：bind 检测即可，无需文件锁。
- 超时管理集中化：一个 watchdog 线程，确定性清理。
- 比分布式协调（文件锁、PID 验证、残留清理）更简单。

## 模块布局

```
phone_cli/
├── daemon/
│   ├── server.py        # 守护进程主循环，Unix socket 服务器，生命周期
│   ├── session.py       # SessionManager：会话创建/激活/过期/释放
│   ├── device.py        # DeviceManager：连接/断开/执行，端口分配
│   ├── watchdog.py      # TimeoutWatchdog：空闲会话超时回收
│   └── protocol.py      # IPC 协议定义（请求/响应格式，命令分发）
├── client.py            # PhoneClient：AI 会话使用的轻量客户端
├── config/
│   └── ports.py         # 端口范围常量，bind 检测工具函数
├── adb/connection.py    # 不变，被 DeviceManager 内部调用
├── hdc/connection.py    # 不变，被 DeviceManager 内部调用
└── ios/connection.py    # 不变，被 DeviceManager 内部调用
```

## 端口分配

### 端口范围

| 平台 | 用途 | 默认端口 | 动态范围 |
|------|------|----------|----------|
| iOS WDA | wdaproxy | 8100 | 8100-8199 |
| ADB Server | adb -P | 5037 | 5037-5099 |
| HDC Server | hdc server | 5100 | 5100-5199 |

### 分配算法

在守护进程内部执行（单线程分配，无竞态条件）：

```
for port in range(start, end):
    1. bind 检测：socket.bind(('127.0.0.1', port))
       - 失败 → 端口被外部进程占用 → 跳过
    2. 检查内部注册表：端口是否已分配给其他设备？
       - 是 → 跳过
    3. 分配端口，记录到注册表 → 返回端口

所有端口耗尽 → 抛出 PortExhaustedError
```

优先尝试默认端口以保持向后兼容（单会话场景下仍然拿到 8100/5037）。

### Bind 检测实现

```python
def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False
```

bind 检测能捕获所有被占用状态（包括 TIME_WAIT），而 connect 检测只能发现正在监听的端口。

## 会话生命周期

### 状态

```
acquire() 调用
    │
    ├── 设备空闲 ──▶ ACTIVE（活跃）
    │
    └── 设备被占 ──▶ QUEUED（排队）──(前一会话释放)──▶ ACTIVE
                                                          │
                                        ┌─────────────────┤
                                        ▼                 ▼
                                    RELEASED          EXPIRED
                                 (AI 主动释放)      (超时过期)
```

### 会话数据

```python
@dataclass
class Session:
    session_id: str         # UUID
    device_id: str          # 目标设备标识
    device_type: str        # "ios" | "adb" | "hdc"
    status: str             # "active" | "queued" | "released" | "expired"
    acquired_at: float      # 会话变为 active 的时间
    last_active_at: float   # 每次 operate/heartbeat 时更新
    timeout: float          # 空闲超时秒数（默认 300）
    created_at: float       # acquire 调用的时间
```

### 超时机制

- 默认：300 秒（5 分钟）无 operate/heartbeat 调用则过期。
- 每个会话可通过 `acquire(timeout=N)` 自定义超时时间。
- Watchdog 线程每 10 秒检查一次。
- 过期时：标记会话为 expired，断开设备连接，释放端口，激活队列中的下一个会话。

## IPC 协议

通过 Unix socket `~/.phone-cli/phone-cli.sock` 通信，JSON 换行分隔。

### 命令

#### acquire

请求设备连接。

```json
{
  "cmd": "acquire",
  "args": {
    "device_id": "emulator-5554",
    "device_type": "adb",
    "timeout": 300
  }
}
```

响应（成功，设备可用）：
```json
{
  "ok": true,
  "session_id": "uuid-xxx",
  "status": "active",
  "port": 5037,
  "device_id": "emulator-5554"
}
```

响应（设备被占，排队中）：
```json
{
  "ok": true,
  "session_id": "uuid-yyy",
  "status": "queued",
  "queue_position": 1
}
```

#### operate

执行设备操作。每次调用会重置空闲超时计时器。

```json
{
  "cmd": "operate",
  "args": {
    "session_id": "uuid-xxx",
    "action": "tap",
    "x": 100,
    "y": 200
  }
}
```

响应：
```json
{"ok": true, "result": {}}
```

错误（会话已过期）：
```json
{"ok": false, "error": "session_expired", "msg": "会话空闲 300 秒后已超时"}
```

#### release

主动释放设备。

```json
{"cmd": "release", "args": {"session_id": "uuid-xxx"}}
```

#### heartbeat

保持会话活跃（不执行操作）。

```json
{"cmd": "heartbeat", "args": {"session_id": "uuid-xxx"}}
```

#### status

查询守护进程状态。

```json
{"cmd": "status", "args": {}}
```

响应：
```json
{
  "ok": true,
  "sessions": [
    {"session_id": "uuid-xxx", "device_id": "emulator-5554", "status": "active", "idle_seconds": 42}
  ],
  "devices": [
    {"device_id": "emulator-5554", "device_type": "adb", "port": 5037, "status": "occupied"}
  ]
}
```

#### list_devices

发现可用设备。

```json
{"cmd": "list_devices", "args": {"device_type": "ios"}}
```

## 设备管理器

### 各平台连接策略

**iOS：**
- 从 8100-8199 范围分配 WDA 端口。
- 启动 `tidevice -u <udid> wdaproxy --port <分配的端口>` 子进程。
- 创建 `wda.Client(f"http://localhost:{分配的端口}")`。
- 断开时：终止 wdaproxy 子进程，释放端口。

**ADB：**
- 从 5037-5099 范围分配 ADB server 端口。
- 启动独立的 ADB server：`adb -P <分配的端口> start-server`。
- 所有设备命令通过：`adb -P <分配的端口> -s <device_id> ...` 执行。
- 断开时：`adb -P <分配的端口> kill-server`，释放端口。

**HDC：**
- 从 5100-5199 范围分配 HDC server 端口。
- 在分配的端口上启动独立的 HDC server。
- 所有设备命令通过该 server 执行。
- 断开时：终止 server，释放端口。

## 客户端 API

```python
class PhoneClient:
    """AI 会话通过此客户端与守护进程通信。"""

    def __init__(self, socket_path="~/.phone-cli/phone-cli.sock"):
        self._socket_path = os.path.expanduser(socket_path)
        self._session_id: str | None = None

    def acquire(self, device_id: str, device_type: str = "auto",
                timeout: float = 300, wait: bool = True) -> dict:
        """申请设备连接。成功后内部保存 session_id。"""

    def tap(self, x: int, y: int) -> dict:
        """点击指定坐标。"""

    def swipe(self, x1, y1, x2, y2, duration=300) -> dict:
        """滑动手势。"""

    def screenshot(self, path: str | None = None) -> dict:
        """截图。"""

    def release(self) -> None:
        """释放设备，清除会话。"""

    def heartbeat(self) -> None:
        """保持活跃（不执行操作）。"""
```

所有 `tap`/`swipe`/`screenshot` 等方法内部调用 `_operate(action, **args)`，每次操作自动刷新超时计时器。

## 从现有架构迁移

### 变化项

| 迁移前 | 迁移后 |
|--------|--------|
| 按设备类型分实例的守护进程 (adb/hdc/ios) | 单一全局守护进程 |
| `~/.phone-cli/instances/{adb,hdc,ios}/` | `~/.phone-cli/`（单一主目录） |
| 多个 pid/socket/state 文件 | 一个 pid、一个 socket、一个 state |
| 设备操作在 CLI 进程中执行 | 设备操作在守护进程中执行 |
| 无会话概念 | 显式的 acquire/operate/release |
| 无超时 | 可配置的空闲超时（默认 300 秒） |
| 硬编码端口 | 动态端口分配 |

### 保留项

- `phone_cli/adb/connection.py` — ADBConnection 类，被 DeviceManager 内部使用。
- `phone_cli/hdc/connection.py` — HDCConnection 类，被 DeviceManager 内部使用。
- `phone_cli/ios/connection.py` — WDAConnection 类，被 DeviceManager 内部使用。
- CLI 命令（`phone-cli start/stop/status`）— 更新为与新守护进程通信。
- Unix socket IPC 模式 — 相同机制，增强协议。

### 向后兼容

- 单 AI 会话：申请设备后获得默认端口（8100/5037），行为与之前完全一致。
- 现有 CLI 命令继续工作。
- `phone-cli start --device-type ios` 启动全局守护进程并自动申请指定设备类型。

## 守护进程启动与恢复

### 启动流程

1. 检查 PID 文件（`~/.phone-cli/phone-cli.pid`）：
   - PID 存在且进程存活 → 守护进程已在运行，报错退出。
   - PID 存在但进程已死 → 残留 PID，清理后继续。
   - 无 PID 文件 → 全新启动。
2. 清理残留 socket：如果 `phone-cli.sock` 存在（崩溃遗留），删除之。
3. 扫描已知端口范围内的孤儿子进程：
   - 检查 8100-8199 端口的孤儿 `tidevice wdaproxy` 进程 → 终止。
   - 检查 5037-5099 端口的孤儿 `adb` server 进程 → `adb -P <端口> kill-server`。
   - 检查 5100-5199 端口的孤儿 `hdc` server 进程 → 终止。
4. 写入新 PID 文件。
5. 绑定 Unix socket，启动 accept 循环。

### 关闭流程（SIGTERM / `phone-cli stop`）

1. 停止接受新连接。
2. 使所有活跃会话过期（不通知客户端；客户端下次操作时会收到 `connection_refused`）。
3. 以 SIGTERM 终止所有设备子进程（wdaproxy、adb server），等待 5 秒，必要时 SIGKILL。
4. 删除 socket 文件和 PID 文件。

### 崩溃恢复

如果守护进程崩溃（SIGKILL、OOM 等）：
- 残留的 socket 和 PID 文件留在磁盘上。
- 孤儿子进程（wdaproxy、adb server）继续运行，占用端口。
- 下次 `phone-cli start` 触发上述启动流程，自动清理所有残留。
- 客户端收到 `connection_refused`，需重新 acquire。

## 并发模型

守护进程使用**多线程模型**：

- **主线程**：Unix socket accept 循环。
- **工作线程**：每个客户端连接一个线程（短生命周期，处理单次请求-响应）。
- **Watchdog 线程**：定期超时扫描。
- **线程安全**：`SessionManager` 和 `DeviceManager` 各持有一个 `threading.Lock`。所有状态变更通过锁保护。设备操作（子进程调用）在锁外执行，避免阻塞其他会话。

每设备串行化：`DeviceManager` 为每个 `DeviceSlot` 持有一个 `threading.Lock`。不同设备的操作可并行执行；同一设备的操作串行化。

## 设备访问模型

**独占访问**：每个设备同一时刻最多被一个活跃会话持有。这是有意设计的——同一设备上的并发操作（点击 + 截图）会产生不可预期的结果。只读操作（list_devices、status）不需要会话。

## 排队激活机制

当会话被排队（设备被占）时，`acquire` 调用**阻塞等待**：

1. 客户端发送 `acquire` 请求。
2. 守护进程发现设备被占 → 创建状态为 `queued` 的会话，加入 `DeviceSlot.wait_queue`。
3. 守护进程**保持 socket 连接不关闭**（暂不发送响应）。
4. 当前会话释放/过期时 → 守护进程从 `wait_queue` 弹出下一个，激活它，通过保持的连接发送 `acquire` 响应（`"status": "active"`）。
5. 客户端超时：如果客户端不想无限等待，可设置 socket 超时。超时后守护进程检测到连接关闭，移除排队会话。

这种设计避免了轮询，保持客户端 API 简洁（`acquire` 仅在设备就绪时返回）。

## DeviceSlot（更新版）

```python
@dataclass
class DeviceSlot:
    device_id: str
    device_type: str                    # "ios" | "adb" | "hdc"
    port: int                           # 分配的端口
    current_session_id: str | None
    wait_queue: list[str]               # 排队的 session_id 列表，FIFO 顺序
    process: subprocess.Popen | None    # wdaproxy / adb server 子进程
    lock: threading.Lock                # 每设备操作锁
    connected_at: float
```

## 端口分配 TOCTOU 缓解

bind 检测存在 TOCTOU 窗口：在关闭测试 socket 和启动实际服务之间，外部进程可能抢占该端口。缓解措施：

- 如果服务（wdaproxy、adb server）无法在分配的端口上启动，捕获错误，标记该端口不可用，使用范围内下一个端口重试。
- 最多重试 3 次，之后抛出 `PortExhaustedError`。
- 实际上，窗口期仅有毫秒级，冲突极为罕见。

## 设备健康监控

Watchdog 线程同时监控设备连接状态：

- 每隔 `HEARTBEAT_INTERVAL`（30 秒），检查设备子进程（wdaproxy、adb server）是否存活。
- 如果子进程意外退出：
  - 将活跃会话标记为 `"error"` 状态。
  - 下次 `operate` 调用返回 `{"ok": false, "error": "device_disconnected", "msg": "..."}`。
  - 客户端可 `release` 后重新 `acquire` 来重试。
- 物理设备断开（USB 拔出）通过子进程退出检测（wdaproxy 在设备消失时退出）或平台特定检查（adb devices、tidevice list）发现。

## 错误分类

| 错误码 | 触发条件 | HTTP 类比 |
|--------|----------|-----------|
| `session_not_found` | 未知或已释放的 session_id | 404 |
| `session_expired` | 会话超时过期 | 410 |
| `device_not_found` | 设备 ID 在发现列表中不存在 | 404 |
| `device_busy` | 设备被其他会话持有（仅在非阻塞 acquire 中使用） | 409 |
| `device_disconnected` | 会话期间设备丢失 | 503 |
| `port_exhausted` | 范围内所有端口均被占用 | 503 |
| `operation_failed` | 设备命令返回错误 | 500 |
| `invalid_request` | JSON 格式错误或缺少必需字段 | 400 |
| `daemon_shutting_down` | 守护进程收到 SIGTERM | 503 |

## 自动检测（`device_type: "auto"`）

当 `device_type` 为 `"auto"` 时，守护进程自动解析：

1. 如果 `device_id` 匹配已知 ADB 设备（`adb devices`）→ `"adb"`。
2. 如果 `device_id` 匹配已知 HDC 设备（`hdc list targets`）→ `"hdc"`。
3. 如果 `device_id` 匹配已知 iOS 设备（`tidevice list`）→ `"ios"`。
4. 均不匹配 → 返回 `{"ok": false, "error": "device_not_found"}`。

发现结果缓存 10 秒，避免重复调用子进程。

## 测试策略

- SessionManager 单元测试：acquire/release/expire 状态转换，队列排序。
- 端口分配单元测试：范围扫描、bind 检测 mock、端口耗尽。
- TimeoutWatchdog 单元测试：超时检测，队列激活。
- IPC 集成测试：通过真实 Unix socket 的客户端-守护进程往返通信。
- E2E 测试（需连接设备）：完整的 acquire-operate-release 流程。
