#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Claude 会话数据本地 HTTP API（方案A：实时解析 JSONL，只读）

每台机器各跑一个，绑定 0.0.0.0 对局域网开放，供 claude-switch (Tauri)
的「会话」横屏窗口聚合消费。跨 macOS / Windows，纯标准库无第三方依赖。

端点：
  GET /api/ping              心跳（不解析，最便宜，供断连检测）
  GET /api/info              本机身份 + 会话/项目计数
  GET /api/sessions          全部会话列表（标题/项目/时间/分支/大小）
  GET /api/session/<id>      单会话消息时间轴（主人发言 + 回复）
  GET /api/stats             按本地日期统计每天发言条数/字数

用法：python session_api_server.py [port]   （默认端口 47800）
"""
import os
import sys
import json
import time
import socket
import threading
import platform
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

from conversation_viewer import ConversationViewer

VERSION = "1.0.0"
DEFAULT_PORT = 47800
# 空闲多久没人访问就自动退出（秒）；0 = 常驻不退。
# 会话窗口开着会持续心跳续命；窗口一关、超时后进程自动消失，不留常驻后台。
IDLE_TIMEOUT_SECONDS = 900

# 无需 launcher，仅用其解析能力
viewer = ConversationViewer(None)

# 最近一次被访问的时刻（单调时钟），看门狗据此判断空闲
_state = {"last": 0.0}


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode('utf-8')


class SessionAPIHandler(BaseHTTPRequestHandler):
    server_version = "ClaudeSessionAPI/" + VERSION

    def _send(self, obj, status=200):
        body = _json_bytes(obj)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def log_message(self, *args):
        """静默，避免刷屏（心跳轮询会很频繁）"""
        pass

    def do_POST(self):
        path = urlparse(self.path).path.rstrip('/')
        if path in ('/api/shutdown', '/shutdown'):
            # 仅允许本机优雅关闭（claude-switch 关闭会话窗口时调用）
            if self.client_address[0] in ('127.0.0.1', '::1'):
                self._send({'ok': True, 'shutting_down': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._send({'ok': False, 'error': 'forbidden'}, 403)
            return
        self._send({'ok': False, 'error': 'not found'}, 404)

    def do_GET(self):
        _state["last"] = time.monotonic()  # 任意访问（含心跳）都续命
        path = urlparse(self.path).path.rstrip('/')
        try:
            if path in ('/api/ping', '/ping'):
                self._send({'ok': True, 'pong': True})
            elif path in ('/api/info', '/info', ''):
                self._send(self._info())
            elif path in ('/api/sessions', '/sessions'):
                self._send(self._sessions())
            elif path.startswith('/api/session/'):
                sid = unquote(path[len('/api/session/'):])
                self._send(self._session(sid))
            elif path in ('/api/stats', '/stats'):
                self._send(self._stats())
            else:
                self._send({'ok': False, 'error': 'not found'}, 404)
        except Exception as e:
            self._send({'ok': False, 'error': str(e)}, 500)

    # ---------- 各端点 ----------

    def _info(self):
        sessions = viewer.get_all_sessions_info()
        projects = set(s.get('project_path', '') for s in sessions if s.get('project_path'))
        return {
            'ok': True,
            'service': 'claude-session-api',
            'version': VERSION,
            'hostname': socket.gethostname(),
            'os': platform.system(),
            'platform': sys.platform,
            'project_count': len(projects),
            'session_count': len(sessions),
        }

    def _sessions(self):
        sessions = viewer.get_all_sessions_info()
        out = []
        for s in sessions:
            out.append({
                'id': s['id'],
                'title': s['title'],
                'project_path': s.get('project_path', ''),
                'project_name': s.get('project_name', ''),
                'git_branch': s.get('git_branch', ''),
                'last_unix': s.get('last_unix', 0),
                'file_size': s.get('file_size', 0),
                'size_human': viewer.format_file_size(s.get('file_size', 0)),
            })
        return {'ok': True, 'hostname': socket.gethostname(), 'sessions': out}

    def _session(self, sid):
        fp = viewer.find_session_file(sid)
        if not fp:
            return {'ok': False, 'error': 'session not found'}
        info = viewer.get_session_info(fp)
        cwd = viewer._read_cwd(fp) or ''
        return {
            'ok': True,
            'id': sid,
            'hostname': socket.gethostname(),
            'title': info.get('title', '') if info else '',
            'project_path': cwd,
            'project_name': os.path.basename(cwd.rstrip('/\\')),
            'git_branch': info.get('git_branch', '') if info else '',
            'messages': viewer.get_session_messages(fp),
        }

    def _stats(self):
        return {
            'ok': True,
            'hostname': socket.gethostname(),
            'days': viewer.get_daily_stats(),
        }


class SessionHTTPServer(ThreadingHTTPServer):
    # 关闭端口复用：Windows 下 SO_REUSEADDR 会让多个进程都 bind 成功，
    # 关掉后第二个实例 bind 失败 → 竞态兜底（安静退出）才可靠，保证全局单例。
    allow_reuse_address = False
    daemon_threads = True


def _idle_watchdog(server, timeout):
    """空闲超时自动退出：超过 timeout 秒无任何访问就停掉服务"""
    if timeout <= 0:
        return
    check_interval = min(30, max(5, timeout // 4))
    while True:
        time.sleep(check_interval)
        if time.monotonic() - _state["last"] > timeout:
            print(f"空闲超过 {timeout}s，自动退出")
            threading.Thread(target=server.shutdown, daemon=True).start()
            return


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
        server = SessionHTTPServer((host, port), SessionAPIHandler)
    except OSError:
        # 端口被占用 = 已有实例在跑（多个 ccrun 同时启动时的竞态兜底），安静退出
        print(f"端口 {port} 已被占用，可能已有会话 API 实例在运行，本次不重复启动")
        return
    _state["last"] = time.monotonic()
    if idle_timeout and idle_timeout > 0:
        threading.Thread(target=_idle_watchdog, args=(server, idle_timeout), daemon=True).start()
    lan = get_lan_ip()
    print("=" * 56)
    print(" Claude 会话 API 服务已启动")
    print("=" * 56)
    print(f"  本机访问 : http://127.0.0.1:{port}/api/info")
    print(f"  局域网   : http://{lan}:{port}/api/info")
    print(f"            （在另一台机器的 Tauri「会话」里填这个地址）")
    print(f"  端点     : /api/ping /api/info /api/sessions")
    print(f"             /api/session/<id> /api/stats")
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
