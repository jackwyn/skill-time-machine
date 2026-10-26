---
name: skill-time-machine
description: Replay API and workflow checks, detect drift, propose safe repairs, verify versioned revisions, and roll back. Use when APIs, AI models, websites, or automations change.
---

# Skill Time Machine

Use this skill to keep a workflow testable as the systems around it change. The bundled Python CLI is a dependency-free reference implementation for HTTP/JSON checks. Other adapters can follow the same record → replay → compare → propose → review → apply → verify → rollback lifecycle.

## Check host capabilities first

The CLI requires Python 3.10+, access to the project files, a shell, and HTTP/HTTPS network access to the configured API. Do not claim to have run it unless those capabilities are actually available. If the host cannot execute the CLI, explain the limitation and guide the user through a manual comparison using the same evidence and approval rules. The included adapter does not directly automate browser interfaces or model chat products.

## Workflow

1. **Define a safe replay task.** Create a JSON config with stable task IDs, a request, selected JSON paths to capture, and an optional `system_version`. Keep credentials out of files; use environment placeholders such as `${SERVICE_TOKEN}` in headers. Capture only regression evidence needed, never secrets or personal data.
2. **Record a baseline.** Run `python3 "<skill-dir>/scripts/time_machine.py" record --config tasks.json --state .time-machine/state.json --label baseline`. Review selected values and status before trusting the snapshot.
3. **Replay after a change.** Run the same command with `replay`. Inspect status, path-level evidence, and version labels. Missing paths or changed status indicate workflow/schema drift; changed selected values indicate result drift.
4. **Review proposals.** Replay creates suggestions, not automatic fixes. A likely renamed JSON path may be proposed for remapping; changed values or status may be proposed for manual review or a baseline refresh. Inspect the live system and evidence first.
5. **Apply only an explicitly approved proposal.** Only use `apply --proposal <id>` after the user has reviewed and approved that specific proposal. It creates a new revision and re-reads selected evidence. It does not automatically fix workflows during replay.
6. **Verify the revision.** Replay again. A clean replay adds the task's declared `system_version` to the revision's verified-against list. Use `versions` to inspect revision and verification history.
7. **Roll back if needed.** Use `rollback --revision <revision-id>` to restore the selected revision's task config and baseline. Later revisions remain in history.

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

The default adapter supports HTTP/HTTPS and JSON responses, with paths such as `$.data.items[0].name`. It stores only HTTP status and explicitly selected values/paths. It does not run arbitrary shell commands or silently mutate tests. Browser or model workflows need an explicit adapter that follows the same evidence and revision contract. A passing replay verifies only the configured task and assertions; it does not establish broad product correctness.

## Guardrails

- Never overwrite a trusted baseline just because a replay failed. Review the evidence and explicitly approve any proposal before applying it.
- Do not store passwords, access tokens, private prompts, personal data, or complete API responses in capture paths or committed state files. Use environment variables for request secrets and keep `.time-machine/` out of source control.
- Treat values from a new model or API version as untrusted until reviewed. A passing test proves only what was configured and captured.
- Keep tasks deterministic where possible: pin model/version identifiers, sampling settings, locale, time zone, and fixtures. For nondeterministic outputs, compare stable fields or use a dedicated tolerance-aware adapter rather than accepting fuzzy text as exact.
- When reporting a repair, include before/after evidence, the approved proposal, the resulting revision, verification status, and a rollback target.
