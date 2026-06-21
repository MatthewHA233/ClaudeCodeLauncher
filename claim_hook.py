#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Claude Code 跨机文件占用 claim hook（自包含、纯标准库）。

由启动器铺设到 ~/.claude/hooks/claim_hook.py，并在 ~/.claude/settings.json 注册三处：
- PreToolUse(Edit|Write|MultiEdit): `python claim_hook.py pretooluse`
    改文件前向主控机 registry acquire（先来后到）+ 续租心跳。**advisory：始终放行（exit 0）**，
    绝不阻断写码；冲突只写 stderr 提示给人看。
- SessionStart / UserPromptSubmit: `python claim_hook.py context`
    拉全局占用清单，把「别的机器/协作者正在改哪些文件」打到 stdout → 注入 Claude 上下文，
    让 AI 自己避让（核实：SessionStart/UserPromptSubmit 的 stdout 直接进上下文）。

registry 地址优先级：环境变量 CLAIM_REGISTRY_URL > ~/.claude/claim_registry.json（主控机下发） > 本机 127.0.0.1:47801（兜底）。
连不上 → 静默放行（降级为无锁，绝不阻断）。owner 取 CLAIM_OWNER 或 hostname；machine_id 取 OS 原生稳定 id（设备唯一标识）。

claim 的 key = 「仓库名/相对仓库根的路径」（向上找 .git），保证**跨机器同一文件 = 同一 key**，
否则各机本地绝对路径不同就无法识别「两台机器在改同一个文件」。
"""
import os
import sys
import json
import socket
import platform
import hashlib
from pathlib import Path
from urllib import request as _req

VERSION = "1.0.0"

REGISTRY_FILE = Path.home() / ".claude" / "claim_registry.json"
TIMEOUT = 3  # 秒：够局域网，且不拖慢 Claude（UserPromptSubmit 阻塞用户输入）


# ---------- 配置 / 身份 ----------

def _registry_url():
    env = (os.environ.get("CLAIM_REGISTRY_URL") or "").strip()
    if env:
        return env
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            url = (json.load(f) or {}).get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    except Exception:
        pass
    return "http://127.0.0.1:47801"  # 兜底：本机若是 registry（开着 monitor）即连本机；连不上则降级放行


def _owner():
    return (os.environ.get("CLAIM_OWNER") or "").strip() or socket.gethostname()


def _machine_id():
    """OS 原生稳定 id（与中继 machine_id() 一致）：换 IP/改名/重装都不变。"""
    mid = ""
    try:
        sysname = platform.system()
        if sysname == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                mid = winreg.QueryValueEx(k, "MachineGuid")[0]
        elif sysname == "Darwin":
            import subprocess
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                 capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    mid = line.split('"')[-2]
                    break
        else:
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(p):
                    mid = Path(p).read_text(encoding="utf-8", errors="ignore").strip()
                    if mid:
                        break
    except Exception:
        mid = ""
    if not mid:
        mid = "h:" + hashlib.sha1(socket.gethostname().encode("utf-8")).hexdigest()[:16]
    return mid.strip()


# ---------- 路径规范化（跨机一致的 claim key） ----------

def _git_root(path):
    """从 path 向上找含 .git 的目录；找不到返回 None。"""
    cur = os.path.dirname(path) if os.path.isfile(path) else path
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _norm_path(fp):
    """claim key = 仓库名/相对仓库根路径；不在仓库内则退化为文件名。"""
    try:
        ap = os.path.abspath(fp)
    except Exception:
        return fp.replace("\\", "/")
    root = _git_root(ap)
    if root:
        repo = os.path.basename(root.rstrip("/\\")) or "repo"
        rel = os.path.relpath(ap, root).replace("\\", "/")
        return f"{repo}/{rel}"
    return os.path.basename(ap)


# ---------- HTTP（纯标准库） ----------

def _join(base, path):
    return base.rstrip("/") + path


def _post(url, obj):
    data = json.dumps(obj).encode("utf-8")
    r = _req.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with _req.urlopen(r, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _get(url):
    with _req.urlopen(url, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _read_stdin_json():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


# ---------- 子命令 ----------

def cmd_pretooluse():
    """改文件前 acquire（顺带续租心跳）；advisory，始终放行。"""
    base = _registry_url()
    if not base:
        return 0  # 没 registry → 降级放行
    data = _read_stdin_json()
    tool_input = data.get("tool_input") or {}
    fp = (tool_input.get("file_path") or "").strip()
    if not fp:
        return 0
    path = _norm_path(fp)
    try:
        out = _post(_join(base, "/claims/acquire"), {
            "path": path,
            "owner": _owner(),
            "machine_id": _machine_id(),
            "host": socket.gethostname(),
            "session_id": data.get("session_id") or "",
        })
    except Exception:
        return 0  # 连不上 → 降级放行
    if not out.get("granted", True):
        holder = out.get("holder") or {}
        who = holder.get("owner") or holder.get("host") or "另一台机器"
        sys.stderr.write(
            f"⚠ 文件占用提醒：{path} 已被 {who} 先占用（先来后到），建议先同步或换文件。\n"
        )
    return 0


def cmd_context():
    """拉全局占用清单，把「别人在改什么」打到 stdout → 注入 Claude 上下文。"""
    base = _registry_url()
    if not base:
        return 0
    try:
        out = _get(_join(base, "/claims/list"))
    except Exception:
        return 0
    me = _machine_id()
    others = [c for c in (out.get("claims") or []) if c.get("machine_id") != me]
    if not others:
        return 0
    lines = ["[跨机文件占用] 其他机器/协作者正在修改以下文件（先来后到，请避让或先沟通）："]
    for c in others:
        who = c.get("owner") or c.get("host") or "?"
        lines.append(f"  - {c.get('path')} — {who}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "context"
    try:
        if cmd == "pretooluse":
            sys.exit(cmd_pretooluse())
        sys.exit(cmd_context())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # 任何异常都放行，绝不阻断 Claude


if __name__ == "__main__":
    main()
