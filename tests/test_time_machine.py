import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skill" / "scripts" / "time_machine.py"
sys.path.insert(0, str(CLI.parent))
import time_machine as tm  # noqa: E402


class MutableHandler(BaseHTTPRequestHandler):
    payload = {"current": {"temperature_c": 21}}

    def do_GET(self):
        body = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class TimeMachineTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], cwd=ROOT, text=True, capture_output=True)

    def test_json_path_object_and_array(self):
        value = {"items": [{"name": "alpha"}]}
        self.assertEqual(tm.get_json_path(value, "$.items[0].name"), "alpha")
        self.assertEqual(tm.leaf_paths(value), ["$.items[0].name"])

    def test_schema_rename_generates_reviewable_proposal(self):
        task = {"id": "weather", "capture_paths": ["$.current.temperature_c"]}
        baseline = {"status": 200, "captured": {"$.current.temperature_c": 21}}
        actual = {"status": 200, "captured": {}, "missing_paths": ["$.current.temperature_c"],
                  "available_paths": ["$.current.temp_c", "$.current.conditions"]}
        drifts, proposals = tm.compare_snapshots(task, baseline, actual)
        self.assertEqual(drifts[0]["kind"], "path_missing")
        self.assertEqual(proposals[0]["action"], "remap_path")
        self.assertEqual(proposals[0]["new_path"], "$.current.temp_c")

    def test_value_change_proposes_refresh_not_silent_acceptance(self):
        task = {"id": "model", "capture_paths": ["$.answer"]}
        baseline = {"status": 200, "captured": {"$.answer": "old"}}
        actual = {"status": 200, "captured": {"$.answer": "new"}, "missing_paths": [], "available_paths": ["$.answer"]}
        drifts, proposals = tm.compare_snapshots(task, baseline, actual)
        self.assertEqual(drifts[0]["kind"], "value_changed")
        self.assertEqual(proposals[0]["action"], "refresh_baseline")

    def test_status_change_requires_manual_review(self):
        task = {"id": "service", "capture_paths": []}
        baseline = {"status": 200, "captured": {}}
        actual = {"status": 401, "captured": {}, "missing_paths": [], "available_paths": []}
        drifts, proposals = tm.compare_snapshots(task, baseline, actual)
        self.assertEqual(drifts[0]["kind"], "status_changed")
        self.assertEqual(proposals[0]["action"], "manual_status_review")

    def test_config_cannot_capture_entire_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"
            path.write_text(json.dumps({"tasks": [{"id": "unsafe", "request": {"url": "https://example.test"}, "capture_paths": ["$"]}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                tm.read_config(str(path))

    def test_demo_writes_rollback_state_and_reports_before_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            result = self.run_cli("demo", "--state", state_path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("BEFORE:", result.stdout)
            self.assertIn("AFTER:", result.stdout)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["active_revision"], "r1")
            self.assertEqual([r["id"] for r in state["revisions"]], ["r1", "r2"])
            self.assertEqual(state["revisions"][1]["verified_against"], ["weather-api/2.0"])

    def test_http_record_replay_apply_verify_and_rollback(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), MutableHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config_path = Path(tmp) / "tasks.json"
                state_path = Path(tmp) / "state.json"
                config = {"tasks": [{"id": "weather", "system_version": "weather-api/1.0",
                                     "request": {"method": "GET", "url": f"http://127.0.0.1:{server.server_port}/weather"},
                                     "capture_paths": ["$.current.temperature_c"]}]}
                config_path.write_text(json.dumps(config), encoding="utf-8")
                recorded = self.run_cli("record", "--config", config_path, "--state", state_path)
                self.assertEqual(recorded.returncode, 0, recorded.stderr + recorded.stdout)

                MutableHandler.payload = {"current": {"temp_c": 21}}
                config["tasks"][0]["system_version"] = "weather-api/2.0"
                config_path.write_text(json.dumps(config), encoding="utf-8")
                replay = self.run_cli("replay", "--config", config_path, "--state", state_path)
                self.assertEqual(replay.returncode, 2, replay.stderr + replay.stdout)
                self.assertIn("$.current.temp_c", replay.stdout)

                applied = self.run_cli("apply", "--config", config_path, "--state", state_path, "--proposal", "p1")
                self.assertEqual(applied.returncode, 0, applied.stderr + applied.stdout)
                repaired = self.run_cli("replay", "--config", config_path, "--state", state_path)
                self.assertEqual(repaired.returncode, 0, repaired.stderr + repaired.stdout)
                self.assertIn("weather-api/2.0", repaired.stdout)

                rollback = self.run_cli("rollback", "--config", config_path, "--state", state_path, "--revision", "r1")
                self.assertEqual(rollback.returncode, 0, rollback.stderr + rollback.stdout)
                rolled_config = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(rolled_config["tasks"][0]["capture_paths"], ["$.current.temperature_c"])
                history = self.run_cli("versions", "--state", state_path)
                self.assertIn("r1 baseline (active)", history.stdout)
                self.assertIn("weather-api/2.0", history.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
