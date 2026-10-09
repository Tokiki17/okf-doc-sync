# Maintenance

## Change workflow

1. Keep the repository shareable: no machine-specific absolute paths, private project names, employer details, or personal records. `validate_repo.py` rejects home-directory paths.
1. Identify the confirmed change and affected skill, docs, or tests. For format or compatibility changes, review the canonical [open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format) specification, record repository/SPEC revisions, and check transfer notices before trusting an old URL. Local wording or scope guidance does not require a fresh format audit.
2. Edit only the canonical `skills/doc-sync/` source and related living docs/tests.
3. Run tests and repository validation.
4. Install the skill and verify byte-for-byte parity.
5. Synchronize affected v0.2 concepts and the update log; change indexes and coverage only where their navigation or mappings changed. Run repository validation after these edits.
6. Review the full diff; commit or push only when requested.

Treat `--doc-sync-profile` as a whole-bundle structural producer gate. This repository must pass it before publishing. For scoped maintenance elsewhere, repair in-scope defects, record pre-existing defects outside the authorized scope and their failed checks, and never claim whole-bundle success while errors remain. This does not silently waive a project's stronger gate. Review factual source quality, status semantics, and coverage claims separately.

## Validation commands

Prepare the [isolated dependency environment](../README.md#validate) with Python 3.10+ when needed. Keep the repository's required `python3` commands and additionally verify the supported PyYAML path through `.venv/bin/python` after parser changes; the system Ruby fallback is exercised when PyYAML is absent.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
python3 scripts/install.py
python3 scripts/install.py --check
git diff --check
```

Repeat `install.py` and `install.py --check` with the `--host` or `--target` of every other installed mirror on this machine, such as `--host claude`.

When a rule source changes, update the [maintenance standard](../skills/doc-sync/references/doc-maintenance.md) and its check date; when a host changes discovery or metadata rules, update [Host compatibility](host-compatibility.md).
When available, also run host validators against `skills/doc-sync/`, such as Codex skill-creator's `quick_validate.py` or the Agent Skills `skills-ref validate`.

For a substantial skill revision, forward-test realistic requests in temporary projects, including a new v0.2 bundle and a pinned v0.1 project. Verify the resulting artifacts and scope behavior; string-matching instructions is not a behavioral test. Keep fixtures free of private project material.

## Vendored project copies

Some projects may keep a repository-local copy of doc-sync. Do not bulk-update those repositories from this project. Update a vendored copy when that repository next enters doc-sync scope, then validate its declared parity contract.

## Release state

- `main` is the stable source branch.
- The public [`Tokiki17/okf-doc-sync`](https://github.com/Tokiki17/okf-doc-sync) repository is the canonical source and collaboration surface.
- The user-level installed directory is runtime state, not a second development branch.
