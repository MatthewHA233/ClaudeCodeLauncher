# -*- coding: utf-8 -*-
"""本机 token 用量计算（纯标准库），供薄中继 /api/token_summary 端点。

扫本机 ~/.claude/projects(Claude) + ~/.codex/sessions(Codex) 算 token，按
(date, provider, model) 聚合后传出，由对端 Claude Usage Monitor 跨机器汇总。

算法必须与 claude-switch 的 src-tauri/src/token_usage.rs **逐字段一致**：
- Claude: type=assistant 且有 usage；message.usage 取 input/cache_read/cache_creation/output；
  按 (message.id:requestId) **全局跨文件去重**；model 取 message.model 并 split('@')[0]；
  day 取 timestamp 前 10 字符(或 rfc3339→UTC date)。
- Codex: turn_context 记 current_model；event_msg+payload.type==token_count 取 info.last_token_usage；
  cache_read = max(cached_input_tokens, cache_read_input_tokens) 再 min(input)。
- 文件: 扫 mtime >= (since - 1day) 的 .jsonl，按 mtime 倒序取前 2000；Codex 去重文件名。
"""
import os
import json
from pathlib import Path
from datetime import datetime, date, timedelta, timezone

MAX_FILES_PER_PROVIDER = 2000


def _claude_roots():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR", "")
    roots = []
    if cfg.strip():
        for part in cfg.split(","):
            part = part.strip()
            if not part:
                continue
            p = Path(part)
            roots.append(p if p.name == "projects" else p / "projects")
    if roots:
        return roots
    home = Path.home()
    return [home / ".config" / "claude" / "projects", home / ".claude" / "projects"]


def _codex_roots():
    base = os.environ.get("CODEX_HOME", "").strip()
    base = Path(base) if base else (Path.home() / ".codex")
    return [base / "sessions", base / "archived_sessions"]


def _scan_floor_ts(since):
    """与 Rust epoch_seconds_for_scan_floor 一致：(since - 1day) 的 UTC 00:00 时间戳"""
    floor = since - timedelta(days=1)
    return datetime(floor.year, floor.month, floor.day, tzinfo=timezone.utc).timestamp()


def _recent_jsonl(root, since):
    floor = _scan_floor_ts(since)
    out = []
    if not root.exists():
        return out
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            fp = Path(dirpath) / fn
            try:
                st = fp.stat()
            except OSError:
                continue
            if st.st_mtime >= floor:
                out.append((fp, int(st.st_mtime)))
    out.sort(key=lambda x: (-x[1], str(x[0])))
    return [fp for fp, _ in out[:MAX_FILES_PER_PROVIDER]]


def _parse_day(ts):
    if not ts or not isinstance(ts, str):
        return None
    if len(ts) >= 10:
        try:
            return datetime.strptime(ts[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).date()
    except Exception:
        return None


def _norm_model(model, provider):
    model = (model or "").strip()
    if provider == "claude_code":
        return model.split("@")[0].strip()
    return model


def _i(d, k):
    try:
        return max(0, int(d.get(k) or 0))
    except (TypeError, ValueError):
        return 0


def _add(days, day, model, tot):
    if tot["input"] + tot["cache_read"] + tot["cache_create"] + tot["output"] == 0:
        return
    m = days.setdefault(day, {}).setdefault(
        model, {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0}
    )
    m["input"] += tot["input"]
    m["cache_read"] += tot["cache_read"]
    m["cache_create"] += tot["cache_create"]
    m["output"] += tot["output"]


def _scan_claude_file(fp, since, until, seen, days):
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"type":"assistant"' not in line or '"usage"' not in line:
                    continue
                try:
                    v = json.loads(line)
                except Exception:
                    continue
                if v.get("type") != "assistant":
                    continue
                day = _parse_day(v.get("timestamp"))
                if not day or day < since or day > until:
                    continue
                msg = v.get("message")
                if not isinstance(msg, dict):
                    continue
                model = msg.get("model")
                if not model or not isinstance(model, str):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                tot = {
                    "input": _i(usage, "input_tokens"),
                    "cache_read": _i(usage, "cache_read_input_tokens"),
                    "cache_create": _i(usage, "cache_creation_input_tokens"),
                    "output": _i(usage, "output_tokens"),
                }
                if tot["input"] + tot["cache_read"] + tot["cache_create"] + tot["output"] == 0:
                    continue
                model = _norm_model(model, "claude_code")
                mid = msg.get("id")
                rid = v.get("requestId")
                if mid and rid:
                    key = f"{mid}:{rid}"
                    if key in seen:
                        continue
                    seen.add(key)
                _add(days, str(day), model, tot)
    except OSError:
        pass


def _scan_codex_file(fp, since, until, days):
    current_model = None
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"token_count"' not in line and '"turn_context"' not in line:
                    continue
                try:
                    v = json.loads(line)
                except Exception:
                    continue
                t = v.get("type")
                if t == "turn_context":
                    pl = v.get("payload") or {}
                    m = pl.get("model") or (pl.get("info") or {}).get("model")
                    if m:
                        current_model = m
                elif t == "event_msg":
                    pl = v.get("payload")
                    if not isinstance(pl, dict) or pl.get("type") != "token_count":
                        continue
                    day = _parse_day(v.get("timestamp"))
                    if not day or day < since or day > until:
                        continue
                    info = pl.get("info") or {}
                    last = info.get("last_token_usage")
                    if not isinstance(last, dict):
                        continue
                    model = (
                        info.get("model")
                        or info.get("model_name")
                        or pl.get("model")
                        or v.get("model")
                        or current_model
                        or "gpt-5"
                    )
                    inp = _i(last, "input_tokens")
                    cr = max(_i(last, "cached_input_tokens"), _i(last, "cache_read_input_tokens"))
                    cc = _i(last, "cache_creation_input_tokens")
                    out = _i(last, "output_tokens")
                    cr = min(cr, inp)
                    tot = {"input": inp, "cache_read": cr, "cache_create": cc, "output": out}
                    if inp + cr + cc + out == 0:
                        continue
                    _add(days, str(day), _norm_model(model, "codex"), tot)
    except OSError:
        pass


def compute(since_days=400):
    """扫本机算 token，返回扁平行：
    {ok, days: [{date, provider, model, input_tokens, cache_read_tokens,
                 cache_creation_tokens, output_tokens}]}
    """
    since_days = max(1, min(int(since_days or 400), 3650))
    today = date.today()
    since = today - timedelta(days=since_days - 1)
    until = today

    # Claude：跨文件全局去重
    claude_days = {}
    seen = set()
    for root in _claude_roots():
        for fp in _recent_jsonl(root, since):
            _scan_claude_file(fp, since, until, seen, claude_days)

    # Codex：去重文件名（sessions / archived_sessions 可能重名）
    codex_days = {}
    seen_names = set()
    for root in _codex_roots():
        for fp in _recent_jsonl(root, since):
            if fp.name in seen_names:
                continue
            seen_names.add(fp.name)
            _scan_codex_file(fp, since, until, codex_days)

    rows = []
    for provider, dd in (("claude_code", claude_days), ("codex", codex_days)):
        for day, models in dd.items():
            for model, tot in models.items():
                rows.append({
                    "date": day,
                    "provider": provider,
                    "model": model,
                    "input_tokens": tot["input"],
                    "cache_read_tokens": tot["cache_read"],
                    "cache_creation_tokens": tot["cache_create"],
                    "output_tokens": tot["output"],
                })
    return {"ok": True, "days": rows}


if __name__ == "__main__":
    import sys
    sd = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    rep = compute(sd)
    tot = {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0}
    for r in rep["days"]:
        tot["input"] += r["input_tokens"]
        tot["cache_read"] += r["cache_read_tokens"]
        tot["cache_create"] += r["cache_creation_tokens"]
        tot["output"] += r["output_tokens"]
    print(f"近 {sd} 天：{len(rep['days'])} 行 (date×provider×model)")
    print(f"  input={tot['input']:,} cache_read={tot['cache_read']:,} "
          f"cache_create={tot['cache_create']:,} output={tot['output']:,}")
