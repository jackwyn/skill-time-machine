# Skill Time Machine

A reusable AI skill and dependency-free Python demo for checking whether an API or workflow still behaves as expected after apps, websites, APIs, or models change. It records selected evidence, detects drift, proposes repairs for review, and keeps versioned history for verification and rollback.

## Quick start

Requires Python 3.10 or newer. The CLI uses only the Python standard library.

```bash
python3 skill/scripts/time_machine.py demo --state /tmp/time-machine-demo.json
python3 -m unittest discover -s tests -v
```

The demo shows a JSON field rename (`temperature_c` → `temp_c`), reports a repair proposal without applying it, verifies a new revision, and rolls back while retaining history.

## Use it with AI skills

This project uses the open [Agent Skills format](https://agentskills.io/specification): a skill directory containing an uppercase `SKILL.md` with `name` and `description` metadata, plus optional scripts and resources. The same core folder can be used by products that implement the standard. **That does not mean every AI product automatically discovers or imports it**; installation and execution support depend on the product and account.

### Claude Code

Claude Code natively discovers skills in personal or project skill directories. From a clone of this repository, install it for your user:

```bash
mkdir -p ~/.claude/skills/skill-time-machine
cp -R skill/. ~/.claude/skills/skill-time-machine/
```

For a repository-only install, copy it to `.claude/skills/skill-time-machine/` inside that repository instead. Claude Code can invoke `/skill-time-machine` or select it when relevant. See [Claude Code skills documentation](https://docs.anthropic.com/en/docs/claude-code/skills).

### Claude.ai

Claude supports custom skill uploads on Free, Pro, Max, Team, and Enterprise plans when code execution is enabled; organization settings can restrict uploads or sharing. Build a ZIP whose top-level folder is named for the skill:

```bash
python3 tools/package_skill.py --format skill
```

Then in Claude, go to **Customize → Skills → + → Create skill → Upload a skill**, upload `dist/skill-time-machine-skill.zip`, and enable it. On Team or Enterprise, an administrator can provision it for everyone or control sharing. See [Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude) and [How to create custom skills](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills).

### ChatGPT

Direct skill upload is available to eligible ChatGPT **Business, Enterprise, Healthcare, and Edu** users, subject to workspace permissions and product availability. In ChatGPT, open **Plugins → Plugin Directory → Skills → Create → Upload from your computer**, then select the same ZIP built above. Review the scan result; workspace members can share or publish the skill if their administrator permits it. Do not assume arbitrary skill upload is available on personal ChatGPT plans. See [Skills in ChatGPT](https://help.openai.com/en/articles/20001066-skills-in-chatgpt).

To make a package for OpenAI's plugin submission process, which can distribute skills through the public plugin directory shared by ChatGPT and Codex, build:

```bash
python3 tools/package_skill.py --format openai-plugin
```

This creates `dist/skill-time-machine-plugin.zip`. It is only a package: it does **not** submit or publish the plugin. Public listing requires a verified developer identity, submission through the [OpenAI plugin portal](https://platform.openai.com/plugins), and review/approval. See [OpenAI's plugin submission guide](https://developers.openai.com/plugins/deploy/submission). This repository currently has no `LICENSE` file, so public GitHub hosting alone does not grant permission to reuse or redistribute its contents. Please choose and add a license before inviting broad reuse.

If Skills are unavailable in a ChatGPT account, a [Project](https://help.openai.com/en/articles/10169521-projects-in-chatgpt) can use the skill text as project instructions and uploaded reference files, but that is not an installed skill and does not itself run the bundled CLI.

### OpenAI Codex

Codex supports local skills. From a clone of this repository, install the skill for your user:

```bash
mkdir -p ~/.agents/skills/skill-time-machine
cp -R skill/. ~/.agents/skills/skill-time-machine/
```

For project scope, copy it under `.agents/skills/skill-time-machine/` in the target repository. Use `$skill-time-machine` or `/skills` in Codex CLI/IDE. ChatGPT desktop also supports skills where the feature is available; check its Skills sidebar for the install and invocation options exposed by your app version. See [OpenAI's Codex skills guide](https://developers.openai.com/codex/skills/).

### Other AI tools

If another agent adopts the Agent Skills standard, install the `skill/` directory using that product's documented skill location. If it does not support skills, attach `skill/SKILL.md` or paste its instructions for a one-off task. The included Python CLI only runs when the host gives the agent access to the project files, a shell, and Python; otherwise the skill can guide a manual workflow but cannot execute the CLI for you. The Claude API and OpenAI API have separate skill upload/invocation flows; those are developer APIs, not automatic installation into their chat products.

## Run against an HTTP/JSON API

Create a starter task config, edit the endpoint and selected JSON paths, then record a baseline:

```bash
python3 skill/scripts/time_machine.py init --output tasks.json
python3 skill/scripts/time_machine.py record --config tasks.json --state .time-machine/state.json --label baseline
```

After a system change, update `system_version` in `tasks.json` and replay:

```bash
python3 skill/scripts/time_machine.py replay --config tasks.json --state .time-machine/state.json
python3 skill/scripts/time_machine.py proposals --state .time-machine/state.json
```

A replay exit code of `0` means checks passed; `2` means drift was detected; `1` means the command, config, or request could not be completed. Read the evidence and independently review a proposed change before accepting it. For example, after reviewing proposal `p1`, create a new revision and verify it:

```bash
python3 skill/scripts/time_machine.py apply --config tasks.json --state .time-machine/state.json --proposal p1
python3 skill/scripts/time_machine.py replay --config tasks.json --state .time-machine/state.json
python3 skill/scripts/time_machine.py versions --state .time-machine/state.json
```

Roll back to a known revision if needed:

```bash
python3 skill/scripts/time_machine.py rollback --config tasks.json --state .time-machine/state.json --revision r1
```

Use JSON paths such as `$.data.items[0].name` in `capture_paths`. Request headers and values can reference environment variables, e.g. `"Authorization": "Bearer ${SERVICE_TOKEN}"`; keep credentials out of task configs and commits. Only explicitly selected response paths are persisted. Avoid capturing secrets or personal data, and keep `.time-machine/` out of version control. The included adapter supports HTTP/HTTPS and JSON; browser tasks and non-HTTP model workflows need an explicit adapter following the same evidence and revision rules.

## Contributing and licensing

Issues and pull requests are welcome. No license is currently included, so public availability on GitHub should not be read as permission to redistribute or adapt the code. Please choose a license before reuse is promoted.

## Optional donation

If this project is useful, an optional donation can be sent to **Jackwyn Fredrick** using UPI ID **9489558549@ptyes**. The amount is entirely donor-chosen; no amount is prefilled. On a UPI-enabled phone, [open a UPI payment to Jackwyn Fredrick](upi://pay?pa=9489558549%40ptyes&pn=Jackwyn%20Fredrick&cu=INR). Donations are optional and are not connected to the software.
