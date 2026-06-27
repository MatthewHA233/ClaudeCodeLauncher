#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Claude Code 跨机文件「协作感知」hook（自包含、纯标准库）。

感知层（不是锁）：各机只【报告】"我最近碰了哪个文件"，其他机【读到即知晓】——advisory、不拒绝、不阻断。
旧报告靠【新鲜度】自然淡出，无需任何显式解除。

由启动器铺到 ~/.claude/hooks/claim_hook.py，在 ~/.claude/settings.json 注册两处：
- PreToolUse(Edit|Write|MultiEdit): `python claim_hook.py pretooluse`
    改文件前向 registry 报告"我碰了这个文件"（POST /claims/report）。始终 exit 0，绝不阻断写码。
- SessionStart / UserPromptSubmit: `python claim_hook.py context`
    拉感知公告板（GET /claims/list，已按新鲜度过滤），把"别的会话/机器最近在改啥"注入 Claude 上下文。

registry 地址优先级：环境变量 CLAIM_REGISTRY_URL > ~/.claude/claim_registry.json（主控机下发） > 本机 127.0.0.1:47801（兜底）。
连不上 → 静默放行。owner 取 CLAIM_OWNER 或 hostname；machine_id 取 OS 原生稳定 id。

claim key = 「owner/repo + 相对仓库根路径」（读 .git/config 的 remote origin），保证跨机器同一文件 = 同一 key。
"""
import os
import sys
import json
import time
import socket
import platform
import hashlib
from pathlib import Path
from urllib import request as _req

VERSION = "2.0.0"  # 感知层版（旧版是锁模型）

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


def _repo_id(git_root):
    """仓库稳定标识：读 .git/config 的 remote origin url 取 'owner/repo'（跨机一致，
    不受本地文件夹名影响）；取不到回退文件夹名。纯文件读，不调 git 命令。"""
    import re
    cfg = os.path.join(git_root, ".git", "config")
    try:
        with open(cfg, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        m = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', text, re.S)
        if not m:
            m = re.search(r"url\s*=\s*(\S+)", text)  # 退而求其次：任意 remote 的 url
        if m:
            u = re.sub(r"\.git$", "", m.group(1).strip())
            m2 = re.search(r"([^/:]+/[^/]+)$", u)  # 取末尾 owner/repo
            if m2:
                return m2.group(1)
    except Exception:
        pass
    return os.path.basename(git_root.rstrip("/\\")) or "repo"


def _norm_path(fp):
    """claim key = 仓库标识/相对仓库根路径。仓库标识取 git remote origin 的 owner/repo
    （跨机一致，不靠本地文件夹名）；无 remote 回退文件夹名；不在仓库内则文件名。"""
    try:
        ap = os.path.abspath(fp)
    except Exception:
        return fp.replace("\\", "/")
    root = _git_root(ap)
    if root:
        rel = os.path.relpath(ap, root).replace("\\", "/")
        return f"{_repo_id(root)}/{rel}"
    return os.path.basename(ap)


def _my_repo(cwd):
    """当前会话所在 git 项目的 owner/repo（与 _norm_path 的前缀同口径）。
    跨机器/同 repo 多克隆(文件夹名不同)都归一到同一个 owner/repo → 统一协作感知。
    不在 git 项目里则 None（注入时兜底不按 repo 过滤）。"""
    try:
        root = _git_root(os.path.abspath(cwd or "."))
        return _repo_id(root) if root else None
    except Exception:
        return None


def _git_branch(path):
    """读 .git/HEAD 取当前分支名。同分支才是真冲突；别分支仅提示「对面在改别分支」、不影响。
    detached HEAD 取 commit 前缀；取不到返回空串。纯文件读，不调 git 命令。"""
    try:
        root = _git_root(os.path.abspath(path or "."))
        if not root:
            return ""
        with open(os.path.join(root, ".git", "HEAD"), "r", encoding="utf-8") as f:
            line = f.read().strip()
        prefix = "ref: refs/heads/"
        if line.startswith(prefix):
            return line[len(prefix):]
        return line[:12]  # detached HEAD：取 commit 前缀
    except Exception:
        return ""


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


def _ago(sec):
    """秒数 → 人话的"多久前"。"""
    if sec < 0:
        sec = 0
    if sec < 60:
        return "刚刚"
    if sec < 3600:
        return "%d分钟前" % (sec // 60)
    return "%d小时前" % (sec // 3600)


def _log_inject(event, session_id, raw_claims, injected_text):
    """把每次注入记到本地日志(jsonl 不记 hook 注入,我们自己记),供实时可视化。
    记两样：registry 返回的【原始数据】+ 实际拼进上下文的【注入文本】。"""
    try:
        rec = {
            "ts": int(time.time()),
            "event": event,
            "session_id": session_id,
            "raw_claims": raw_claims,     # registry 原样返回了什么(查投毒)
            "injected": injected_text,    # 实际注入 Claude 上下文的文本
        }
        logf = Path.home() / ".claude" / "claim_inject_log.jsonl"
        with open(logf, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------- 子命令 ----------

def cmd_report():
    """改文件前向 registry 报告"我碰了这个文件"。感知层：不拒绝、不阻断，始终 exit 0。"""
    base = _registry_url()
    if not base:
        return 0  # 没 registry → 静默放行
    data = _read_stdin_json()
    tool_input = data.get("tool_input") or {}
    fp = (tool_input.get("file_path") or "").strip()
    if not fp:
        return 0
    path = _norm_path(fp)
    try:
        _post(_join(base, "/claims/report"), {
            "path": path,
            "owner": _owner(),
            "machine_id": _machine_id(),
            "host": socket.gethostname(),
            "session_id": data.get("session_id") or "",
            "branch": _git_branch(fp),
        })
    except Exception:
        pass  # 连不上 → 静默（感知失败不影响写码）
    return 0


def cmd_context():
    """拉感知公告板，把"别的会话/机器最近在改啥"注入 Claude 上下文（advisory）。
    按 session_id 排除自己这个会话（同机其他会话仍显示）。
    每次都落注入日志（不管注没注），供实时可视化 + 查投毒。"""
    base = _registry_url()
    if not base:
        return 0
    data = _read_stdin_json()
    me_session = (data.get("session_id") or "").strip()
    event = data.get("hook_event_name") or "context"
    cwd = data.get("cwd") or os.getcwd()
    my_repo = _my_repo(cwd)       # 当前会话所属 git 项目(owner/repo)
    my_branch = _git_branch(cwd)  # 当前分支：区分"同分支真冲突" vs "别分支不影响"
    try:
        out = _get(_join(base, "/claims/list"))
    except Exception:
        return 0
    raw_claims = out.get("claims") or []
    now = int(time.time())
    others = []
    for c in raw_claims:
        sid = c.get("session_id") or ""
        if me_session and sid == me_session:
            continue  # 排除自己这个会话
        # 项目过滤：只感知【同一个 git 项目(owner/repo)】的占用。claim key 形如
        # "owner/repo/相对路径"，故按 "my_repo/" 前缀匹配。my_repo 取不到(当前不在
        # git 项目里)则兜底不过滤，避免误杀。别的项目改啥与本会话无关，不注入。
        path = c.get("path") or ""
        if my_repo and not path.startswith(my_repo + "/"):
            continue
        others.append(c)
    injected = ""
    if others:
        lines = ["👀 协作感知 · 同项目其他会话/机器最近在改："]
        for c in others:
            path = c.get("path") or "?"
            name = path.rsplit("/", 1)[-1] or path  # 只显文件名，简洁
            who = c.get("owner") or c.get("host") or "?"
            touched = int(c.get("last_touch") or c.get("heartbeat") or now)
            cbranch = (c.get("branch") or "").strip()
            # 别分支：仅提示「对面在改别分支」，标明不影响（同分支才是真冲突感知）
            note = " · (别分支 %s·不影响)" % cbranch if (cbranch and my_branch and cbranch != my_branch) else ""
            lines.append("   %s · %s · %s%s" % (name, who, _ago(now - touched), note))
        injected = "\n".join(lines)
    # 落日志：registry 原始返回 + 实际注入文本（即便没注入也记，便于查"registry 返回了啥"）
    _log_inject(event, me_session, raw_claims, injected)
    if injected:
        sys.stdout.write(injected + "\n")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "context"
    try:
        if cmd in ("pretooluse", "report"):
            sys.exit(cmd_report())
        sys.exit(cmd_context())  # context / 其它都走感知注入
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # 任何异常都放行，绝不阻断 Claude


if __name__ == "__main__":
    main()
