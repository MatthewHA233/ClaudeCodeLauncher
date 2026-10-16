"""跨平台系统文件夹选择框：macOS 用 osascript，其余平台用 tkinter（Windows 上为资源管理器样式）。"""
import os
import subprocess
import sys


def _applescript_str(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _pick_with_osascript(title, initial_dir):
    script = f"POSIX path of (choose folder with prompt {_applescript_str(title)}"
    if initial_dir:
        script += f" default location (POSIX file {_applescript_str(initial_dir)} as alias)"
    script += ")"
    # 先 activate 自身，避免选择框被终端窗口挡住
    result = subprocess.run(["osascript", "-e", "activate", "-e", script],
                            capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    if "-128" in result.stderr:  # 用户取消
        return None
    raise RuntimeError(result.stderr.strip() or "osascript 执行失败")


def _pick_with_tk(title, initial_dir):
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 防止高分屏下对话框发虚
        except (AttributeError, OSError):
            pass
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=root, title=title,
                                       initialdir=initial_dir or None, mustexist=True)
    finally:
        root.destroy()


def pick_folder(title="选择项目文件夹", initial_dir=None):
    """弹出系统文件夹选择框，返回所选目录；用户取消返回 None，无法弹框时抛异常。"""
    if initial_dir and not os.path.isdir(initial_dir):
        initial_dir = None
    if sys.platform == "darwin":
        path = _pick_with_osascript(title, initial_dir)
    else:
        path = _pick_with_tk(title, initial_dir)
    return os.path.normpath(path) if path else None
