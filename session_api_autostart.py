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
from pathlib import Path

DEFAULT_PORT = 47800


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
        ensure_claim_hook_installed()  # 顺手铺/更新跨机文件占用 hook（幂等、安全合并 settings.json）
        # 打包成 exe 后 sys.executable 是 exe（非 python），没法拿它拉起 .py 脚本，
        # 强行 spawn 反而会误开一个 launcher 窗口；中继是给跨机读数据用的，打包版直接跳过。
        if getattr(sys, "frozen", False):
            return False

        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_api_server.py")
        if not os.path.exists(script):
            return False

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


def _claim_hook_command_base(dst_path):
    """hook command 前缀：用对的 python 解释器 + 脚本路径（均加引号防空格）。
    脚本运行时 sys.executable 是 python.exe → 直接用；打包成 exe 时回退 PATH 的 python。"""
    exe = sys.executable or ""
    py = exe if "python" in os.path.basename(exe).lower() else "python"
    return f'"{py}" "{dst_path}"'


def ensure_claim_hook_installed():
    """把 claim_hook.py 铺到 ~/.claude/hooks/ 并在 ~/.claude/settings.json 注册三处 hook
    （PreToolUse: Edit|Write|MultiEdit；SessionStart；UserPromptSubmit）。

    幂等：脚本内容/配置无变化则不写。安全：只动「我们这条」（command 含 claim_hook.py），
    绝不覆盖用户其它 hook；settings.json 解析失败时放弃（宁可不装也不毁配置）。任何异常静默。"""
    try:
        home = Path.home()
        src = Path(os.path.dirname(os.path.abspath(__file__))) / "claim_hook.py"
        if not src.exists():
            return
        hooks_dir = home / ".claude" / "hooks"
        dst = hooks_dir / "claim_hook.py"

        # 1) 铺脚本（内容不同才写，幂等）
        hooks_dir.mkdir(parents=True, exist_ok=True)
        new_code = src.read_text(encoding="utf-8")
        old_code = dst.read_text(encoding="utf-8") if dst.exists() else None
        if new_code != old_code:
            dst.write_text(new_code, encoding="utf-8")

        # 2) 安全合并 settings.json
        settings_path = home / ".claude" / "settings.json"
        try:
            data = (
                json.loads(settings_path.read_text(encoding="utf-8"))
                if settings_path.exists()
                else {}
            )
        except Exception:
            return  # 解析失败：不冒险改用户文件
        if not isinstance(data, dict):
            return

        base = _claim_hook_command_base(str(dst))
        specs = [
            ("PreToolUse", "Edit|Write|MultiEdit", f"{base} pretooluse"),
            ("SessionStart", None, f"{base} context"),
            ("UserPromptSubmit", None, f"{base} context"),
        ]
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            hooks = {}
            data["hooks"] = hooks

        before = json.dumps(data, sort_keys=True, ensure_ascii=False)
        for event, matcher, command in specs:
            arr = hooks.get(event)
            if not isinstance(arr, list):
                arr = []
            # 删掉旧的「我们这条」（command 含 claim_hook.py），保留用户其它 hook
            kept = []
            for item in arr:
                cmds = []
                if isinstance(item, dict):
                    for h in (item.get("hooks") or []):
                        if isinstance(h, dict):
                            cmds.append(h.get("command") or "")
                if any("claim_hook.py" in c for c in cmds):
                    continue
                kept.append(item)
            entry = {"hooks": [{"type": "command", "command": command}]}
            if matcher:
                entry["matcher"] = matcher
            kept.append(entry)
            hooks[event] = kept
        after = json.dumps(data, sort_keys=True, ensure_ascii=False)
        if before == after:
            return  # 已是最新，无需写

        tmp = settings_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(settings_path))
    except Exception:
        pass
