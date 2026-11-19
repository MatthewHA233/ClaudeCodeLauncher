#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

import session_api_server as relay

# 终端常设 http_proxy，urllib 不会自动绕过回环地址
urlopen_direct = build_opener(ProxyHandler({})).open


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
            with urlopen_direct(
                base + urlencode({**common, "path": str(self.event_image)}),
                timeout=3,
            ) as response:
                self.assertEqual(response.read(), b"test-image-bytes")
                self.assertEqual(response.headers.get_content_type(), "image/png")
            with self.assertRaises(HTTPError) as blocked:
                urlopen_direct(
                    base + urlencode({**common, "path": str(self.unreferenced_image)}),
                    timeout=3,
                )
            self.assertEqual(blocked.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class RawSliceTests(unittest.TestCase):
    """/raw/file 增量模式：offset 续传 + slim 去掉解析器用不到的 api-request* 请求日志。"""

    USER = b'{"parentUuid":null,"type":"user","message":{"role":"user","content":"hi"}}\n'
    API = b'{"type":"api-request","params":{"safeguards":[{"big":"x"}]}}\n'
    BLOB = b'{"type":"api-request-blob","hash":"h","message":{}}\n'
    ASSISTANT = b'{"type":"assistant","message":{"content":[{"type":"text","text":"yo"}]}}\n'
    PARTIAL = b'{"type":"assistant","mess'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_projects = relay.PROJECTS_DIR
        self.addCleanup(setattr, relay, "PROJECTS_DIR", self.old_projects)
        relay.PROJECTS_DIR = Path(self.temp.name) / "projects"
        self.fp = relay.PROJECTS_DIR / "proj" / "s.jsonl"
        self.fp.parent.mkdir(parents=True)
        self.body = self.USER + self.API + self.BLOB + self.ASSISTANT + self.PARTIAL
        self.fp.write_bytes(self.body)
        self.complete_end = len(self.body) - len(self.PARTIAL)

    def test_slim_full_read_drops_api_request_lines_and_trailing_partial_line(self):
        start, end, size, data = relay._read_raw_slice(self.fp, 0, slim=True)
        self.assertEqual((start, end, size), (0, self.complete_end, len(self.body)))
        self.assertEqual(data, self.USER + self.ASSISTANT)

    def test_offset_on_line_boundary_returns_only_the_tail(self):
        offset = len(self.USER + self.API)
        start, end, _, data = relay._read_raw_slice(self.fp, offset, slim=False)
        self.assertEqual((start, end), (offset, self.complete_end))
        self.assertEqual(data, self.BLOB + self.ASSISTANT)

    def test_offset_at_end_returns_nothing_new(self):
        start, end, _, data = relay._read_raw_slice(self.fp, self.complete_end, slim=True)
        self.assertEqual((start, end, data), (self.complete_end, self.complete_end, b""))

    def test_invalid_offset_restarts_from_beginning(self):
        for bad in (3, len(self.body) + 10, -5):
            start, end, _, data = relay._read_raw_slice(self.fp, bad, slim=True)
            self.assertEqual((start, end), (0, self.complete_end), bad)
            self.assertEqual(data, self.USER + self.ASSISTANT)

    def test_endpoint_keeps_legacy_bytes_and_adds_range_headers_in_incremental_mode(self):
        server = relay.SessionHTTPServer(("127.0.0.1", 0), relay.RelayHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}/raw/file?"
            common = {"provider": "claude_code", "key": "proj/s.jsonl"}
            with urlopen_direct(base + urlencode(common), timeout=3) as response:
                self.assertEqual(response.read(), self.body)
                self.assertIsNone(response.headers.get("X-Raw-End"))
            offset = len(self.USER)
            query = urlencode({**common, "offset": offset, "slim": 1})
            with urlopen_direct(base + query, timeout=3) as response:
                self.assertEqual(response.read(), self.ASSISTANT)
                self.assertEqual(response.headers.get("X-Raw-Start"), str(offset))
                self.assertEqual(response.headers.get("X-Raw-End"), str(self.complete_end))
                self.assertEqual(response.headers.get("X-Raw-Size"), str(len(self.body)))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class SingletonBindTests(unittest.TestCase):
    def test_second_relay_cannot_bind_same_port(self):
        first = relay.SessionHTTPServer(("127.0.0.1", 0), relay.RelayHandler)
        self.addCleanup(first.server_close)
        with self.assertRaises(OSError):
            relay.SessionHTTPServer(("127.0.0.1", first.server_address[1]), relay.RelayHandler)

    @unittest.skipIf(os.name == "nt", "Windows 不开端口复用")
    def test_restart_right_after_serving_requests(self):
        """旧中继刚处理完请求就关闭，端口留着 TIME_WAIT，新中继仍要能 bind（launchd 重启场景）。"""
        old = relay.SessionHTTPServer(("127.0.0.1", 0), relay.RelayHandler)
        port = old.server_address[1]
        thread = threading.Thread(target=old.serve_forever, daemon=True)
        thread.start()
        urlopen_direct(f"http://127.0.0.1:{port}/api/ping", timeout=3).read()
        old.shutdown()
        old.server_close()
        thread.join(timeout=3)
        relay.SessionHTTPServer(("127.0.0.1", port), relay.RelayHandler).server_close()


@unittest.skipIf(os.name == "nt", "Windows 不做 mDNS 广播")
class AdvertiserLifetimeTests(unittest.TestCase):
    """中继无论怎么退出，广播都要跟着停：残留广播会以同一 mid 指向死端口，对端可能连过去。"""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.pidfile = base / "advertiser.pid"
        bin_dir = base / "bin"
        bin_dir.mkdir()
        # 替身：记下 pid 后常驻，代替 dns-sd / avahi-publish-service，不真的广播
        for name in ("dns-sd", "avahi-publish-service"):
            fake = bin_dir / name
            fake.write_text('#!/bin/sh\necho $$ > "$FAKE_PIDFILE"\nexec sleep 60\n', encoding="utf-8")
            fake.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "HOME": str(base), "FAKE_PIDFILE": str(self.pidfile)}

    def start_relay(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        proc = subprocess.Popen([sys.executable, relay.__file__, str(port)], env=self.env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(proc.kill)
        deadline = time.monotonic() + 10
        while not (self.pidfile.exists() and self.pidfile.read_text().strip()):
            if time.monotonic() > deadline:
                self.fail("广播替身没有启动")
            time.sleep(0.05)
        return proc, int(self.pidfile.read_text())

    def assert_gone(self, pid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        os.kill(pid, signal.SIGKILL)
        self.fail("中继退出后广播进程仍在")

    def test_advertiser_stops_however_relay_exits(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig.name):
                self.pidfile.unlink(missing_ok=True)
                proc, pid = self.start_relay()
                proc.send_signal(sig)
                proc.wait(timeout=5)
                self.assert_gone(pid)


if __name__ == "__main__":
    unittest.main()
