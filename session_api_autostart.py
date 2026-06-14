#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""会话 API 服务的幂等自启：被 launcher 启动时调用。

设计目标：用户经常同时开一大堆 ccrun 窗口，每个都会调用这里，
但会话 API 服务全局只能有一份、绝不冲突：
  1. 先探测端口，已有服务在跑就直接跳过（连 spawn 都不做）。
  2. 否则后台 detached 拉起，脱离 launcher 进程常驻、不弹窗。
  3. 极端竞态（多个窗口几乎同时探测到没在跑都去 spawn）由
     session_api_server.py 端 bind 失败安静退出兜底，最终只活一份。
任何异常都被吞掉，绝不影响 launcher 主流程。
"""
import os
import sys
import json
import socket
import subprocess

DEFAULT_PORT = 47800
# 公共注册文件：记录怎么拉起本机会话 API（python 解释器 + 脚本路径 + 端口）。
# claude-switch 打开会话窗口时读它来确保本机服务在跑，用户无需手动配置路径。
REGISTRY_PATH = os.path.join(os.path.expanduser("~"), ".claude_session_api.json")


def _write_registry(port):
    """写公共注册文件，记录本机会话 API 的启动方式（失败不影响主流程）"""
    try:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_api_server.py")
        data = {
            "python": sys.executable,
            "script": script,
            "port": port,
        }
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def is_running(port=DEFAULT_PORT, timeout=0.3):
    """探测本机端口是否已有服务在监听"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False
    finally:
        sock.close()


def ensure_running(port=DEFAULT_PORT):
    """幂等地确保会话 API 服务在后台运行。

    返回值：True=本次拉起了新进程，False=已在跑/跳过/失败（均不影响主流程）。
    """
    try:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_api_server.py")
        if not os.path.exists(script):
            return False

        # 无论是否已在跑，都刷新注册文件，保证 claude-switch 拿到最新启动方式
        _write_registry(port)

        if is_running(port):
            return False

        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            # 脱离父进程 + 不弹控制台窗口（用户会同时开很多 ccrun 窗口）
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
            kwargs["close_fds"] = True
        else:
            kwargs["start_new_session"] = True

        subprocess.Popen([sys.executable, script, str(port)], **kwargs)
        return True
    except Exception:
        return False
