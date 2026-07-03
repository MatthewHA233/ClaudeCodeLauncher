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

# 中文 Windows 上 Python 的 stdin/stdout 默认 GBK，而 Claude Code 与 hook 之间收发的
# 都是 UTF-8：不重配的话，中文路径经 stdin 变 mojibake（_git_root 找不到仓库 → 误判
# 仓库外 → key 退化裸文件名），stdout 里的 emoji 直接 UnicodeEncodeError 静默丢注入。
try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VERSION = "2.1.0"  # 2.1: 仓库外不上报/不注入、同内容去重防重复注入、日志自动修剪、worktree 支持

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
    """从 path 向上找含 .git 的目录；找不到返回 None。
    .git 可能是目录(普通仓库)也可能是文件(worktree/submodule 的 gitdir 指针)，都算。"""
    cur = os.path.dirname(path) if os.path.isfile(path) else path
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _git_dir(git_root):
    """root/.git 的真实 git 目录。普通仓库 .git 就是目录；worktree/submodule 的 .git
    是「gitdir: 指针」文件，解析指向的目录。解析不了返回 None。"""
    g = os.path.join(git_root, ".git")
    if os.path.isdir(g):
        return g
    try:
        with open(g, "r", encoding="utf-8", errors="ignore") as f:
            line = f.read().strip()
        if line.startswith("gitdir:"):
            gd = line[len("gitdir:"):].strip()
            if not os.path.isabs(gd):
                gd = os.path.normpath(os.path.join(git_root, gd))
            return gd
    except Exception:
        pass
    return None


def _repo_id(git_root):
    """仓库稳定标识：读 .git/config 的 remote origin url 取 'owner/repo'（跨机一致，
    不受本地文件夹名影响）；取不到回退文件夹名。纯文件读，不调 git 命令。
    worktree 的 config 在主仓库 git 目录（顺 commondir 找过去）。"""
    import re
    gd = _git_dir(git_root)
    cfg = os.path.join(gd, "config") if gd else os.path.join(git_root, ".git", "config")
    if gd and not os.path.exists(cfg):
        try:
            cd = (Path(gd) / "commondir").read_text(encoding="utf-8").strip()
            cfg = os.path.normpath(os.path.join(gd, cd, "config"))
        except Exception:
            pass
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
        gd = _git_dir(root)
        if not gd:
            return ""
        with open(os.path.join(gd, "HEAD"), "r", encoding="utf-8") as f:
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


LOG_FILE = Path.home() / ".claude" / "claim_inject_log.jsonl"
LOG_TRIM_BYTES = 2_000_000  # 超过即修剪（每条 prompt 都追加一行，不修剪会无限长）
LOG_KEEP_DAYS = 7
STATE_FILE = Path.home() / ".claude" / "claim_inject_state.json"  # 每会话上次注入内容的指纹（去重用）


def _log_inject(event, session_id, raw_claims, injected_text, skipped=""):
    """把每次注入记到本地日志(jsonl 不记 hook 注入,我们自己记),供实时可视化。
    记两样：registry 返回的【原始数据】+ 实际拼进上下文的【注入文本】。
    skipped 非空 = 本次没注入及其原因（去重跳过/不在项目内），前端照样能核对。"""
    try:
        rec = {
            "ts": int(time.time()),
            "event": event,
            "session_id": session_id,
            "raw_claims": raw_claims,     # registry 原样返回了什么(查投毒)
            "injected": injected_text,    # 实际注入 Claude 上下文的文本
        }
        if skipped:
            rec["skipped"] = skipped
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _trim_log()
    except Exception:
        pass


def _trim_log():
    """日志超限时只留最近 N 天（仍超则只留末 4000 行），临时文件原子替换。"""
    try:
        if LOG_FILE.stat().st_size <= LOG_TRIM_BYTES:
            return
        cutoff = int(time.time()) - LOG_KEEP_DAYS * 86400
        kept = []
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    if int(json.loads(line).get("ts") or 0) >= cutoff:
                        kept.append(line)
                except Exception:
                    continue
        if len(kept) > 4000:
            kept = kept[-4000:]
        tmp = str(LOG_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
        os.replace(tmp, LOG_FILE)
    except Exception:
        pass


def _state_get(session_id):
    """取该会话上次注入内容的指纹（没有则空串）。"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f) or {}
        return ((st.get(session_id) or {}).get("hash")) or ""
    except Exception:
        return ""


def _state_set(session_id, h):
    """记录该会话本次注入内容的指纹；顺手清 2 天没动静的会话。原子替换。"""
    if not session_id:
        return
    try:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f) or {}
        except Exception:
            st = {}
        now = int(time.time())
        st[session_id] = {"hash": h, "ts": now}
        st = {k: v for k, v in st.items()
              if now - int((v or {}).get("ts") or 0) <= 172800}
        tmp = str(STATE_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
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
    # 仓库外文件不上报：其 key 会退化成裸文件名，跨项目/跨机器全局撞车（不同项目的
    # 同名文件互相覆盖、互相注入 → 正是 ghidra-re-plan.md 串进别项目那类污染的根源）。
    # 协作感知只对「同一个 git 项目」有意义，仓库外没有协作场景。
    try:
        if _git_root(os.path.abspath(fp)) is None:
            return 0
    except Exception:
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
    - 只感知【同一个 git 项目(owner/repo)】的占用；仓库外会话没有协作范围 → 不注入。
    - 按 session_id 排除自己这个会话（同机其他会话仍显示）。
    - 同内容去重：UserPromptSubmit 每条都触发，内容(文件/机器/分支集合)没变就不再
      重复注入 —— 反复注入同样几行正是上下文污染。SessionStart 不去重(上下文刚重建)。
    - 每次都落注入日志（含跳过原因），供实时可视化 + 查投毒。"""
    data = _read_stdin_json()
    me_session = (data.get("session_id") or "").strip()
    event = data.get("hook_event_name") or "context"
    cwd = data.get("cwd") or os.getcwd()
    my_repo = _my_repo(cwd)       # 当前会话所属 git 项目(owner/repo)
    if not my_repo:
        # 仓库外会话（桌面/临时目录/ghidra 分析这类）：没有可协作的项目范围，不拉不注入
        _log_inject(event, me_session, [], "", skipped="会话不在 git 项目内，无协作感知范围")
        return 0
    base = _registry_url()
    if not base:
        return 0
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
        # 项目过滤：claim key 形如 "owner/repo/相对路径"，按前缀匹配同项目
        path = c.get("path") or ""
        if not path.startswith(my_repo + "/"):
            continue
        others.append(c)
    injected = ""
    fingerprint = ""
    if others:
        key_items = sorted(
            [[c.get("path") or "", c.get("machine_id") or "", c.get("branch") or ""] for c in others]
        )
        fingerprint = hashlib.sha1(
            json.dumps(key_items, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
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
    # 同内容去重（仅 UserPromptSubmit；指纹=文件/机器/分支集合，时间变化不算变）。
    # 集合变空会把指纹清掉 → 淡出后再出现会重新注入。
    skipped = ""
    if event == "UserPromptSubmit" and me_session and fingerprint \
            and fingerprint == _state_get(me_session):
        skipped = "内容与上次注入相同，跳过重复注入"
        injected = ""
    else:
        _state_set(me_session, fingerprint)
    # 落日志：registry 原始返回 + 实际注入文本 + 跳过原因（没注入也记，便于核对）
    _log_inject(event, me_session, raw_claims, injected, skipped)
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
