---
name: skill-time-machine
description: Replay saved API, website-adapter, and model-backed test tasks against recorded baselines; detect workflow or result drift; propose evidence-based repairs; preserve revisions for rollback; and report verified versions. Use when maintaining AI skills or automations as apps, sites, APIs, or models change, or when a workflow needs regression checks and version evidence.
---

# Skill Time Machine

Use this skill to keep a workflow testable as its underlying apps, APIs, or models evolve. The bundled Python CLI is a small, dependency-free reference implementation for HTTP/JSON workflows; other adapters can follow the same record → replay → compare → propose → apply → verify → rollback lifecycle.

## Workflow

1. **Define safe replay tasks.** Create a JSON config with stable task IDs, the request to replay, selected JSON paths to capture, and an optional system/model version label. Keep credentials out of the file; use environment placeholders such as `${SERVICE_TOKEN}` in headers. Capture only fields needed for regression evidence, never secrets or personal data.
2. **Record a baseline.** Run `python3 "<skill-dir>/scripts/time_machine.py" record --config "tasks.json" --state ".time-machine/state.json" --label "baseline"`. Review the selected paths and status before treating the snapshot as a trusted baseline.
3. **Replay after a change.** Run the same command with `replay`. Inspect status, path-level expected/actual evidence, and version label. A missing path or changed status indicates workflow/schema drift; a changed captured value indicates result drift.
4. **Review proposals before applying.** Replay creates suggestions, not automatic fixes. A likely renamed JSON path may be proposed for remapping; changed output values or status may be proposed for a baseline refresh. Check the evidence and the live system first.
5. **Apply only a reviewed proposal.** Use `apply --proposal <id>` to create a new immutable revision. The tool re-reads the affected task and stores the new selected evidence. It does not apply repairs during replay.
6. **Verify and preserve evidence.** Replay again; only a clean replay adds that task's declared `system_version` to the revision's verified-against list. Use `versions` to inspect revision and verification history.
7. **Roll back when needed.** Use `rollback --revision <revision-id>` to restore that revision's task config and baseline. Revisions remain in history.

## CLI commands

```text
python3 "<skill-dir>/scripts/time_machine.py" init --output tasks.json
python3 "<skill-dir>/scripts/time_machine.py" record --config tasks.json --state .time-machine/state.json --label baseline
python3 "<skill-dir>/scripts/time_machine.py" replay --config tasks.json --state .time-machine/state.json
python3 "<skill-dir>/scripts/time_machine.py" proposals --state .time-machine/state.json
python3 "<skill-dir>/scripts/time_machine.py" apply --config tasks.json --state .time-machine/state.json --proposal p1
python3 "<skill-dir>/scripts/time_machine.py" versions --state .time-machine/state.json
python3 "<skill-dir>/scripts/time_machine.py" rollback --config tasks.json --state .time-machine/state.json --revision r1
python3 "<skill-dir>/scripts/time_machine.py" demo
```

The default request adapter supports HTTP/HTTPS and JSON responses, with exact JSON paths such as `$.data.items[0].name`. It stores only HTTP status and explicitly selected values/paths. It does not execute arbitrary shell commands or silently mutate tests. For browser workflows or model calls that do not expose HTTP, keep the same evidence/revision contract and use an explicit adapter appropriate to that environment.

## Guardrails

- Never overwrite the trusted baseline just because a replay failed. Review and explicitly apply a proposal.
- Do not store passwords, access tokens, private prompts, personal data, or complete API responses in capture paths or committed state files. Use environment variables for request secrets and keep `.time-machine/` out of source control.
- Treat values from a new model or API version as untrusted until the task passes review. A passing test verifies only the configured task and selected assertions; it does not establish broad product correctness.
- Keep task definitions deterministic where possible: pin model/version identifiers, sampling settings, locale, time zone, and fixtures. Where outputs are nondeterministic, compare stable fields or define tolerances in a dedicated adapter rather than accepting fuzzy text as exact.
- Save before/after evidence, the proposal selected, the resulting revision, and a rollback target when reporting a repair.
