# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import claude_launcher
import console_typer
import launcher_queue


@unittest.skipIf(os.name == "nt", "fcntl / termios 仅 Unix 可用")
class TypeMacosTest(unittest.TestCase):
    def typed_bytes(self, text):
        sent = []
        with mock.patch("builtins.open", mock.mock_open()), \
                mock.patch("fcntl.ioctl", side_effect=lambda fd, op, byte: sent.append(byte)), \
                mock.patch.object(console_typer.time, "sleep"):
            console_typer._type_macos(text, initial_delay=0)
        return b"".join(sent)

    def test_chinese_and_emoji_keep_utf8_bytes(self):
        self.assertEqual(self.typed_bytes("你好🚀 ok").decode("utf-8"), "你好🚀 ok")

    def test_never_injects_carriage_return_or_trailing_newline(self):
        typed = self.typed_bytes("第一行\r\n第二行\r\n")
        self.assertNotIn(b"\r", typed)
        self.assertEqual(typed.decode("utf-8"), "第一行\n第二行")


class CanTypeTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "sys.platform 分支仅 Unix 走到")
    def test_platforms(self):
        with mock.patch.object(console_typer.sys, "platform", "linux"):
            self.assertFalse(console_typer.can_type())
        with mock.patch.object(console_typer.sys, "platform", "darwin"), \
                mock.patch("builtins.open", side_effect=OSError("没有控制终端")):
            self.assertFalse(console_typer.can_type())
        with mock.patch.object(console_typer.sys, "platform", "darwin"), mock.patch("builtins.open", mock.mock_open()):
            self.assertTrue(console_typer.can_type())


class DraftWatcherTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(launcher_queue, "QUEUE_PATH", Path(tmp.name) / "launcher_queue.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.launcher = claude_launcher.ClaudeLauncher.__new__(claude_launcher.ClaudeLauncher)

    def test_draft_stays_queued_when_typing_is_unavailable(self):
        launcher_queue.push("sess", "留在队列里", "d1")
        with mock.patch.object(console_typer, "can_type", return_value=False):
            stop = self.launcher._start_draft_watcher("claude --resume sess", "/tmp")
        self.assertIsNone(stop)
        self.assertEqual(launcher_queue.pop("sess"), "留在队列里")


if __name__ == "__main__":
    unittest.main()
