# okf-doc-sync

`okf-doc-sync` (DocSync) is the canonical repository for `doc-sync`, a host-neutral [Agent Skill](https://agentskills.io/specification) that any agent harness, model, or person can use. It helps an agent enter a project quickly, find the constraints the code does not show, make the change correctly, and keep the one authoritative document for each fact current:

- **Read-time routing.** The project entrypoint (`AGENTS.md`, a host file that imports it, or `README.md`) says which contract to read before which kind of change, and when no further reading is needed. Routes exist only where the code alone would mislead.
- **Conditional write-time rule.** Docs change only when a change alters, or adds a cross-session rule about, a described behavior, constraint, command, status, or path. Otherwise they stay untouched.
- **Single layer.** Each fact lives in one authoritative living doc, following a [maintenance standard](skills/doc-sync/references/doc-maintenance.md) distilled from model, harness, and industry guidance. There is no parallel knowledge bundle.

The repository name is historical; the skill no longer maintains Open Knowledge Format bundles.

## Quick start

```bash
git clone https://github.com/Tokiki17/okf-doc-sync.git
cd okf-doc-sync
python3 scripts/install.py --host claude   # or: codex (default), agents, gemini, antigravity, cursor, copilot, windsurf, opencode, dsh
```

Then ask your agent to sync the project's docs after a change, or invoke the skill by name (`/doc-sync` in Claude Code or Cursor, `$doc-sync` in Codex).

## Repository layout

- `skills/doc-sync/` — the installable Agent Skill; `agents/openai.yaml` is optional Codex metadata that other hosts ignore.
- `skills/doc-sync/references/` — the cited documentation maintenance standard.
- `skills/doc-sync/scripts/` — the zero-dependency documentation checker shipped with the skill.
- `scripts/install.py` — installs or checks a host's mirror (`--host <host>` or `--target`).
- `scripts/validate_repo.py` — this repository's self-check.
- `tests/` — regression tests for the checker, the installer, and the self-check.
- `docs/` — architecture, host compatibility, and maintenance documentation.

## Install

Each command copies the same tree; see [Host compatibility](docs/host-compatibility.md) for all built-in `--host` targets, environment variable overrides, and duplicate-name cautions.

```bash
python3 scripts/install.py                      # Codex: ${CODEX_HOME:-~/.codex}/skills/doc-sync
python3 scripts/install.py --host agents        # Shared .agents readers: ~/.agents/skills/doc-sync
python3 scripts/install.py --host claude        # Claude Code: ${CLAUDE_CONFIG_DIR:-~/.claude}/skills/doc-sync
python3 scripts/install.py --host gemini        # Gemini CLI: ${GEMINI_CLI_HOME:-~}/.gemini/skills/doc-sync
python3 scripts/install.py --host antigravity   # Antigravity: ~/.gemini/config/skills/doc-sync
python3 scripts/install.py --host cursor        # Cursor: ${CURSOR_CONFIG_DIR:-~/.cursor}/skills/doc-sync
python3 scripts/install.py --host copilot       # GitHub Copilot: ${COPILOT_HOME:-~/.copilot}/skills/doc-sync
python3 scripts/install.py --host windsurf      # Windsurf: ~/.codeium/windsurf/skills/doc-sync
python3 scripts/install.py --host opencode      # OpenCode: ${OPENCODE_CONFIG_DIR:-${XDG_CONFIG_HOME:-~/.config}/opencode}/skills/doc-sync
python3 scripts/install.py --host dsh           # DeepSeek Harness: ${DSH_HOME:-~/.dsh}/skills/doc-sync
python3 scripts/install.py --target DIR/doc-sync
```

If an existing installation differs, the installer refuses to overwrite it. Review the reported paths, then rerun with `--force`; the old tree is kept as a rollback backup outside the skills root (see [Architecture](docs/architecture.md#source-and-installation)). Check that a mirror is byte-for-byte current with the same host or target:

```bash
python3 scripts/install.py --host claude --check
```

Without skill support, follow [`SKILL.md`](skills/doc-sync/SKILL.md) directly and run:

```bash
python3 skills/doc-sync/scripts/validate_docs.py <project-root>
```

## Validate

Python 3.10 or newer with only the standard library; there is nothing to install.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
git diff --check
```

## Contributing

Read [`AGENTS.md`](AGENTS.md) and the [maintenance workflow](docs/maintenance.md). Make changes here, validate them, and reinstall any local mirror with `--check`. Project-local vendored copies are updated only when work in those projects next invokes doc-sync.

## License

[MIT](LICENSE)
