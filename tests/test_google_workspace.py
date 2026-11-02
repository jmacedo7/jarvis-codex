import json
import tempfile
import unittest
from pathlib import Path

from integrations.google_workspace import GoogleWorkspace, _event, _headers


class GoogleWorkspaceTests(unittest.TestCase):
    def test_missing_credentials_report_disconnected(self):
        with tempfile.TemporaryDirectory() as folder:
            result = GoogleWorkspace(Path(folder)).dashboard()
        self.assertEqual(result["status"], "needs_credentials")
        self.assertEqual(result["emails"], [])
        self.assertEqual(result["events"], [])

    def test_header_names_are_case_insensitive(self):
        result = _headers({"payload": {"headers": [
            {"name": "From", "value": "Pessoa"},
            {"name": "Subject", "value": "Assunto"},
        ]}})
        self.assertEqual(result["from"], "Pessoa")
        self.assertEqual(result["subject"], "Assunto")

    def test_all_day_calendar_event(self):
        result = _event({"id": "event-1", "summary": "Compromisso",
                         "start": {"date": "2026-11-02"}})
        self.assertTrue(result["all_day"])
        self.assertEqual(result["title"], "Compromisso")
        self.assertEqual(result["start"], "2026-11-02")


if __name__ == "__main__":
    unittest.main()


from security.bridge import MobileBridge


class MobileHealthSyncTests(unittest.TestCase):
    def test_health_payload_is_sanitized_and_saved_locally(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = MobileBridge({
                "ntfy_inbox": "inbox-topic",
                "ntfy_alerts": "alerts-topic",
                "mobile_secret": "x" * 32,
            }, Path(folder))
            bridge._save_health({
                "steps_today": 8123,
                "sleep_sessions": [{
                    "start": "2026-11-01T23:00:00Z",
                    "end": "2026-11-02T07:00:00Z",
                    "duration_minutes": 480,
                    "stages": [{"type": 5, "start": "2026-11-02T01:00:00Z", "end": "2026-11-02T02:00:00Z"}],
                    "unexpected_field": "should not be persisted",
                }],
            })
            result = json.loads((Path(folder) / "health_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(result["steps_today"], 8123)
            self.assertEqual(result["sleep_sessions"][0]["duration_minutes"], 480)
            self.assertNotIn("unexpected_field", json.dumps(result))
