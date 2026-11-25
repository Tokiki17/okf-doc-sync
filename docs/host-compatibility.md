# Host compatibility

DocSync ships one host-neutral skill that any agent harness supporting the [Agent Skills specification](https://agentskills.io/specification) can load. An agent or person without skill support can follow `skills/doc-sync/SKILL.md` directly and run the checker as a command.

## Portability contract

- **Format**: `skills/doc-sync/` follows the Agent Skills layout: `SKILL.md`, `references/`, and `scripts/`. References are linked one level deep from `SKILL.md`, which stays under 500 lines.
- **Frontmatter**: only `name` and `description`. This is the set every checked consumer accepts: the Agent Skills specification, Codex's skill-creator validator (which rejects `compatibility`), and the claude.ai and Claude API upload validator (which rejects Claude Code-only keys). Runtime requirements live in the body instead of a `compatibility` field.
- **Description**: third person, what the skill does first and when to use it second, under 1,024 characters, as the [Anthropic authoring guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) and [Codex skills guide](https://learn.chatgpt.com/docs/build-skills) both recommend.
- **Body**: no host tool names, model names, or fixed install paths. Paths are relative to the skill directory; the only executable dependency is Python 3.10+ with its standard library.
- **Host extras**: `agents/openai.yaml` is optional Codex UI and invocation metadata, and its `short_description` stays within 25–64 characters for skill-creator. Other hosts ignore the file, and it stays in the tree so every installed mirror has the same parity check.
- **Maintenance rules**: [the maintenance standard](../skills/doc-sync/references/doc-maintenance.md) cites model, harness, and industry sources with a check date. Update that file, not host-specific copies, when a source changes.

## Installation by host

`scripts/install.py` copies the same tree and verifies byte-for-byte parity. Use the same `--host` or `--target` for `--check`.

| Host | Command | Default target |
| --- | --- | --- |
| Codex (default) | `python3 scripts/install.py` | `${CODEX_HOME:-~/.codex}/skills/doc-sync` |
| Shared `.agents` readers | `python3 scripts/install.py --host agents` | `~/.agents/skills/doc-sync` |
| Claude Code | `python3 scripts/install.py --host claude` | `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/doc-sync` |
| Gemini CLI | `python3 scripts/install.py --host gemini` | `${GEMINI_CLI_HOME:-~}/.gemini/skills/doc-sync` |
| Google Antigravity | `python3 scripts/install.py --host antigravity` | `~/.gemini/config/skills/doc-sync` |
| Cursor | `python3 scripts/install.py --host cursor` | `${CURSOR_CONFIG_DIR:-~/.cursor}/skills/doc-sync` |
| GitHub Copilot (CLI / VS Code) | `python3 scripts/install.py --host copilot` | `${COPILOT_HOME:-~/.copilot}/skills/doc-sync` |
| Windsurf | `python3 scripts/install.py --host windsurf` | `~/.codeium/windsurf/skills/doc-sync` |
| OpenCode | `python3 scripts/install.py --host opencode` | `${OPENCODE_CONFIG_DIR:-${XDG_CONFIG_HOME:-~/.config}/opencode}/skills/doc-sync` |
| DeepSeek Harness | `python3 scripts/install.py --host dsh` | `${DSH_HOME:-~/.dsh}/skills/doc-sync` |
| Any other harness or project scope | `python3 scripts/install.py --target <dir>/doc-sync` | The given directory |

Install only one copy per skill root a host scans:

- **Shared `~/.agents/skills` overlap**: Codex, Gemini CLI, Cursor, GitHub Copilot, and DeepSeek Harness scan `~/.agents/skills` in addition to their own user directory, and `.agents`-native harnesses (such as Goose, Amp, Roo Code, and Kiro) read `~/.agents/skills` directly. Choose either `--host agents` for shared coverage or per-host `--host` installs, and do not install both `~/.codex` and `~/.agents` copies on one Codex host (which does not merge same-named skills).
- **Cross-tool `~/.claude/skills` overlap**: GitHub Copilot also scans `~/.claude/skills` for personal skills, so a machine that already maintains `--host claude` needs no separate `--host copilot` copy unless `COPILOT_HOME` is isolated.
- **Hot reload**: Claude Code and DeepSeek Harness pick up edits to existing skill directories within a session; a newly created top-level skills directory in Claude Code needs `/reload-skills`.

## Host notes

- **Codex**: loads a capped catalog of names, descriptions, and paths first and reads `SKILL.md` on selection, so the description front-loads the task and triggers. `agents/openai.yaml` keeps implicit invocation enabled. Codex lists `.agents/skills` roots; existing `~/.codex/skills` installs keep working. Resolve resource-backed skill locators through the host instead of assuming a local path. [Codex skills guide](https://learn.chatgpt.com/docs/build-skills)
- **Claude Code**: loads personal skills from `~/.claude/skills` and project skills from `.claude/skills`, and provides the skill's base directory when it loads the skill. Edits to existing skill directories apply within a session. [Claude Code skills](https://code.claude.com/docs/en/skills)
- **Gemini CLI and Antigravity**: Gemini CLI reads user skills from `~/.gemini/skills` (`$GEMINI_CLI_HOME/.gemini/skills` when `GEMINI_CLI_HOME` is set), whereas Antigravity's global discovery root is `~/.gemini/config/skills` (workspace `.agents/skills` works in both).
- **Cursor, GitHub Copilot, Windsurf, OpenCode, and DeepSeek Harness**: all read standard `SKILL.md` directories with progressive disclosure (`name` and `description` at discovery, body and bundled scripts on activation) and ignore `agents/openai.yaml`.
- **Model and execution choice**: the skill never selects models, reasoning settings, or client versions, and defines no delegation protocol. Routine synchronization runs in the current session; whether a large task is split up is the host's decision.

## Agent instruction files

The skill treats instruction files as the project entrypoint and keeps shared rules in `AGENTS.md`, which Codex, Gemini CLI, Antigravity, Cursor, GitHub Copilot, Windsurf, OpenCode, and DeepSeek Harness all read directly. Claude Code also reads `AGENTS.md` directly when a project has no `CLAUDE.md`, so this repository has no `CLAUDE.md`. A project that needs Claude-specific rules adds a `CLAUDE.md` that imports `@AGENTS.md` and holds only those rules; the checker warns when a root `CLAUDE.md` lacks that import. Details and sources are in the maintenance standard.

## Verification boundary

Repository checks enforce the format, size limits, links, navigation, and installer parity. They do not measure triggering quality or behavior across models and hosts. Forward-test realistic requests on a host after substantial skill changes.
