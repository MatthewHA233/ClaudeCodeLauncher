#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

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

        self.codex_key = "sessions/2026/07/12/rollout-active.jsonl"
        self.event_image = base / "screenshots" / "event.png"
        self.tool_image = base / "screenshots" / "tool.jpg"
        self.unreferenced_image = base / "private" / "secret.png"
        for fp in (self.event_image, self.tool_image, self.unreferenced_image):
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(b"test-image-bytes")
        wrapper = (
            "const r=await tools.view_image({path:"
            + json.dumps(str(self.tool_image))
            + ',detail:"original"}); image(r.image_url);'
        )
        codex_file.write_text(
            "\n".join(
                json.dumps(item)
                for item in (
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "local_images": [str(self.event_image)],
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "input": wrapper,
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{
                                "type": "input_text",
                                "text": f"ordinary text mentions {self.unreferenced_image}",
                            }],
                        },
                    },
                )
            )
            + "\n",
            encoding="utf-8",
        )

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

    def test_codex_image_must_be_referenced_by_the_selected_rollout(self):
        self.assertEqual(
            relay._resolve_codex_image(self.codex_key, str(self.event_image)),
            self.event_image.resolve(),
        )
        self.assertEqual(
            relay._resolve_codex_image(self.codex_key, str(self.tool_image)),
            self.tool_image.resolve(),
        )
        self.assertIsNone(
            relay._resolve_codex_image(self.codex_key, str(self.unreferenced_image))
        )
        self.assertIsNone(
            relay._resolve_codex_image(
                "archived_sessions/rollout-old.jsonl", str(self.event_image)
            )
        )

    def test_raw_image_endpoint_returns_bytes_and_hides_unreferenced_files(self):
        server = relay.SessionHTTPServer(("127.0.0.1", 0), relay.RelayHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}/raw/image?"
            common = {"provider": "codex", "key": self.codex_key}
            with urlopen(
                base + urlencode({**common, "path": str(self.event_image)}),
                timeout=3,
            ) as response:
                self.assertEqual(response.read(), b"test-image-bytes")
                self.assertEqual(response.headers.get_content_type(), "image/png")
            with self.assertRaises(HTTPError) as blocked:
                urlopen(
                    base + urlencode({**common, "path": str(self.unreferenced_image)}),
                    timeout=3,
                )
            self.assertEqual(blocked.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
