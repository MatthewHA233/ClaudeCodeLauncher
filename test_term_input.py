# -*- coding: utf-8 -*-
import os
import sys
import unittest

import term_input

if os.name != "nt":
    import termios


@unittest.skipIf(os.name == "nt", "pty 仅 Unix 可用")
class ReadInputPtyTest(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = os.openpty()
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        # 关回显：没人读主端时，回显积压会让 tcsetattr(TCSADRAIN) 一直等下去
        attrs = termios.tcgetattr(self.slave)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self.slave, termios.TCSANOW, attrs)
        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = os.fdopen(os.dup(self.slave), "r")
        self.addCleanup(sys.stdin.close)

    def feed(self, data):
        os.write(self.master, data)

    def test_arrow_sequence_is_consumed_whole(self):
        self.feed(b"\x1b[Ax")
        self.assertEqual(term_input.read_input(), "UP")
        self.assertEqual(term_input.read_input(), "x")

    def test_nul_and_a_grave_do_not_swallow_next_key(self):
        for prefix in (b"\x00", "à".encode()):
            with self.subTest(prefix=prefix):
                self.feed(prefix + b"\n")
                self.assertEqual(term_input.read_input(), prefix.decode())
                self.assertEqual(term_input.read_input(), "ENTER")

    def test_sgr_mouse_click(self):
        self.feed(b"\x1b[<0;7;3M")
        self.assertEqual(term_input.read_input(), term_input.MouseEvent("click", 3, 7))

    def test_cbreak_keeps_ctrl_c_but_disables_suspend(self):
        attrs = term_input._cbreak_attrs(self.slave)
        self.assertTrue(attrs[3] & termios.ISIG)
        self.assertFalse(attrs[3] & (termios.ICANON | termios.ECHO | termios.IEXTEN))
        self.assertEqual(attrs[6][termios.VSUSP], os.fpathconf(self.slave, "PC_VDISABLE"))
        termios.tcsetattr(self.slave, termios.TCSANOW, attrs)  # 能被终端驱动接受


@unittest.skipIf(os.name == "nt", "os.pipe + select 仅 Unix 可用")
class ReadInputEofTest(unittest.TestCase):
    def test_eof_raises_instead_of_spinning_menu_loop(self):
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = os.fdopen(read_fd, "r")
        self.addCleanup(sys.stdin.close)
        with term_input.mouse_mode(), self.assertRaises(EOFError):  # 非 tty 时 mouse_mode 不动终端
            term_input.read_input()


if __name__ == "__main__":
    unittest.main()
