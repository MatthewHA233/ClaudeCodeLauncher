#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""启动器「预备发言」队列：claude-switch 推来的待发草稿，按 session_id 暂存。

文件：~/.claude/launcher_queue.json
  {"version": 1, "queue": {"<session_id>": [{"id": "<uuid>", "text": "..."}, ...]}}

写入方：claude-switch —— 本机由 Rust 直写此文件；远程经薄中继 POST /queue/push 写入本机此文件。
读取方：本启动器 —— 进入对话时取该会话的下一条草稿、逐字符打字注入、并移除。
读改写用「临时文件 + os.replace」尽量原子；低频低并发，容忍偶发竞态（异常一律静默）。
"""
import os
import json
import tempfile
from pathlib import Path

QUEUE_PATH = Path.home() / ".claude" / "launcher_queue.json"


def _load():
    try:
        with open(QUEUE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("queue"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "queue": {}}


def _save(data):
    tmp = None
    try:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(QUEUE_PATH.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, QUEUE_PATH)
        return True
    except Exception:
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def pop(session_id):
    """取出并移除该会话队首草稿，返回文本；无则 None。"""
    if not session_id:
        return None
    data = _load()
    items = data.get("queue", {}).get(session_id) or []
    if not items:
        return None
    first = items.pop(0)
    if items:
        data["queue"][session_id] = items
    else:
        data["queue"].pop(session_id, None)
    _save(data)
    return first.get("text")


def push(session_id, text, draft_id=None):
    """追加一条草稿到该会话队列；同 draft_id 先去重（覆盖），避免重复推送堆积。"""
    if not session_id or not text:
        return False
    data = _load()
    q = data.setdefault("queue", {})
    items = q.setdefault(session_id, [])
    if draft_id is not None:
        items = [it for it in items if it.get("id") != draft_id]
    items.append({"id": draft_id, "text": text})
    q[session_id] = items
    return _save(data)
