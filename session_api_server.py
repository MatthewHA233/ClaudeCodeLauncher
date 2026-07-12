#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Claude / Codex 会话「薄中继」HTTP 服务（只读、跨平台、纯标准库）。

每台机器各跑一个，绑 0.0.0.0:47800 对局域网开放。它**不解析、不建库**，
只把本机 Claude / Codex 会话原始数据传出去，由 Claude Usage Monitor (Rust)
统一解析 + rusqlite 物化。本机数据 Claude Usage Monitor 直接读文件系统、不经此中继；
此中继只为「别的机器要读本机数据」而存在。

端点：
  GET  /api/ping           心跳
  GET  /api/info           本机身份（hostname/os）
  GET  /raw/list?provider=claude_code|codex
                            列出对应 provider 的 .jsonl
  GET  /raw/file?provider=...&key=...
                            返回对应会话文件的原始字节（纯文本）
  GET  /api/token_summary?since_days=N  本机 token 用量摘要(date×provider×model)，供跨机器汇总
  GET  /queue/list         查看本机待发的「预备发言」队列（按 session_id 分组）
  POST /queue/push         Claude Usage Monitor 推入一条待发草稿 {session_id, text, id?}
  POST /claims/set_registry 主控机下发 claim registry 地址 {url}（本机 hook 据此 acquire）
  GET  /claims/registry    查看本机已存的 registry 地址
  POST /api/shutdown       本机优雅关闭

空闲超时自动退出，不留常驻后台。
用法：python session_api_server.py [port]   （默认 47800）
"""
import os
import sys
import json
import time
import socket
import threading
import platform
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

VERSION = "2.3.0"
DEFAULT_PORT = 47800
# 空闲多久没人访问就自动退出（秒）；0 = 常驻不退。
# 设 0：本中继是「会话归档」的数据出口，别的机器随时可能来读，不该因本机没活动就退出
# →常驻可达。单例由端口 bind 失败兜底，重启随 launcher 幂等自启，关机即没、pkill 可手动停。
IDLE_TIMEOUT_SECONDS = 0
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
CLAUDE_PROVIDER = "claude_code"
CODEX_PROVIDER = "codex"
RAW_PROVIDERS = (CLAUDE_PROVIDER, CODEX_PROVIDER)

# 最近一次被访问的时刻（单调时钟），看门狗据此判断空闲
_state = {"last": 0.0}

_machine_id_cache = None


def machine_id():
    """机器稳定标识：OS 原生硬件/系统 id，改名/换 IP/重装系统都不变。
    对端据此把同一台机器永久绑定为同一来源（不再因 IP 变动而丢历史）。
    macOS=IOPlatformUUID / Windows=注册表 MachineGuid / Linux=/etc/machine-id；
    取不到时回退为 hostname 的稳定 hash（带 'h:' 前缀以示降级）。纯标准库实现。"""
    global _machine_id_cache
    if _machine_id_cache:
        return _machine_id_cache
    mid = ""
    try:
        sysname = platform.system()
        if sysname == "Darwin":
            import subprocess
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    mid = line.split('"')[-2]
                    break
        elif sysname == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                mid = winreg.QueryValueEx(k, "MachineGuid")[0]
        else:  # Linux / 其它
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(p):
                    mid = Path(p).read_text(encoding="utf-8", errors="ignore").strip()
                    if mid:
                        break
    except Exception:
        mid = ""
    if not mid:
        import hashlib
        mid = "h:" + hashlib.sha1(socket.gethostname().encode("utf-8")).hexdigest()[:16]
    _machine_id_cache = mid.strip()
    return _machine_id_cache


def _file_entry(fp, key):
    try:
        st = fp.stat()
    except OSError:
        return None
    return {
        'key': key,
        'session_id': fp.stem,
        'mtime': int(st.st_mtime),
        'size': int(st.st_size),
    }


def _list_claude_files():
    """列出 ~/.claude/projects 下所有 Claude JSONL（保持旧 key 格式）。"""
    out = []
    if not PROJECTS_DIR.exists():
        return out
    for dir_name in os.listdir(PROJECTS_DIR):
        dir_path = PROJECTS_DIR / dir_name
        if not dir_path.is_dir():
            continue
        for fn in os.listdir(dir_path):
            if not fn.endswith('.jsonl'):
                continue
            entry = _file_entry(dir_path / fn, f"{dir_name}/{fn}")
            if entry:
                out.append(entry)
    return out


def _list_codex_files():
    """列出 $CODEX_HOME/sessions + archived_sessions 下所有 Codex rollout。"""
    out = []
    for root_name in ("sessions", "archived_sessions"):
        root = CODEX_HOME / root_name
        if not root.exists():
            continue
        try:
            files = root.rglob("*.jsonl")
            for fp in files:
                if not fp.is_file():
                    continue
                try:
                    key = fp.relative_to(CODEX_HOME).as_posix()
                except ValueError:
                    continue
                entry = _file_entry(fp, key)
                if entry:
                    out.append(entry)
        except OSError:
            continue
    return out


def _list_files(provider=CLAUDE_PROVIDER):
    if provider == CLAUDE_PROVIDER:
        return _list_claude_files()
    if provider == CODEX_PROVIDER:
        return _list_codex_files()
    return []


def _resolve_key(key, provider=CLAUDE_PROVIDER):
    """按 provider 安全映射 key，严格限制在对应会话根目录内。"""
    if not key or '..' in key:
        return None
    parts = key.replace('\\', '/').split('/')
    if any(not part for part in parts) or not parts[-1].endswith('.jsonl'):
        return None
    if provider == CLAUDE_PROVIDER:
        if len(parts) != 2:
            return None
        root = PROJECTS_DIR
        fp = root / parts[0] / parts[1]
    elif provider == CODEX_PROVIDER:
        if parts[0] not in ("sessions", "archived_sessions"):
            return None
        root = CODEX_HOME / parts[0]
        fp = CODEX_HOME.joinpath(*parts)
    else:
        return None
    try:
        fp_resolved = fp.resolve()
        root = root.resolve()
    except OSError:
        return None
    if root not in fp_resolved.parents:
        return None
    if not fp_resolved.is_file():
        return None
    return fp_resolved


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "ClaudeSessionRelay/" + VERSION

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _raw(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        """静默，避免刷屏（心跳轮询很频繁）"""
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path.rstrip('/')
        if path in ('/api/shutdown', '/shutdown'):
            # 仅允许本机优雅关闭
            if self.client_address[0] in ('127.0.0.1', '::1'):
                self._json({'ok': True, 'shutting_down': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._json({'ok': False, 'error': 'forbidden'}, 403)
            return
        if path in ('/queue/push', '/queue'):
            # Claude Usage Monitor 把「预备发言」推到本机：写入 ~/.claude/launcher_queue.json，
            # 由本机启动器进入对话时消费。{session_id, text, id?}
            try:
                length = int(self.headers.get('Content-Length', 0) or 0)
                raw = self.rfile.read(length) if length else b''
                payload = json.loads(raw.decode('utf-8') or '{}')
            except Exception as e:
                self._json({'ok': False, 'error': f'bad json: {e}'}, 400)
                return
            session_id = (payload.get('session_id') or '').strip()
            text = payload.get('text') or ''
            draft_id = payload.get('id')
            if not session_id or not text:
                self._json({'ok': False, 'error': 'session_id and text required'}, 400)
                return
            try:
                import launcher_queue
                ok = launcher_queue.push(session_id, text, draft_id)
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)
                return
            self._json({'ok': bool(ok)}, 200 if ok else 500)
            return
        if path in ('/claims/set_registry',):
            # 主控机下发它的 claim registry 地址 {url}；本机写 claim_registry.json，
            # 由本机 PreToolUse hook 据此向主控机 acquire（先来后到的跨机文件占用）。
            try:
                length = int(self.headers.get('Content-Length', 0) or 0)
                raw = self.rfile.read(length) if length else b''
                payload = json.loads(raw.decode('utf-8') or '{}')
            except Exception as e:
                self._json({'ok': False, 'error': f'bad json: {e}'}, 400)
                return
            url = (payload.get('url') or '').strip()
            if not url:
                self._json({'ok': False, 'error': 'url required'}, 400)
                return
            try:
                import file_claims
                ok = file_claims.set_registry(url)
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)
                return
            self._json({'ok': bool(ok)}, 200 if ok else 500)
            return
        self._json({'ok': False, 'error': 'not found'}, 404)

    def do_GET(self):
        _state["last"] = time.monotonic()  # 任意访问（含心跳）都续命
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        try:
            if path in ('/api/ping', '/ping'):
                self._json({'ok': True, 'pong': True})
            elif path in ('/api/info', '/info', ''):
                self._json({
                    'ok': True,
                    'service': 'claude-session-relay',
                    'version': VERSION,
                    'machine_id': machine_id(),  # 机器稳定 id：对端据此绑定设备(换 IP/改名不变)
                    'hostname': socket.gethostname(),
                    'os': platform.system(),
                    'platform': sys.platform,
                    'raw_providers': list(RAW_PROVIDERS),
                })
            elif path in ('/raw/list', '/raw'):
                qs = parse_qs(parsed.query)
                provider = (qs.get('provider', [CLAUDE_PROVIDER])[0] or CLAUDE_PROVIDER).strip()
                if provider not in RAW_PROVIDERS:
                    self._json({'ok': False, 'error': 'invalid provider'}, 400)
                    return
                self._json({
                    'ok': True,
                    'hostname': socket.gethostname(),
                    'provider': provider,
                    'files': _list_files(provider),
                })
            elif path == '/raw/file':
                qs = parse_qs(parsed.query)
                provider = (qs.get('provider', [CLAUDE_PROVIDER])[0] or CLAUDE_PROVIDER).strip()
                key = (qs.get('key', [''])[0] or '').strip()
                fp = _resolve_key(key, provider)
                if not fp:
                    self._json({'ok': False, 'error': 'invalid key'}, 400)
                    return
                with open(fp, 'rb') as f:
                    self._raw(f.read())
            elif path in ('/api/token_summary', '/token/summary'):
                # 跨机器 token 汇总：本机扫 jsonl 算 token 摘要(按 date/provider/model)传出，
                # 由对端 Claude Usage Monitor 合并。算法与其 Rust token_usage.rs 逐字段一致。
                qs = parse_qs(parsed.query)
                try:
                    since_days = int((qs.get('since_days', ['400'])[0] or '400'))
                except ValueError:
                    since_days = 400
                import token_summary
                rep = token_summary.compute(since_days)
                rep['hostname'] = socket.gethostname()
                self._json(rep)
            elif path in ('/queue/list', '/queue'):
                # 查看本机待发的预备发言队列（按 session_id 分组），供调试/校验
                try:
                    import launcher_queue
                    q = launcher_queue._load().get('queue', {})
                except Exception:
                    q = {}
                self._json({'ok': True, 'queue': q})
            elif path in ('/claims/registry',):
                # 查看本机已存的 registry 地址（调试/校验用；hook 直接读文件不经此）
                try:
                    import file_claims
                    url = file_claims.get_registry()
                except Exception:
                    url = None
                self._json({'ok': True, 'url': url})
            else:
                self._json({'ok': False, 'error': 'not found'}, 404)
        except Exception as e:
            self._json({'ok': False, 'error': str(e)}, 500)


class SessionHTTPServer(ThreadingHTTPServer):
    # 关闭端口复用：Windows 下 SO_REUSEADDR 会让多个进程都 bind 成功，
    # 关掉后第二个实例 bind 失败 → 竞态兜底（安静退出）才可靠，保证全局单例。
    allow_reuse_address = False
    daemon_threads = True


def _idle_watchdog(server, timeout):
    """空闲超时自动退出"""
    if timeout <= 0:
        return
    check_interval = min(30, max(5, timeout // 4))
    while True:
        time.sleep(check_interval)
        if time.monotonic() - _state["last"] > timeout:
            print(f"空闲超过 {timeout}s，自动退出")
            threading.Thread(target=server.shutdown, daemon=True).start()
            return


def _start_mdns_advertise(port):
    """用系统原生 Bonjour 广播本中继(_claude-relay._tcp)，便于对端零配置发现。

    保持「纯标准库」：不引 zeroconf 依赖，改 subprocess 调系统工具——
    macOS 用内置 `dns-sd -R`，Linux 用 `avahi-publish-service`(若装了 avahi)。
    返回 Popen(供退出时终止)；不支持/失败时返回 None，绝不影响中继主流程。
    """
    import shutil
    import subprocess
    try:
        host = socket.gethostname()
        sysname = platform.system()
        mid = machine_id()  # 机器稳定 id，放进 TXT 供对端零配置「按设备」绑定/配对
        if sysname == "Darwin" and shutil.which("dns-sd"):
            args = ["dns-sd", "-R", host, "_claude-relay._tcp", "local", str(port),
                    f"os=macos", f"host={host}", f"mid={mid}"]
        elif sysname == "Linux" and shutil.which("avahi-publish-service"):
            args = ["avahi-publish-service", host, "_claude-relay._tcp", str(port),
                    "os=linux", f"host={host}", f"mid={mid}"]
        else:
            return None  # 其它平台暂不广播(对端仍可手动填地址)
        return subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except Exception:
        return None


def get_lan_ip():
    """获取本机局域网 IP（不实际发包，仅用于显示给另一台机器填写）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def run(host='0.0.0.0', port=DEFAULT_PORT, idle_timeout=IDLE_TIMEOUT_SECONDS):
    try:
        server = SessionHTTPServer((host, port), RelayHandler)
    except OSError:
        print(f"端口 {port} 已被占用，可能已有中继实例在运行，本次不重复启动")
        return
    _state["last"] = time.monotonic()
    if idle_timeout and idle_timeout > 0:
        threading.Thread(target=_idle_watchdog, args=(server, idle_timeout), daemon=True).start()
    advertiser = _start_mdns_advertise(port)  # mDNS 广播(便于对端零配置发现)；不支持的平台返回 None
    lan = get_lan_ip()
    print("=" * 56)
    print(" Claude 会话薄中继已启动")
    print("=" * 56)
    print(f"  本机访问 : http://127.0.0.1:{port}/api/info")
    print(f"  局域网   : http://{lan}:{port}/api/info")
    print(f"            （在另一台机器的 Claude Usage Monitor「会话」里填这个地址）")
    print(f"  端点     : /api/ping /api/info /raw/list?provider= /raw/file?provider=&key= /api/token_summary /queue/push")
    if advertiser is not None:
        print(f"  局域网发现: 已用 Bonjour 广播 _claude-relay._tcp（对端可零配置发现本机）")
    if idle_timeout and idle_timeout > 0:
        print(f"  空闲退出 : {idle_timeout}s 无访问自动停止")
    print(f"  Ctrl+C 停止")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()
    finally:
        if advertiser is not None:
            try:
                advertiser.terminate()
            except Exception:
                pass
        server.server_close()


if __name__ == '__main__':
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"端口参数无效，使用默认 {DEFAULT_PORT}")
    idle = IDLE_TIMEOUT_SECONDS
    if len(sys.argv) > 2:
        try:
            idle = int(sys.argv[2])
        except ValueError:
            pass
    run(port=port, idle_timeout=idle)
