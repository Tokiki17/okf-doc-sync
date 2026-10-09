# okf-doc-sync

`okf-doc-sync` (DocSync) is the canonical repository for `doc-sync`, a host-neutral [Agent Skill](https://agentskills.io/specification) that any agent harness, model, or person can use. The skill combines two completion gates:

1. synchronize authoritative living documentation, including agent instruction files, after meaning changes, without omissions or duplicated sources, following a [maintenance standard](skills/doc-sync/references/doc-maintenance.md) distilled from model, harness, and industry guidance; and
2. maintain an [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/open-knowledge-format) knowledge bundle by default, using v0.2 for new bundles and preserving existing version pins.

Projects no longer need to opt into OKF manually. During durable initialization or authorized governance repair, `doc-sync` establishes the minimal OKF governance spine while keeping project living docs authoritative. Local synchronization updates affected facts and navigation; valid entrypoints and unrelated coverage rows need no rewrite. Pre-existing governance defects outside the authorized scope are reported with their validation impact.

## Quick start

```bash
git clone https://github.com/Tokiki17/okf-doc-sync.git
cd okf-doc-sync
python3 scripts/install.py --host claude   # or: --host agents, default Codex, or --target DIR/doc-sync
```

Then ask your agent to sync the project's docs after a change, or invoke the skill by name (`/doc-sync` in Claude Code, `$doc-sync` in Codex).

## Repository layout

- `skills/doc-sync/` — canonical installable Agent Skill; `agents/openai.yaml` is optional Codex metadata that other hosts ignore.
- `skills/doc-sync/references/` — cited documentation maintenance standard, OKF interpretation, and project policies.
- `skills/doc-sync/scripts/` — reusable OKF validator shipped with the skill.
- `scripts/install.py` — installs or checks a host's mirror (`--host codex|agents|claude` or `--target`).
- `scripts/validate_repo.py` — validates this repository's structure, links, skill metadata, and OKF bundle.
- `tests/` — regression tests for installation, repository validation, Markdown link parsing, and OKF/DocSync profile behavior.
- `docs/` — authoritative architecture and maintenance documentation.
- `okf/` — this project's own OKF v0.2 knowledge bundle.

## Install

Install the canonical skill into a host's skills directory. Each command copies the same tree; see [Host compatibility](docs/host-compatibility.md) for the default targets and duplicate-name cautions.

```bash
python3 scripts/install.py                  # Codex: ${CODEX_HOME:-~/.codex}/skills/doc-sync
python3 scripts/install.py --host agents    # Codex and other .agents readers: ~/.agents/skills/doc-sync
python3 scripts/install.py --host claude    # Claude Code: ${CLAUDE_CONFIG_DIR:-~/.claude}/skills/doc-sync
python3 scripts/install.py --target DIR/doc-sync
```

If an existing installation differs, the installer refuses to overwrite it. Review the reported paths, then rerun with `--force` to keep the old tree as a rollback backup in `.doc-sync-install/backup` beside the skills root and install the canonical source. Check that an installed mirror is byte-for-byte current with the same host or target:

```bash
python3 scripts/install.py --host claude --check
```

Without skill support, follow [`SKILL.md`](skills/doc-sync/SKILL.md) directly and run `python3 skills/doc-sync/scripts/validate_okf.py <project>/okf --doc-sync-profile`.

## Validate

The package requires Python 3.10+ and PyYAML. Use a compatible interpreter to create a project-local virtual environment, then install the declared dependencies there. Without PyYAML, the standalone validator falls back to system Ruby's YAML parser.

```bash
python3 -m venv .venv  # Use Python 3.10+ for this command.
.venv/bin/python -m pip install .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_repo.py
git diff --check
```

The upstream OKF conformance model deliberately tolerates broken links, missing optional navigation files, unknown versions, and unknown extensions when consuming bundles. `--doc-sync-profile` selects the stricter profile from root `okf_version`: v0.1 retains `timestamp` and numbered citations; v0.2 uses `generated` and structured `sources`. Both profiles require coverage, index reachability, metadata, and strict maintained links. See the [v0.2 reference](skills/doc-sync/references/okf-v0.2.md) and [v0.1 compatibility policy](skills/doc-sync/references/okf-v0.1.md).

## Contributing and releases

Read [`AGENTS.md`](AGENTS.md) and the [maintenance workflow](docs/maintenance.md). Make changes here, validate them, and reinstall any local mirror with `--check`. Project-local vendored copies are updated only when work in those projects next invokes doc-sync; they are not bulk-rewritten from here.

## License

[MIT](LICENSE)
