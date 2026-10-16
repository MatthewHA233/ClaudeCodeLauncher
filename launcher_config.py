"""三个启动器共享的配置读写：原子写入 + 跨盘镜像，任一磁盘写满都不会丢配置。"""
import json
import os
import tempfile
from pathlib import Path

PRIMARY_PATH = Path.home() / ".claude_launcher_config.json"
# 镜像放在启动器目录（Windows 上在 D 盘），与 C 盘主配置互为备份
MIRROR_PATH = Path(__file__).resolve().parent / ".launcher_config_mirror.json"
CONFIG_PATHS = (PRIMARY_PATH, MIRROR_PATH)


def _read_valid(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        mtime = path.stat().st_mtime
    except (OSError, ValueError):
        return None
    return (mtime, data) if isinstance(data, dict) else None


def load_config(defaults):
    """返回主配置与镜像中较新的有效那份；都不可用时返回 defaults。"""
    candidates = [c for c in map(_read_valid, CONFIG_PATHS) if c is not None]
    if not candidates:
        return defaults
    return max(candidates, key=lambda c: c[0])[1]


def _write_atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_config(config):
    """写入主配置和镜像，返回失败信息列表（空列表表示全部成功）。"""
    text = json.dumps(config, ensure_ascii=False, indent=2)
    errors = []
    for path in CONFIG_PATHS:
        try:
            _write_atomic(path, text)
        except OSError as e:
            errors.append(f"{path}: {e}")
    return errors
