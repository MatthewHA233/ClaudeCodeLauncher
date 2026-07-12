#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装/更新 macOS LaunchAgent，让 session relay 登录后自动启动。纯标准库。"""

import argparse
import os
import plistlib
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

LABEL = "com.matthew.claude-session-relay"
DEFAULT_PORT = 47800


def _domain():
    return f"gui/{os.getuid()}"


def _is_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _shutdown_old(port):
    try:
        req = Request(f"http://127.0.0.1:{port}/api/shutdown", data=b"{}", method="POST")
        urlopen(req, timeout=2).read()
    except Exception:
        return
    for _ in range(30):
        if not _is_port_open(port):
            return
        time.sleep(0.1)


def _run_launchctl(*args, check=False):
    return subprocess.run(
        ["launchctl", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=check,
    )


def _is_loaded():
    return _run_launchctl("print", f"{_domain()}/{LABEL}").returncode == 0


def _plist_bytes(port):
    here = Path(__file__).resolve().parent
    logs = Path.home() / "Library" / "Logs"
    logs.mkdir(parents=True, exist_ok=True)
    data = {
        "Label": LABEL,
        "ProgramArguments": [
            str(Path(sys.executable).resolve()),
            str(here / "session_api_server.py"),
            str(port),
        ],
        "WorkingDirectory": str(here),
        "RunAtLoad": True,
        # 异常退出自动拉起；/api/shutdown 正常退出时保持停止，便于更新。
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Background",
        "ThrottleInterval": 5,
        "StandardOutPath": str(logs / "claude-session-relay.log"),
        "StandardErrorPath": str(logs / "claude-session-relay.error.log"),
    }
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        data["EnvironmentVariables"] = {"CODEX_HOME": codex_home}
    return plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=True)


def install(port=DEFAULT_PORT, restart=True):
    if platform.system() != "Darwin":
        return False
    agents = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist_path = agents / f"{LABEL}.plist"
    new_bytes = _plist_bytes(port)
    old_bytes = plist_path.read_bytes() if plist_path.exists() else None
    if old_bytes != new_bytes:
        tmp = plist_path.with_suffix(".plist.tmp")
        tmp.write_bytes(new_bytes)
        os.replace(tmp, plist_path)

    loaded = _is_loaded()
    if restart:
        _shutdown_old(port)
        if loaded:
            _run_launchctl("bootout", f"{_domain()}/{LABEL}")
        _run_launchctl("bootstrap", _domain(), str(plist_path), check=True)
        _run_launchctl("kickstart", "-k", f"{_domain()}/{LABEL}", check=True)
    elif not loaded and not _is_port_open(port):
        _run_launchctl("bootstrap", _domain(), str(plist_path), check=True)
    return True


def uninstall(port=DEFAULT_PORT):
    if platform.system() != "Darwin":
        return False
    _shutdown_old(port)
    if _is_loaded():
        _run_launchctl("bootout", f"{_domain()}/{LABEL}")
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if plist_path.exists():
        plist_path.unlink()
    return True


def main():
    parser = argparse.ArgumentParser(description="安装 macOS Claude/Codex 会话中继自启动")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        raise SystemExit("此安装器仅支持 macOS")
    if args.uninstall:
        uninstall(args.port)
        print("macOS session relay LaunchAgent 已卸载")
    else:
        install(args.port, restart=not args.no_restart)
        print(f"macOS session relay 已安装并监听 0.0.0.0:{args.port}")


if __name__ == "__main__":
    main()
