# Skill Time Machine

A portable AI skill plus a runnable, dependency-free Python demo for keeping workflows reliable as APIs, apps, websites, and models change. It replays saved HTTP/JSON tasks, compares selected evidence with a baseline, flags workflow or result drift, suggests repairs without applying them, and keeps revisions for verification and rollback.

## Run the demo

Requires Python 3.10 or newer; no third-party packages are needed.

```bash
python3 skill/scripts/time_machine.py demo --state /tmp/time-machine-demo.json
python3 -m unittest discover -s tests -v
```

The demo starts with an API field rename (`temperature_c` → `temp_c`), shows the before evidence and repair proposal, demonstrates a passing replay on a new revision, lists the versions verified, and rolls the active baseline back while retaining the newer revision.

## Try it against an HTTP JSON API

Generate a starter config, edit the URL/version/capture paths, and record a baseline:

```bash
python3 skill/scripts/time_machine.py init --output tasks.json
python3 skill/scripts/time_machine.py record --config tasks.json --state .time-machine/state.json --label baseline
```

After an API/model change, update `system_version` in `tasks.json` and replay:

```bash
python3 skill/scripts/time_machine.py replay --config tasks.json --state .time-machine/state.json
python3 skill/scripts/time_machine.py proposals --state .time-machine/state.json
```

A replay exit code of `0` means all configured checks passed; `2` means drift was detected; `1` means the command/config/request could not be completed. Review evidence before accepting a proposal. To apply a reviewed repair, create a new revision, verify it, inspect the version history, or roll back:

```bash
python3 skill/scripts/time_machine.py apply --config tasks.json --state .time-machine/state.json --proposal p1
python3 skill/scripts/time_machine.py replay --config tasks.json --state .time-machine/state.json
python3 skill/scripts/time_machine.py versions --state .time-machine/state.json
python3 skill/scripts/time_machine.py rollback --config tasks.json --state .time-machine/state.json --revision r1
```

Use JSON paths such as `$.data.items[0].name` in `capture_paths`. Requests can reference environment variables in headers or values, for example `"Authorization": "Bearer ${SERVICE_TOKEN}"`; keep credentials out of task configs and commits. Only explicitly selected response values are persisted. Avoid capturing secrets or personal data, and keep `.time-machine/` out of version control. The included HTTP adapter is intentionally small: browser tasks and non-HTTP model workflows need an explicit adapter that follows the same evidence and revision rules.

## Portable skill

The skill package is in [`skill/`](skill/). Copy that directory into a compatible agent skills folder, or open [`skill/SKILL.md`](skill/SKILL.md) for the complete agent workflow.

## Optional donation

If this project is useful, an optional donation can be sent to **Jackwyn Fredrick** using UPI ID **9489558549@ptyes**. The amount is entirely donor-chosen; no amount is prefilled. On a UPI-enabled phone, [open a UPI payment to Jackwyn Fredrick](upi://pay?pa=9489558549%40ptyes&pn=Jackwyn%20Fredrick&cu=INR). Donations are optional and are not connected to the software.
