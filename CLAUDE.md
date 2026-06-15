# ClaudeCodeLauncher — AI 辅助开发规则

> 本文件目前聚焦**与 claude-switch（Claude Usage Monitor）的联动契约**。
> 改到下面这些文件/端点时务必小心：它们是另一个项目（`D:\my_pro\Tauri_ob\claude-switch`）
> 的「会话」窗口依赖的对外接口，破坏会导致对方功能挂掉。

## 角色：本启动器 = claude-switch 会话功能的「每台机器的桥」

claude-switch 的「会话」窗口要聚合**本机 + 局域网各机器**的 Claude Code 会话数据，
但它只跑在某台 Windows 上。于是**每台机器各跑一个本启动器自带的薄中继**，对外暴露本机数据；
claude-switch 用 Rust 统一解析 + rusqlite 物化。

- **本机数据**：claude-switch 直接读 `~/.claude/projects`，**不经本中继**。
- **远程机器**：claude-switch 才通过本中继读那台机器的数据。
- 所以「本机自己用」时这个中继可有可无；它主要是为「别的机器要读本机数据」+「接收别的机器推来的预备发言」而存在。

## 薄中继：`session_api_server.py`（绑 `0.0.0.0:47800`，纯标准库、只读 + 队列写）

**不解析、不建库**，只搬运原始数据。端点（即对 claude-switch 的契约，勿随意改名/改结构）：

| 方向 | 端点 | 说明 |
|------|------|------|
| 读 | `GET /api/ping` | 心跳（claude-switch 检测在线） |
| 读 | `GET /api/info` | 本机身份 `{hostname, os, platform}` |
| 读 | `GET /raw/list` | 列全部 `.jsonl`：`{key, session_id, mtime, size}`（key=`<dir>/<file>.jsonl`） |
| 读 | `GET /raw/file?key=...` | 返回该会话文件原始字节（claude-switch 自己解析） |
| 写 | `POST /queue/push` | claude-switch 把「预备发言」推到本机：`{session_id, text, id?}` → 入队 |
| 写 | `GET /queue/list` | 查看本机待发队列（调试用） |
| — | `POST /api/shutdown` | 仅本机优雅关闭 |

`/raw/file` 的 `key` 经 `_resolve_key()` 严格校验（必须 `<dir>/<file>.jsonl`、禁 `..`、限定在 projects 内）。
空闲 `IDLE_TIMEOUT_SECONDS`（默认 900s）无访问自动退出，不留常驻后台。

## 自启：`session_api_autostart.py`

`ensure_running()` 幂等拉起中继（已在跑则跳过、否则 detached 不弹窗启动），由
`claude_launcher.py` / `codex_launcher.py` 进入主流程时调用。多个 ccrun 窗口同时启动时，
靠中继端 `allow_reuse_address=False` 的 bind 失败兜底，保证全局单例。

## 预备发言：claude-switch → 本启动器 → 实时打进正在跑的对话

claude-switch 的「预备发言/待办」挂靠到某个会话。用户在 claude-switch 点 ✈ 投递时：
- **本机会话**：claude-switch 的 Rust 直接写 `~/.claude/launcher_queue.json`（不经中继）。
- **远程会话**：claude-switch `POST /queue/push` 到那台机的中继 → `launcher_queue.push(...)` 写它本机同名文件。

**队列文件契约** `~/.claude/launcher_queue.json`：
`{"version":1,"queue":{"<session_id>":[{"id":"<draft_id>","text":"..."}]}}`，同 `draft_id` 去重，临时文件 `os.replace` 原子替换。

涉及三个模块：

- **`launcher_queue.py`**：队列读写。`push(session_id, text, draft_id)` 入队（去重）；`pop(session_id)` 取走队首并消费。
- **`console_typer.py`**：把文字**逐字符**写进当前控制台输入缓冲。Windows 用 `WriteConsoleInputW`
  （按 UTF-16 码元发送，正确处理中文；**不依赖窗口前台焦点**）。**只填不发**——剥掉 `\r`/尾换行，不注入回车。
- **`claude_launcher.py` 的 `execute_claude_command`**：四种进入对话的触发器全汇于此。先用
  `_resolve_session_id(command, path)` 解析目标会话（`--resume <id>` 直接取；`-c` 反查最近会话；
  新建 `claude` / 无 id 的 `--resume` 选择器拿不到 → 跳过），再 `_start_draft_watcher` 起一个
  **后台轮询线程**：会话存活期间每秒 `launcher_queue.pop` 一次，有就 `console_typer.type_text` 打进去；
  会话退出时主线程 `stop_evt.set()` 停。既覆盖「进入前已排队」也覆盖「**常驻对话期间随时推送**」。

**为什么能在 claude 运行时打字**：`subprocess.run(..., shell=True)` 阻塞的是**主线程**，而本启动器进程与
claude **共用同一个控制台**，所以后台线程仍能 `WriteConsoleInput` 写进 claude 正在读的输入缓冲。
**因此只有经更新后的启动器进入/恢复的会话才带 watcher**；更新前拉起的旧会话需重新 `ccrun` 进入一次才生效。

## 改这块时的注意

- `/raw/list`、`/raw/file`、`/api/ping`、`/api/info` 是 claude-switch 的硬依赖：**字段名、`key` 格式不要改**。
  对应的 Rust 解析在 claude-switch 的 `src-tauri/src/session_store.rs`（`sync_remote`）。
- `~/.claude/projects` 下的 JSONL 是只读来源，中继**只读不写**。
- 真正的会话解析/物化逻辑在 claude-switch（Rust），本仓库不要重新实现一套解析。
- `~/.claude/launcher_queue.json` 是预备发言的本机落地点，结构改动需与 claude-switch 推送端（`session_store.rs` 的 `push_local_queue` / 中继 `/queue/push`）同步。
- `console_typer` **只填不发**：绝不注入回车（`\r`），由用户检查后自行发送。改动注入逻辑勿破坏这条。
- 实时注入依赖「启动器与 claude 共用同一控制台」+「后台线程」。若哪天把 `subprocess.run` 改成新开窗口/新控制台
  （如 `CREATE_NEW_CONSOLE`、`wt.exe` 起新窗口），`WriteConsoleInputW` 会失效，需改用 `AttachConsole(目标pid)` 或 `SendInput`。
