# okf-doc-sync repository instructions

## Scope and source of truth

- This repository is the canonical source for the host-neutral `doc-sync` Agent Skill and its OKF tooling.
- Edit `skills/doc-sync/` here. Do not edit installed copies such as `~/.codex/skills/doc-sync`, `~/.agents/skills/doc-sync`, or `~/.claude/skills/doc-sync`; they are mirrors produced by `scripts/install.py`.
- This repository is public. Never commit machine-specific absolute paths, private project or employer names, personal records, or secrets; keep such records in a private repository.
- Treat [GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format) as the current format authority. The old `knowledge-catalog/okf` directory is frozen. Use the pinned references for v0.1 compatibility and v0.2 production; record stricter project policies separately.

## Mandatory OKF and doc sync

- Use the repository's `doc-sync` skill after confirmed changes to logic, behavior, scope, interfaces, contracts, status claims, installation, validation, or governance.
- OKF is the default project knowledge format; it does not require a separate user opt-in or an existing OKF declaration.
- Synchronize affected authoritative living docs and OKF concepts; update indexes, coverage, citations, and cross-links when their facts or navigation change, and log meaningful knowledge changes. Valid entrypoints and unrelated concepts do not need a rewrite for every edit.
- Preserve historical records as history. Distinguish current, inactive fallback, historical, pending, and retired states.
- This repository maintains OKF v0.2 and a backwards-compatible v0.1 validator profile. Preserve other projects' version pins and update vendored skills only when their repository is in scope.

## Change and validation rules

- Keep `SKILL.md` concise and host-neutral: no host tool names, model names, or fixed install paths, and frontmatter limited to `name` and `description`. Place detailed rules in `skills/doc-sync/references/`, host-specific policy in `docs/`, and deterministic checks in `skills/doc-sync/scripts/`.
- Ground maintenance rules in cited official or industry sources and record the check date in `references/doc-maintenance.md`.
- Read the documents and references affected by the change; routine edits do not require a full repository tour. Complete authorized local edits, validation, and fixes without an extra review pause.
- Preserve unknown OKF frontmatter keys and tolerate unknown concept types when consuming bundles.
- Prefer file-relative Markdown links for repository portability; validators must accept both relative and bundle-root-absolute OKF links.
- Run all of the following before publishing:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
git diff --check
```

- When you maintain a local installed mirror, also run `python3 scripts/install.py --check` with its `--host` or `--target`.

- Review the complete diff and do not stage unrelated changes or secrets.
- Once the applicable checks pass, repeat or broaden them only for new changes, failures, or unresolved concerns. Publishing retains all gates above.
