# -*- coding: utf-8 -*-
import contextlib
import io
import os
import unittest
from unittest import mock

import git_commit_organizer


class FakeProcess:
    returncode = 0

    def __init__(self):
        self.stdin = io.StringIO()
        self.stdin.close = lambda: None
        self.stdout = io.StringIO("ok\n")
        self.stderr = io.StringIO("")

    def poll(self):
        return 0


class CallAiAgentTest(unittest.TestCase):
    def run_agent(self, agent, platform_name=os.name):
        launcher = mock.Mock(config={"use_proxy": False})
        organizer = git_commit_organizer.GitCommitOrganizer.__new__(git_commit_organizer.GitCommitOrganizer)
        organizer.launcher = launcher
        organizer.show_loading_animation = mock.Mock()
        process = FakeProcess()
        seen = {}

        def popen(cmd, **kwargs):
            seen["cmd"] = cmd
            if "--prompt-file" in cmd:
                seen["path"] = cmd[cmd.index("--prompt-file") + 1]
                with open(seen["path"], encoding="utf-8") as f:
                    seen["file"] = f.read()
            return process

        with mock.patch.object(git_commit_organizer.os, "name", platform_name), \
                mock.patch.object(git_commit_organizer.subprocess, "Popen", side_effect=popen), \
                contextlib.redirect_stdout(io.StringIO()):
            result = organizer.call_ai_agent(os.getcwd(), "提示词", {}, "", agent)
        self.assertEqual(result, "ok")
        return seen, process.stdin.getvalue()

    def test_claude_uses_cmd_shim_only_on_windows(self):
        seen, stdin = self.run_agent("claude", "posix")
        self.assertEqual(seen["cmd"][0], "claude")
        self.assertEqual(stdin, "提示词")
        seen, _ = self.run_agent("claude", "nt")
        self.assertEqual(seen["cmd"][0], "claude.cmd")

    def test_codex_runs_non_interactive_and_reads_stdin(self):
        seen, stdin = self.run_agent("codex")
        self.assertEqual(seen["cmd"], ["codex", "exec", "-"])
        self.assertEqual(stdin, "提示词")

    def test_grok_gets_prompt_from_file_and_removes_it(self):
        seen, stdin = self.run_agent("grok")
        self.assertEqual(seen["file"], "提示词")
        self.assertEqual(stdin, "")
        self.assertFalse(os.path.exists(seen["path"]))


if __name__ == "__main__":
    unittest.main()
