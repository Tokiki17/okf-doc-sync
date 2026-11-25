# Maintenance

## Change workflow

1. Keep the repository shareable: no machine-specific absolute paths, private project names, employer details, or personal records.
2. Identify the confirmed change and the affected skill files, docs, and tests. Follow the routes in [AGENTS.md](../AGENTS.md) before editing.
3. Edit only the canonical `skills/doc-sync/` source and the related docs and tests.
4. Run the validation commands below.
5. Install the skill into each local mirror you maintain and verify parity.
6. Review the full diff; commit or push only when requested.

When a rule source changes, update the [maintenance standard](../skills/doc-sync/references/doc-maintenance.md) and its check date. When a host changes discovery or metadata rules, update [Host compatibility](host-compatibility.md).

## Validation commands

Use any Python 3.10 or newer; nothing needs to be installed.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
python3 scripts/install.py
python3 scripts/install.py --check
git diff --check
```

Repeat `install.py` and `install.py --check` with the `--host` or `--target` of every other installed mirror on this machine, such as `--host claude`. When available, also run host validators against `skills/doc-sync/`, such as Codex skill-creator's `quick_validate.py` or the Agent Skills `skills-ref validate`.

CI runs the unit tests and `validate_repo.py` on Python 3.10 without installing packages, on Ubuntu, macOS, and Windows.

## Forward testing

Structural checks do not show whether a model finds hidden constraints or skips needless reading. After a substantial skill revision, compare one project snapshot before and after a doc-sync tidy-up, with the same model, permissions, global instructions, and skill visibility, a fresh directory and session per task, and task prompts that never mention docs:

- **Positive task:** a change that depends on a constraint the code does not show and alters a documented contract. Observe whether the model finds the constraint before editing, makes the change correctly, and updates the right authoritative doc.
- **Negative task:** a change confined to one module's internals. Observe whether the model edits the code directly, skips unrelated doc reading, and leaves the docs untouched.

The tidy-up session must not see the tasks or the scoring criteria. Report the actual trajectories; string-matching instructions is not a behavioral test. Keep fixtures free of private project material.

## Vendored project copies

Some projects may keep a repository-local copy of doc-sync. Do not bulk-update those repositories from this project. Update a vendored copy when that repository next enters doc-sync scope, then validate its declared parity contract.

## Release state

- `main` is the stable source branch.
- The public [`Tokiki17/okf-doc-sync`](https://github.com/Tokiki17/okf-doc-sync) repository is the canonical source and collaboration surface.
- The user-level installed directory is runtime state, not a second development branch.
