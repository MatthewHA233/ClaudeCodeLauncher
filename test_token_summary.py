# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import token_summary


def token_count(timestamp, input_tokens, cached_input_tokens, output_tokens):
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                }
            },
        },
    }


class TokenSummaryTests(unittest.TestCase):
    def test_codex_subagent_only_counts_usage_after_trigger_turn(self):
        records = [
            {
                "timestamp": "2026-07-30T08:00:00Z",
                "type": "session_meta",
                "payload": {
                    "thread_source": "subagent",
                    "source": {"subagent": {"thread_spawn": {"depth": 1}}},
                },
            },
            {
                "timestamp": "2026-07-30T08:00:01Z",
                "type": "turn_context",
                "payload": {"model": "gpt-test"},
            },
            token_count("2026-07-30T08:00:02Z", 1000, 900, 10),
            {
                "timestamp": "2026-07-30T08:00:03Z",
                "type": "inter_agent_communication_metadata",
                "payload": {"trigger_turn": True},
            },
            token_count("2026-07-30T08:00:04Z", 500, 450, 9),
            {
                "timestamp": "2026-07-30T08:00:05Z",
                "type": "inter_agent_communication_metadata",
                "payload": {"trigger_turn": True},
            },
            token_count("2026-07-30T08:00:06Z", 100, 80, 7),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )
            days = {}
            target = date(2026, 7, 30)
            token_summary._scan_codex_file(path, target, target, days)

        self.assertEqual(
            days,
            {
                "2026-07-30": {
                    "gpt-test": {
                        "input": 20,
                        "cache_read": 80,
                        "cache_create": 0,
                        "output": 7,
                    }
                }
            },
        )

    def test_compute_contract_advertises_token_schema(self):
        self.assertEqual(token_summary.TOKEN_SCHEMA_VERSION, 2)


if __name__ == "__main__":
    unittest.main()
