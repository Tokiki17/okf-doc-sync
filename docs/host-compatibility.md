# Host compatibility

DocSync ships one host-neutral skill that any agent harness supporting the [Agent Skills specification](https://agentskills.io/specification) can load. An agent or person without skill support can follow `skills/doc-sync/SKILL.md` directly and run the validator as a command.

## Portability contract

- **Format**: `skills/doc-sync/` follows the Agent Skills layout: `SKILL.md`, `references/`, and `scripts/`. References are linked one level deep from `SKILL.md`, which stays under 500 lines.
- **Frontmatter**: only `name` and `description`. This is the set every checked consumer accepts: the Agent Skills specification, Codex's skill-creator validator (which rejects `compatibility`), and the claude.ai and Claude API upload validator (which rejects Claude Code-only keys). Runtime requirements live in the body instead of a `compatibility` field.
- **Description**: third person, what the skill does first and when to use it second, under 1,024 characters, as the [Anthropic authoring guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) and [Codex skills guide](https://learn.chatgpt.com/docs/build-skills) both recommend.
- **Body**: no host tool names, model names, or fixed install paths. Paths are relative to the skill directory; the only executable dependency is Python 3.10+ with PyYAML, or system Ruby for YAML.
- **Host extras**: `agents/openai.yaml` is optional Codex UI and invocation metadata. Other hosts ignore it, and it stays in the tree so every installed mirror has the same parity check.
- **Maintenance rules**: [the maintenance standard](../skills/doc-sync/references/doc-maintenance.md) cites model, harness, and industry sources with a check date. Update that file, not host-specific copies, when a source changes.

## Installation by host

`scripts/install.py` copies the same tree and verifies byte-for-byte parity. Use the same `--host` or `--target` for `--check`.

| Host | Command | Default target |
| --- | --- | --- |
| Codex (existing installs) | `python3 scripts/install.py` | `${CODEX_HOME:-~/.codex}/skills/doc-sync` |
| Codex and other `.agents` readers | `python3 scripts/install.py --host agents` | `~/.agents/skills/doc-sync` |
| Claude Code | `python3 scripts/install.py --host claude` | `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/doc-sync` |
| Any other harness or project scope | `python3 scripts/install.py --target <dir>/doc-sync` | The given directory |

Install only one copy per skill root a host scans. Codex does not merge same-named skills, so do not install both the `~/.codex` and `~/.agents` copies on one Codex host. Claude Code picks up edits to existing skill directories within a session; a newly created top-level skills directory needs `/reload-skills`.

## Host notes

- **Codex**: loads a capped catalog of names, descriptions, and paths first and reads `SKILL.md` on selection, so the description front-loads the task and triggers. `agents/openai.yaml` keeps implicit invocation enabled. Codex lists `.agents/skills` roots; existing `~/.codex/skills` installs keep working. Resolve resource-backed skill locators through the host instead of assuming a local path. [Codex skills guide](https://learn.chatgpt.com/docs/build-skills)
- **Claude Code**: loads personal skills from `~/.claude/skills` and project skills from `.claude/skills`, and provides the skill's base directory when it loads the skill. Edits to existing skill directories apply within a session. [Claude Code skills](https://code.claude.com/docs/en/skills)
- **Model choice**: the skill never selects models, reasoning settings, or client versions, and a model upgrade is not a reason to migrate an OKF version.

## Agent instruction files

The skill updates instruction files as living docs and keeps shared rules in `AGENTS.md`. Claude Code reads `AGENTS.md` directly when a project has no `CLAUDE.md`, so this repository has no `CLAUDE.md`. A project that needs Claude-specific rules adds a `CLAUDE.md` that imports `@AGENTS.md` and holds only those rules. Details and sources are in the maintenance standard.

## Verification boundary

Repository checks enforce the format, size limits, links, and installer parity. They do not measure triggering quality or behavior across models and hosts. Forward-test realistic requests on a host after substantial skill changes.
