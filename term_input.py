"""终端按键 + 鼠标输入（xterm SGR 鼠标上报），Windows / macOS 通用。

read_input() 返回：'UP' / 'DOWN' / 'LEFT' / 'RIGHT' / 'ENTER' / 'ESC'、单个字符，
或 MouseEvent（仅在 mouse_mode() 内才会出现）；无法识别时返回 None。
"""
import atexit
import codecs
import contextlib
import io
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import namedtuple

if os.name == "nt":
    import ctypes
    from ctypes import wintypes
else:
    import select
    import termios

MouseEvent = namedtuple("MouseEvent", "kind row col")  # kind: click / wheel_up / wheel_down

_ESC_TIMEOUT = 0.05
_MOUSE_ON = "\x1b[?1000h\x1b[?1006h"
_MOUSE_OFF = "\x1b[?1000l\x1b[?1006l"
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_ARROWS = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}
_WIN_ARROWS = {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}

_mouse_depth = 0
_restore = None  # 退出鼠标模式时的恢复函数
_reassert = None  # 控制台模式被外部改掉时重新设置（仅 Windows）


# ---------- 底层读字符 ----------

if os.name == "nt":
    # Windows Terminal 下鼠标多以 MOUSE_EVENT 记录送达（需 ENABLE_MOUSE_INPUT），
    # msvcrt.getwch 会丢弃这类记录，所以直接读取原始输入记录。
    class _COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class _KEY_EVENT(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                    ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                    ("uChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

    class _MOUSE_EVENT(ctypes.Structure):
        _fields_ = [("dwMousePosition", _COORD), ("dwButtonState", wintypes.DWORD),
                    ("dwControlKeyState", wintypes.DWORD), ("dwEventFlags", wintypes.DWORD)]

    class _EVENT(ctypes.Union):
        _fields_ = [("KeyEvent", _KEY_EVENT), ("MouseEvent", _MOUSE_EVENT)]

    class _INPUT_RECORD(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT)]

    class _SMALL_RECT(ctypes.Structure):
        _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                    ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]

    class _CSBI(ctypes.Structure):
        _fields_ = [("dwSize", _COORD), ("dwCursorPosition", _COORD), ("wAttributes", wintypes.WORD),
                    ("srWindow", _SMALL_RECT), ("dwMaximumWindowSize", _COORD)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.GetStdHandle.argtypes = [wintypes.DWORD]
    _k32.GetStdHandle.restype = wintypes.HANDLE
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_INPUT_RECORD),
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _k32.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_CSBI)]
    _k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.FlushConsoleInputBuffer.argtypes = [wintypes.HANDLE]

    _STD_INPUT, _STD_OUTPUT = wintypes.DWORD(-10).value, wintypes.DWORD(-11).value
    _VK_ARROWS = {0x26: "UP", 0x28: "DOWN", 0x25: "LEFT", 0x27: "RIGHT"}

    def _viewport_pos(pos):
        info = _CSBI()
        if _k32.GetConsoleScreenBufferInfo(_k32.GetStdHandle(_STD_OUTPUT), ctypes.byref(info)):
            return pos.Y - info.srWindow.Top + 1, pos.X - info.srWindow.Left + 1
        return pos.Y + 1, pos.X + 1

    def _record_to_mouse(m):
        flags, state = m.dwEventFlags, m.dwButtonState
        row, col = _viewport_pos(m.dwMousePosition)
        if flags & 0x4:  # MOUSE_WHEELED，高 16 位为有符号滚动量
            up = ctypes.c_short(state >> 16).value > 0
            return MouseEvent("wheel_up" if up else "wheel_down", row, col)
        if flags in (0, 0x2) and state & 0x1:  # 左键按下 / 双击的第二次按下
            return MouseEvent("click", row, col)
        return None

    def _read_char(timeout=None):
        """返回单个字符、方向键名或 MouseEvent；超时返回 None。"""
        handle = _k32.GetStdHandle(_STD_INPUT)
        end = None if timeout is None else time.monotonic() + timeout
        rec, count = _INPUT_RECORD(), wintypes.DWORD()
        while True:
            # 分段等待，让 Ctrl+C 能及时生效
            wait_ms = 100 if end is None else max(0, int((end - time.monotonic()) * 1000))
            if _k32.WaitForSingleObject(handle, wait_ms) != 0:
                if end is not None and time.monotonic() >= end:
                    return None
                continue
            if not _k32.ReadConsoleInputW(handle, ctypes.byref(rec), 1, ctypes.byref(count)):
                return None
            if rec.EventType == 1:  # KEY_EVENT
                key = rec.Event.KeyEvent
                if key.bKeyDown:
                    if key.uChar and key.uChar != "\x00":
                        return key.uChar
                    if key.wVirtualKeyCode in _VK_ARROWS:
                        return _VK_ARROWS[key.wVirtualKeyCode]
            elif rec.EventType == 2:  # MOUSE_EVENT
                event = _record_to_mouse(rec.Event.MouseEvent)
                if event:
                    return event

    @contextlib.contextmanager
    def _key_mode():
        yield
else:
    _decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def _read_char(timeout=None):
        fd = sys.stdin.fileno()
        while True:
            if timeout is not None and not select.select([fd], [], [], timeout)[0]:
                return None
            data = os.read(fd, 1)
            if not data:
                return None
            ch = _decoder.decode(data)
            if ch:
                return ch

    def _cbreak_attrs(fd):
        attrs = termios.tcgetattr(fd)
        attrs[3] &= ~(termios.ICANON | termios.ECHO)
        attrs[6][termios.VMIN] = 1
        attrs[6][termios.VTIME] = 0
        return attrs

    @contextlib.contextmanager
    def _key_mode():
        if _mouse_depth:  # mouse_mode 已经切到 cbreak
            yield
            return
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        termios.tcsetattr(fd, termios.TCSANOW, _cbreak_attrs(fd))
        try:
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ---------- 解析 ----------

def _parse_mouse(button, col, row, pressed):
    if button == 64:
        return MouseEvent("wheel_up", row, col)
    if button == 65:
        return MouseEvent("wheel_down", row, col)
    if pressed and (button & ~(4 | 8 | 16)) == 0:  # 左键按下（允许带修饰键）
        return MouseEvent("click", row, col)
    return None


def _next_char(timeout):
    """转义序列内部只接受普通字符，遇到鼠标记录 / 方向键名视为序列中断。"""
    c = _read_char(timeout)
    return c if isinstance(c, str) and len(c) == 1 else None


def _read_escape():
    nxt = _read_char(_ESC_TIMEOUT)
    if nxt is None:
        return "ESC"
    if not (isinstance(nxt, str) and len(nxt) == 1):  # ESC 后紧跟方向键 / 鼠标：ESC 单独生效
        return "ESC"
    if nxt == "O":  # SS3 方向键
        return _ARROWS.get(_next_char(_ESC_TIMEOUT) or "")
    if nxt != "[":
        return "ESC"

    seq = ""
    while True:
        c = _next_char(_ESC_TIMEOUT)
        if c is None:
            return None
        seq += c
        if "\x40" <= c <= "\x7e":
            break

    if seq == "M":  # 旧式 X10 鼠标：后跟 3 个字节
        raw = [_next_char(_ESC_TIMEOUT) for _ in range(3)]
        if None in raw:
            return None
        b, x, y = (ord(ch) - 32 for ch in raw)
        return _parse_mouse(b, x, y, (b & 3) != 3)
    if seq.startswith("<") and seq[-1] in "Mm":  # SGR 鼠标
        try:
            b, x, y = (int(p) for p in seq[1:-1].split(";"))
        except ValueError:
            return None
        return _parse_mouse(b, x, y, seq[-1] == "M")
    return _ARROWS.get(seq[-1])


_last_click = (0.0, None)


def _dedupe(event):
    """同一次点击若以 MOUSE_EVENT 记录和 VT 序列各送达一次，只保留一次。"""
    global _last_click
    if event is None or event.kind != "click":
        return event
    now = time.monotonic()
    last_time, last_event = _last_click
    _last_click = (now, event)
    return None if event == last_event and now - last_time < 0.05 else event


def _read_token():
    ch = _read_char()
    if ch is None or isinstance(ch, MouseEvent):
        return ch
    if len(ch) > 1:  # Windows 虚拟键（方向键）
        return ch
    if ch in ("\x00", "\xe0"):  # 旧式控制台方向键前缀
        return _WIN_ARROWS.get(_next_char(None) or "")
    if ch == "\x1b":
        return _read_escape()
    if ch in ("\r", "\n"):
        return "ENTER"
    return ch


def read_input():
    with _key_mode():
        token = _read_token()
    return _dedupe(token) if isinstance(token, MouseEvent) else token


# ---------- 鼠标模式 ----------

def _write_raw(text):
    out = sys.__stdout__
    out.write(text)
    out.flush()


def _enable_windows():
    k32 = _k32
    h_in, h_out = k32.GetStdHandle(_STD_INPUT), k32.GetStdHandle(_STD_OUTPUT)
    in_mode, out_mode = wintypes.DWORD(), wintypes.DWORD()
    if not (k32.GetConsoleMode(h_in, ctypes.byref(in_mode))
            and k32.GetConsoleMode(h_out, ctypes.byref(out_mode))):
        return None
    global _reassert
    mouse_input, quick_edit, extended, vt_input = 0x0010, 0x0040, 0x0080, 0x0200
    new_mode = (in_mode.value | mouse_input | extended | vt_input) & ~quick_edit
    if not k32.SetConsoleMode(h_in, new_mode):
        # 老系统不支持 VT 输入时，退回只用 MOUSE_EVENT 记录
        new_mode &= ~vt_input
        if not k32.SetConsoleMode(h_in, new_mode):
            return None
    k32.SetConsoleMode(h_out, out_mode.value | 0x0004)  # VT 输出处理

    def reassert():
        current = wintypes.DWORD()
        if k32.GetConsoleMode(h_in, ctypes.byref(current)) and current.value != new_mode:
            k32.SetConsoleMode(h_in, new_mode)
    _reassert = reassert

    def restore():
        k32.FlushConsoleInputBuffer(h_in)
        k32.SetConsoleMode(h_in, in_mode.value)
        k32.SetConsoleMode(h_out, out_mode.value)
    return restore


def _enable_unix():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    termios.tcsetattr(fd, termios.TCSANOW, _cbreak_attrs(fd))

    def restore():
        termios.tcflush(fd, termios.TCIFLUSH)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return restore


def _disable():
    global _restore, _reassert
    if _restore is None:
        return
    _write_raw(_MOUSE_OFF)
    time.sleep(0.03)  # 让已在途中的鼠标事件到达，再一起清掉
    restore, _restore, _reassert = _restore, None, None
    restore()


def clear_screen():
    """清屏。鼠标模式中不能启动 cls 子进程：cmd.exe 会清掉控制台的鼠标输入标志。"""
    if _restore is not None:
        _write_raw("\x1b[2J\x1b[3J\x1b[H")
    else:
        os.system("cls" if os.name == "nt" else "clear")


atexit.register(_disable)


@contextlib.contextmanager
def mouse_mode():
    """在 with 块内开启鼠标上报；退出时关闭并清空输入缓冲，避免残留事件漏给后续程序。"""
    global _mouse_depth, _restore
    if _mouse_depth == 0 and sys.stdin.isatty() and sys.__stdout__.isatty():
        try:
            _restore = _enable_windows() if os.name == "nt" else _enable_unix()
        except Exception:
            _restore = None
        if _restore is not None:
            _write_raw(_MOUSE_ON)
    _mouse_depth += 1
    try:
        yield
    finally:
        _mouse_depth -= 1
        if _mouse_depth == 0:
            _disable()


# ---------- 菜单布局与鼠标动作 ----------

def _display_width(text):
    width = 0
    for ch in _ANSI_RE.sub("", text):
        if unicodedata.combining(ch) or ch in "️‍":
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


class MenuLayout:
    """记录菜单输出在屏幕上的位置：每个选项占的行，以及底部提示栏里各按键文字的行列。
    行列均从 1 开始，已考虑长行自动换行和内容超出终端高度时的滚屏。"""

    def __init__(self, text, marks, hotkeys=()):
        cols, lines = shutil.get_terminal_size()
        self._cols = max(cols, 1)
        self._text = text
        self._starts, row = [], 0
        for line in text.split("\n"):
            self._starts.append(row)
            row += max(1, -(-_display_width(line) // self._cols))
        self._offset = max(0, row - lines)

        self.option_rows = [(self._row_of(a), self._row_of(b) - 1) for a, b in zip(marks, marks[1:])]
        self.hotspots = []
        footer = marks[-1] if marks else 0
        for label, key in hotkeys:
            pos = text.find(label, footer)
            if pos < 0:
                continue
            col0 = _display_width(text[text.rfind("\n", 0, pos) + 1:pos])
            row = self._starts[text.count("\n", 0, pos)] + col0 // self._cols - self._offset + 1
            col = col0 % self._cols + 1
            self.hotspots.append((row, col, col + _display_width(label) - 1, key))

    def _row_of(self, pos):
        return self._starts[self._text.count("\n", 0, pos)] - self._offset + 1

    def option_at(self, row):
        for i, (first, last) in enumerate(self.option_rows):
            if first <= row <= last:
                return i
        return None

    def hotkey_at(self, row, col):
        for r, first, last, key in self.hotspots:
            if r == row and first <= col <= last:
                return key
        return None


def capture_menu(render, hotkeys=()):
    """调用 render(mark) 绘制菜单：mark() 需在每个选项前和最后一个选项后各调用一次。
    hotkeys 为底部提示栏中可点击的 (文字, 按键名)。输出整体写出（减少闪烁），返回 MenuLayout。"""
    marks, buf = [], io.StringIO()
    with contextlib.redirect_stdout(buf):
        render(lambda: marks.append(buf.tell()))
    text = buf.getvalue()
    sys.stdout.write(text)
    sys.stdout.flush()
    if _reassert is not None:
        _reassert()
    return MenuLayout(text, marks, hotkeys)


_last_page_turn = 0.0


def _page_turn_ready(interval=0.25):
    """滚轮翻页节流：触控板惯性滚动会连续产生大量滚轮事件，避免一下翻过好几页。"""
    global _last_page_turn
    now = time.monotonic()
    if now - _last_page_turn < interval:
        return False
    _last_page_turn = now
    return True


def menu_action(event, layout, selected, paged):
    """把鼠标事件翻译成菜单动作：('select', 序号) 只移动高亮；('key', 按键名) 按键盘按键处理；
    None 表示忽略（无需重画）。点已选中的项 = 确认；paged 时滚轮翻页，否则上下移动。"""
    if event.kind == "click":
        hit = layout.option_at(event.row)
        if hit is not None:
            return ("key", "ENTER") if hit == selected else ("select", hit)
        key = layout.hotkey_at(event.row, event.col)
        return ("key", key) if key else None
    up = event.kind == "wheel_up"
    if paged:
        return ("key", "LEFT" if up else "RIGHT") if _page_turn_ready() else None
    return ("key", "UP" if up else "DOWN")
