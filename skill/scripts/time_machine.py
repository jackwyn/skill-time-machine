#!/usr/bin/env python3
"""Portable workflow drift tracker. Uses only the Python standard library."""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STATE = ".time-machine/state.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_json_path(path: str) -> list[str | int]:
    if path == "$":
        return []
    if not path.startswith("$"):
        raise ValueError(f"JSON path must start with '$': {path}")
    parts: list[str | int] = []
    pos = 1
    token = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]")
    while pos < len(path):
        match = token.match(path, pos)
        if not match:
            raise ValueError(f"Unsupported JSON path near {path[pos:]} in {path}")
        parts.append(match.group(1) if match.group(1) is not None else int(match.group(2)))
        pos = match.end()
    return parts


def get_json_path(value: Any, path: str) -> Any:
    current = value
    for part in parse_json_path(path):
        if isinstance(part, int):
            if not isinstance(current, list):
                raise KeyError(path)
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                raise KeyError(path)
            current = current[part]
    return current


def leaf_paths(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict) and value:
        for key, item in value.items():
            found.extend(leaf_paths(item, f"{prefix}.{key}"))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            found.extend(leaf_paths(item, f"{prefix}[{index}]"))
    else:
        found.append(prefix)
    return found


def interpolate(value: Any) -> Any:
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(f"Required environment variable is not set: {name}")
            return os.environ[name]

        return pattern.sub(replace, value)
    if isinstance(value, list):
        return [interpolate(item) for item in value]
    if isinstance(value, dict):
        return {key: interpolate(item) for key, item in value.items()}
    return value


def task_snapshot(task: dict[str, Any]) -> dict[str, Any]:
    request = task.get("request", {})
    method = str(request.get("method", "GET")).upper()
    url = interpolate(request.get("url", ""))
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Task {task.get('id', '?')} must use an absolute HTTP or HTTPS URL")

    headers = interpolate(request.get("headers", {}))
    body = interpolate(request.get("body"))
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            raise ValueError("Request body must be a string, object, array, or null")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=float(request.get("timeout", 20))) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        content_type = error.headers.get("Content-Type", "") if error.headers else ""
        raw = error.read()

    text = raw.decode("utf-8", errors="replace")
    payload: Any = None
    is_json = "json" in content_type.lower()
    if is_json or text.lstrip().startswith(("{", "[")):
        try:
            payload = json.loads(text)
            is_json = True
        except json.JSONDecodeError:
            is_json = False
    if not is_json:
        payload = text

    captures: dict[str, Any] = {}
    missing: list[str] = []
    for path in task.get("capture_paths", []):
        try:
            captures[path] = get_json_path(payload, path)
        except (KeyError, IndexError, ValueError, TypeError):
            missing.append(path)
    available = leaf_paths(payload) if is_json else (["$"] if payload else [])
    return {
        "status": status,
        "captured": captures,
        "missing_paths": missing,
        "available_paths": available,
    }


def compare_snapshots(task: dict[str, Any], baseline: dict[str, Any], actual: dict[str, Any], first_id: int = 1) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    task_id = task["id"]
    drifts: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    counter = first_id

    def suggest(issue: str, action: str, **details: Any) -> None:
        nonlocal counter
        proposals.append({"id": f"p{counter}", "task_id": task_id, "issue": issue, "action": action, **details})
        counter += 1

    if actual.get("error"):
        drifts.append({"task_id": task_id, "kind": "request_error", "message": actual["error"]})
        return drifts, proposals

    if baseline.get("status") != actual.get("status"):
        drift = {"task_id": task_id, "kind": "status_changed", "expected": baseline.get("status"), "actual": actual.get("status")}
        drifts.append(drift)
        suggest("HTTP status changed; inspect the cause before updating expectations", "manual_status_review")

    missing = set(actual.get("missing_paths", []))
    available = actual.get("available_paths", [])
    for path, expected in baseline.get("captured", {}).items():
        if path in missing:
            alternatives = difflib.get_close_matches(path, available, n=1, cutoff=0.48)
            candidate = alternatives[0] if alternatives else None
            drifts.append({"task_id": task_id, "kind": "path_missing", "path": path, "suggested_path": candidate})
            if candidate:
                suggest("JSON path appears renamed", "remap_path", old_path=path, new_path=candidate)
            else:
                suggest("JSON path no longer exists", "manual_schema_review", old_path=path)
        else:
            actual_value = actual.get("captured", {}).get(path)
            if actual_value != expected:
                drifts.append({"task_id": task_id, "kind": "value_changed", "path": path, "expected": expected, "actual": actual_value})
                suggest("Captured result changed", "refresh_baseline", path=path)
    return drifts, proposals


def active_revision(state: dict[str, Any]) -> dict[str, Any]:
    for revision in state.get("revisions", []):
        if revision["id"] == state.get("active_revision"):
            return revision
    raise ValueError("Active revision is missing from state")


def next_revision_id(state: dict[str, Any]) -> str:
    numbers = [int(item["id"][1:]) for item in state.get("revisions", []) if item.get("id", "").startswith("r") and item["id"][1:].isdigit()]
    return f"r{max(numbers, default=0) + 1}"


def read_config(path: str) -> dict[str, Any]:
    config = load_json(path)
    if not isinstance(config, dict) or not isinstance(config.get("tasks"), list) or not config["tasks"]:
        raise ValueError("Config must be a JSON object with a non-empty 'tasks' array")
    ids = [task.get("id") for task in config["tasks"]]
    if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("Every task needs a unique, non-empty string id")
    for task in config["tasks"]:
        if not isinstance(task.get("capture_paths", []), list):
            raise ValueError(f"Task {task['id']} capture_paths must be an array")
        for path in task.get("capture_paths", []):
            parse_json_path(path)
            if path == "$":
                raise ValueError(f"Task {task['id']} cannot capture the entire response; select specific JSON paths")
    return config


def collect_snapshots(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snapshots: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    for task in config["tasks"]:
        try:
            snapshots[task["id"]] = task_snapshot(task)
        except Exception as exc:  # Keep error details minimal; URLs can contain private query data.
            snapshots[task["id"]] = {"status": None, "captured": {}, "missing_paths": [], "available_paths": [], "error": type(exc).__name__}
            failures.append({"task_id": task["id"], "kind": "request_error", "message": type(exc).__name__})
    return snapshots, failures


def cmd_init(args: argparse.Namespace) -> int:
    template = {
        "tasks": [{
            "id": "service-health",
            "title": "Example JSON API check",
            "system_version": "service/v1",
            "request": {"method": "GET", "url": "http://127.0.0.1:8000/api/status", "headers": {}, "timeout": 10},
            "capture_paths": ["$.status"],
        }]
    }
    save_json(args.output, template)
    print(f"Created task config: {args.output}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    snapshots, failures = collect_snapshots(config)
    if failures:
        print("Could not record baseline: one or more requests failed.", file=sys.stderr)
        for item in failures:
            print(f"  {item['task_id']}: {item['message']}", file=sys.stderr)
        return 1
    missing = [(task["id"], path) for task in config["tasks"] for path in snapshots[task["id"]]["missing_paths"]]
    if missing:
        print("Could not record baseline: selected capture paths are missing.", file=sys.stderr)
        for task_id, path in missing:
            print(f"  {task_id}: {path}", file=sys.stderr)
        return 1
    state = {"schema_version": 1, "active_revision": "r1", "revisions": [{
        "id": "r1", "label": args.label, "created_at": now(), "config": config,
        "snapshots": snapshots, "verified_against": [],
    }], "last_run": None}
    save_json(args.state, state)
    for task in config["tasks"]:
        snap = snapshots[task["id"]]
        print(f"Recorded {task['id']}: HTTP {snap['status']}; {len(snap['captured'])} selected path(s); version {task.get('system_version', 'unspecified')}")
    print(f"Baseline saved as r1 ({args.label}) in {args.state}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    state = load_json(args.state)
    revision = active_revision(state)
    baselines = revision.get("snapshots", {})
    current_ids = {task["id"] for task in config["tasks"]}
    if current_ids != set(baselines):
        raise ValueError("Current config task IDs do not match the active baseline. Record a new baseline or roll back first.")
    actuals, request_failures = collect_snapshots(config)
    drifts: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    successful: list[str] = []
    for task in config["tasks"]:
        task_id = task["id"]
        found, suggested = compare_snapshots(task, baselines[task_id], actuals[task_id], len(proposals) + 1)
        drifts.extend(found)
        proposals.extend(suggested)
        if not found:
            successful.append(task_id)
            version = task.get("system_version")
            if version and version not in revision.setdefault("verified_against", []):
                revision["verified_against"].append(version)
    run = {"run_id": f"run-{len(state.get('runs', [])) + 1}", "started_at": now(), "revision": revision["id"],
           "drifts": drifts, "proposals": proposals, "actuals": actuals, "passed_tasks": successful}
    state.setdefault("runs", []).append(run)
    state["last_run"] = run
    save_json(args.state, state)
    print(f"Replay {run['run_id']} against {revision['id']} ({revision['label']})")
    for task in config["tasks"]:
        task_id = task["id"]
        relevant = [item for item in drifts if item["task_id"] == task_id]
        actual = actuals[task_id]
        verdict = "PASS" if not relevant else "DRIFT"
        print(f"  {verdict} {task_id}: HTTP {actual.get('status', 'error')} | system version {task.get('system_version', 'unspecified')}")
        for item in relevant:
            if item["kind"] == "value_changed":
                print(f"    {item['path']}: expected {json.dumps(item['expected'], ensure_ascii=False)}; got {json.dumps(item['actual'], ensure_ascii=False)}")
            elif item["kind"] == "path_missing":
                print(f"    Missing {item['path']}; likely replacement: {item.get('suggested_path') or 'not found'}")
            elif item["kind"] == "status_changed":
                print(f"    HTTP status changed: expected {item['expected']}; got {item['actual']}")
            else:
                print(f"    {item['kind']}: {item.get('message', '')}")
    if proposals:
        print("Proposals (review; none applied automatically):")
        for item in proposals:
            detail = f" {item.get('old_path')} → {item.get('new_path')}" if item["action"] == "remap_path" else ""
            print(f"  {item['id']}: {item['action']} — {item['issue']}{detail}")
    else:
        print(f"All tasks passed. Verified versions: {', '.join(revision.get('verified_against', [])) or 'none declared'}")
    return 0 if not drifts else 2


def cmd_proposals(args: argparse.Namespace) -> int:
    state = load_json(args.state)
    run = state.get("last_run")
    if not run:
        print("No replay proposals yet.")
        return 0
    proposals = run.get("proposals", [])
    if not proposals:
        print(f"No proposals for {run['run_id']}.")
        return 0
    for item in proposals:
        detail = f"; {item.get('old_path')} → {item.get('new_path')}" if item["action"] == "remap_path" else ""
        print(f"{item['id']} [{item['action']}] task={item['task_id']}: {item['issue']}{detail}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    state = load_json(args.state)
    run = state.get("last_run") or {}
    proposal = next((item for item in run.get("proposals", []) if item["id"] == args.proposal), None)
    if proposal is None:
        raise ValueError(f"Proposal {args.proposal} was not found in the latest replay")
    if proposal["action"] not in {"remap_path", "refresh_baseline"}:
        raise ValueError("This proposal needs manual schema review and cannot be applied automatically")
    task = next(item for item in config["tasks"] if item["id"] == proposal["task_id"])
    if proposal["action"] == "remap_path":
        old = proposal["old_path"]
        task["capture_paths"] = [proposal["new_path"] if path == old else path for path in task.get("capture_paths", [])]
    new_snapshot = task_snapshot(task)
    if new_snapshot.get("status") is None or new_snapshot.get("missing_paths"):
        raise ValueError("The proposed task did not produce all configured capture paths; no revision was created")
    current = active_revision(state)
    snapshots = copy.deepcopy(current["snapshots"])
    snapshots[task["id"]] = new_snapshot
    revision_id = next_revision_id(state)
    revision = {"id": revision_id, "label": args.label or f"accepted-{args.proposal}", "created_at": now(),
                "config": config, "snapshots": snapshots, "verified_against": []}
    state["revisions"].append(revision)
    state["active_revision"] = revision_id
    save_json(args.config, config)
    save_json(args.state, state)
    print(f"Applied {args.proposal} as revision {revision_id}; captured HTTP {new_snapshot['status']} and {len(new_snapshot['captured'])} selected path(s).")
    print("Replay once more to verify the new revision against its declared system version.")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    state = load_json(args.state)
    target = next((item for item in state.get("revisions", []) if item["id"] == args.revision), None)
    if not target:
        raise ValueError(f"Revision {args.revision} does not exist")
    save_json(args.config, target["config"])
    state["active_revision"] = target["id"]
    save_json(args.state, state)
    print(f"Rolled back to {target['id']} ({target['label']}); later revisions remain available.")
    return 0


def cmd_versions(args: argparse.Namespace) -> int:
    state = load_json(args.state)
    for item in state.get("revisions", []):
        verified = ", ".join(item.get("verified_against", [])) or "not yet verified"
        marker = " (active)" if item["id"] == state.get("active_revision") else ""
        print(f"{item['id']} {item['label']}{marker} — verified against: {verified}")
    return 0


def make_demo_state() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = {"tasks": [{"id": "weather-summary", "title": "Read current temperature", "system_version": "weather-api/1.0",
                         "request": {"method": "GET", "url": "fixture://weather"}, "capture_paths": ["$.current.temperature_c"]}]}
    baseline_payload = {"current": {"temperature_c": 21, "conditions": "Clear"}}
    changed_payload = {"current": {"temp_c": 21, "conditions": "Clear"}}
    baseline = {"status": 200, "captured": {"$.current.temperature_c": 21}, "missing_paths": [], "available_paths": leaf_paths(baseline_payload)}
    actual = {"status": 200, "captured": {}, "missing_paths": ["$.current.temperature_c"], "available_paths": leaf_paths(changed_payload)}
    return config, baseline, actual


def cmd_demo(args: argparse.Namespace) -> int:
    config, baseline, actual = make_demo_state()
    task = config["tasks"][0]
    drifts, proposals = compare_snapshots(task, baseline, actual)
    proposal = proposals[0]
    print("Demo: saved task replay across a JSON schema change")
    print("BEFORE: r1 expected $.current.temperature_c = 21; current response has $.current.temp_c")
    print(f"DRIFT: {drifts[0]['kind']} — {drifts[0]['path']} is missing")
    print(f"PROPOSAL: {proposal['id']} remap {proposal['old_path']} → {proposal['new_path']} (not auto-applied)")

    revised_config = copy.deepcopy(config)
    revised_config["tasks"][0]["capture_paths"] = [proposal["new_path"]]
    after = {"status": 200, "captured": {proposal["new_path"]: 21}, "missing_paths": [], "available_paths": actual["available_paths"]}
    revised_baseline = {"status": 200, "captured": {proposal["new_path"]: 21}, "missing_paths": [], "available_paths": actual["available_paths"]}
    after_drifts, _ = compare_snapshots(revised_config["tasks"][0], revised_baseline, after)
    revision1 = {"id": "r1", "label": "baseline", "created_at": now(), "config": config,
                 "snapshots": {"weather-summary": baseline}, "verified_against": ["weather-api/1.0"]}
    revision2 = {"id": "r2", "label": f"accepted-{proposal['id']}", "created_at": now(), "config": revised_config,
                 "snapshots": {"weather-summary": revised_baseline}, "verified_against": []}
    state = {"schema_version": 1, "active_revision": "r2", "revisions": [revision1, revision2],
             "last_run": {"run_id": "demo-run-1", "revision": "r1", "drifts": drifts, "proposals": proposals}}
    if not after_drifts:
        revision2["verified_against"].append("weather-api/2.0")
    print(f"AFTER: r2 captures $.current.temp_c = 21; replay {'PASS' if not after_drifts else 'DRIFT'}")
    print("VERSIONS: r1 verified against weather-api/1.0; r2 verified against weather-api/2.0")
    state["active_revision"] = "r1"
    print("ROLLBACK: active revision restored to r1; r2 remains in history")
    if args.state:
        save_json(args.state, state)
        print(f"Demo state written to {args.state}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Replay saved HTTP/JSON tasks, detect drift, and manage verified revisions.")
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write a starter task config")
    init.add_argument("--output", default="tasks.json")
    init.set_defaults(func=cmd_init)
    record = sub.add_parser("record", help="capture a new baseline revision")
    record.add_argument("--config", required=True)
    record.add_argument("--state", default=DEFAULT_STATE)
    record.add_argument("--label", default="baseline")
    record.set_defaults(func=cmd_record)
    replay = sub.add_parser("replay", help="replay tasks and compare to active baseline")
    replay.add_argument("--config", required=True)
    replay.add_argument("--state", default=DEFAULT_STATE)
    replay.set_defaults(func=cmd_replay)
    proposals = sub.add_parser("proposals", help="list proposals from the latest replay")
    proposals.add_argument("--state", default=DEFAULT_STATE)
    proposals.set_defaults(func=cmd_proposals)
    apply = sub.add_parser("apply", help="accept a reviewed proposal as a new revision")
    apply.add_argument("--config", required=True)
    apply.add_argument("--state", default=DEFAULT_STATE)
    apply.add_argument("--proposal", required=True)
    apply.add_argument("--label")
    apply.set_defaults(func=cmd_apply)
    rollback = sub.add_parser("rollback", help="restore a prior config and baseline revision")
    rollback.add_argument("--config", required=True)
    rollback.add_argument("--state", default=DEFAULT_STATE)
    rollback.add_argument("--revision", required=True)
    rollback.set_defaults(func=cmd_rollback)
    versions = sub.add_parser("versions", help="list revisions and verified system versions")
    versions.add_argument("--state", default=DEFAULT_STATE)
    versions.set_defaults(func=cmd_versions)
    demo = sub.add_parser("demo", help="run a deterministic drift/repair/rollback example")
    demo.add_argument("--state", help="optional path to save the demo state JSON")
    demo.set_defaults(func=cmd_demo)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
