# okf-doc-sync repository instructions

This public repository is the canonical source of the host-neutral `doc-sync` Agent Skill. Edit `skills/doc-sync/` here; copies in a host's skills directory are mirrors written by `scripts/install.py` and are never edited directly. The [documentation index](docs/index.md) lists every maintained doc.

## Before you change something

| Change | Read first | Stop reading when |
| --- | --- | --- |
| `SKILL.md` text or frontmatter, `agents/openai.yaml` | [Portability contract](docs/host-compatibility.md#portability-contract) | the frontmatter keys, size limits, and host-neutral wording rules are clear |
| A documentation rule in the maintenance standard | [Its sources](skills/doc-sync/references/doc-maintenance.md#sources) | the rule is backed by a cited source or marked as DocSync policy |
| `validate_docs.py` behavior | [Validation](docs/architecture.md#validation) | you know which masking layer or reachability edge the change touches |
| `scripts/install.py` behavior | [Source and installation](docs/architecture.md#source-and-installation) | you know the work-root, cross-device, and recovery rules |
| CI, supported Python, or release steps | [Maintenance](docs/maintenance.md) | — |

Changes inside one function that keep its behavior, new tests for existing behavior, and typo fixes need no doc reading.

## Rules the code does not show

- Never commit machine-specific absolute paths, private project or employer names, personal records, or secrets. The self-check rejects home-directory paths.
- Runtime code and tests use only the Python 3.10+ standard library; there are no third-party dependencies to install.
- `SKILL.md` stays host-neutral: no host tool names, model names, or fixed install paths, and frontmatter holds only `name` and `description`.
- There is no `CLAUDE.md`; Claude Code reads this file directly. Add one only for Claude-specific rules, starting with `@AGENTS.md`.

## Keeping docs in sync

If a change alters, or adds a cross-session rule about, the behavior, constraints, commands, status, or paths that an authoritative doc or this file describes, update the affected places. When none of those facts changed, leave the existing docs untouched.

## Validation

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
git diff --check
```

When you maintain a local installed mirror, also run `python3 scripts/install.py --check` with its `--host` or `--target`. Review the complete diff and stage only what belongs to the change.
