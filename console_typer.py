#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把文字逐字符「打」进当前控制台的输入缓冲区（不回车）。

Windows：用 WriteConsoleInputW 直接写控制台输入缓冲（CONIN$），claude 的 TUI
从中读到字符。不依赖窗口前台焦点（区别于 SendInput），即便用户切走窗口也只写进
这个控制台、不会误打到别处，更稳。
非 Windows：暂为 no-op（启动器主要在 Windows 用）。

约定：只填不发——不注入回车（\\r），尾部换行也清掉，避免误触发送。
失败一律静默，绝不影响启动器主流程。
"""
import os
import time


def _type_windows(text, per_char_delay=0.012, initial_delay=2.0):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    class CHAR_UNION(ctypes.Union):
        _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", ctypes.c_char)]

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("uChar", CHAR_UNION),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class INPUT_RECORD(ctypes.Structure):
        class _EVENT(ctypes.Union):
            _fields_ = [("KeyEvent", KEY_EVENT_RECORD)]
        _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT)]

    KEY_EVENT = 0x0001
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    # 明确 restype/argtypes，否则 64 位下句柄会被截断成无效值
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.WriteConsoleInputW.restype = wintypes.BOOL
    kernel32.WriteConsoleInputW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]

    # 拿真正的控制台输入句柄（CONIN$），失败回退到 STD_INPUT_HANDLE
    handle = kernel32.CreateFileW(
        "CONIN$", GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None,
    )
    if not handle or handle == INVALID_HANDLE:
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
    if not handle or handle == INVALID_HANDLE:
        return

    # 等 claude 的 TUI 起来（代理设置 + node 启动需要时间）
    time.sleep(initial_delay)

    # 去掉尾部换行 + 丢弃所有 \r，避免误触发送
    text = text.rstrip("\r\n").replace("\r", "")

    rec = INPUT_RECORD()
    rec.EventType = KEY_EVENT
    ke = rec.Event.KeyEvent
    ke.wRepeatCount = 1
    ke.wVirtualKeyCode = 0
    ke.wVirtualScanCode = 0
    ke.dwControlKeyState = 0
    written = wintypes.DWORD(0)

    # 按 UTF-16 码元逐个发送（正确处理中文与代理对）
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        code_unit = data[i] | (data[i + 1] << 8)
        ke.uChar.UnicodeChar = chr(code_unit)
        ke.bKeyDown = True
        kernel32.WriteConsoleInputW(handle, ctypes.byref(rec), 1, ctypes.byref(written))
        ke.bKeyDown = False
        kernel32.WriteConsoleInputW(handle, ctypes.byref(rec), 1, ctypes.byref(written))
        if per_char_delay:
            time.sleep(per_char_delay)


def type_text(text, **kwargs):
    """逐字符打字（不回车）。失败静默。"""
    if not text:
        return
    try:
        if os.name == "nt":
            _type_windows(text, **kwargs)
    except Exception:
        pass
