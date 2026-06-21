#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨机文件占用 claim —— 中继侧只负责存「registry 地址」。

仲裁（先来后到）全在主控机的 Claude Usage Monitor（Rust，绑 0.0.0.0:47801）里，本中继不参与。
本机的 PreToolUse hook（~/.claude/hooks/claim_hook.py）需要知道往哪台机器 acquire：
主控机会把自己的局域网地址 POST 到本机中继的 /claims/set_registry，中继据此写
~/.claude/claim_registry.json，hook 直接读该文件（同机，不必再发 HTTP）。

文件：~/.claude/claim_registry.json  {"version": 1, "url": "http://192.168.x.x:47801"}
读改写用「临时文件 + os.replace」尽量原子；异常一律静默。
"""
import os
import json
import tempfile
from pathlib import Path

REGISTRY_PATH = Path.home() / ".claude" / "claim_registry.json"


def get_registry():
    """读取下发来的 registry URL；无则 None。"""
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        url = (data or {}).get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    except Exception:
        pass
    return None


def set_registry(url):
    """写入主控机下发的 registry URL。"""
    if not isinstance(url, str) or not url.strip():
        return False
    tmp = None
    try:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(REGISTRY_PATH.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "url": url.strip()}, f, ensure_ascii=False)
        os.replace(tmp, REGISTRY_PATH)
        return True
    except Exception:
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False
