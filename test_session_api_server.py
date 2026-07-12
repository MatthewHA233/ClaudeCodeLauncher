#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

import session_api_server as relay


class RawProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.old_projects = relay.PROJECTS_DIR
        self.old_codex_home = relay.CODEX_HOME
        relay.PROJECTS_DIR = base / ".claude" / "projects"
        relay.CODEX_HOME = base / ".codex"

        claude_file = relay.PROJECTS_DIR / "project-a" / "claude-session.jsonl"
        codex_file = relay.CODEX_HOME / "sessions" / "2026" / "07" / "12" / "rollout-active.jsonl"
        archived_file = relay.CODEX_HOME / "archived_sessions" / "rollout-old.jsonl"
        for fp in (claude_file, codex_file, archived_file):
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text("{}\n", encoding="utf-8")

    def tearDown(self):
        relay.PROJECTS_DIR = self.old_projects
        relay.CODEX_HOME = self.old_codex_home
        self.temp.cleanup()

    def test_default_provider_keeps_legacy_claude_shape(self):
        files = relay._list_files()
        self.assertEqual([f["key"] for f in files], ["project-a/claude-session.jsonl"])
        self.assertEqual(files[0]["session_id"], "claude-session")

    def test_codex_lists_active_and_archived_rollouts(self):
        keys = sorted(f["key"] for f in relay._list_files(relay.CODEX_PROVIDER))
        self.assertEqual(
            keys,
            [
                "archived_sessions/rollout-old.jsonl",
                "sessions/2026/07/12/rollout-active.jsonl",
            ],
        )

    def test_resolve_key_is_provider_scoped_and_blocks_traversal(self):
        self.assertIsNotNone(
            relay._resolve_key(
                "sessions/2026/07/12/rollout-active.jsonl",
                relay.CODEX_PROVIDER,
            )
        )
        self.assertIsNone(
            relay._resolve_key("project-a/claude-session.jsonl", relay.CODEX_PROVIDER)
        )
        self.assertIsNone(
            relay._resolve_key("sessions/../auth.json", relay.CODEX_PROVIDER)
        )


if __name__ == "__main__":
    unittest.main()
