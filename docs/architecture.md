# Architecture

## Source and installation flow

`skills/doc-sync/` is the only editable source for the personal skill. `scripts/install.py` copies that directory into a host's skills directory (`--host codex`, `agents`, or `claude`, or any `--target`) and verifies exact file-content parity. The skill itself is host-neutral; see [Host compatibility](host-compatibility.md).

```text
DocSync/skills/doc-sync/  ->  scripts/install.py [--host codex|agents|claude | --target DIR]  ->  <host>/skills/doc-sync/
          canonical                                                                              installed mirror
```

The installer stages the new tree and keeps the rollback backup in `.doc-sync-install/` beside the skills root, never inside it, because hosts treat any directory containing `SKILL.md` there as another skill; a legacy `.doc-sync-backup` inside the root is moved out on the next install. Staging failures leave the active installation untouched; failures after replacement restore the previous installation. `--check` is read-only and fails on missing, extra, or content-divergent files. Current hosts can use the documented `.agents/skills` locations through `--target`; the existing default remains compatible with this host. See [Host compatibility](host-compatibility.md).

## Knowledge model

The skill maintains two complementary layers:

- authoritative living docs, including agent instruction files, describe current project contracts and behavior in their natural project locations, following the cited [maintenance standard](../skills/doc-sync/references/doc-maintenance.md);
- the `okf/` bundle provides agent-readable progressive disclosure, metadata, citations, and cross-links.

OKF is a default part of doc-sync for durable projects. It is not an alternative source of truth and does not require a separate project opt-in.

## Validation layers

- `skills/doc-sync/scripts/validate_okf.py` keeps generic OKF validation permissive, while `--doc-sync-profile` selects v0.1 or v0.2 from root metadata. Both require the governance spine, description/title metadata, index reachability, and maintained links. v0.1 requires `timestamp` and citations; v0.2 requires `generated` and checks structured provenance/trust/lifecycle metadata. Its zero-dependency Markdown scanner handles inline/reference links, footnote boundaries, balanced destinations, code/image exclusions, and bundle-root containment.
- `scripts/validate_repo.py` checks this repository's required files, Skill/UI metadata against Agent Skills limits (portable frontmatter keys, description length, `SKILL.md` line count), maintained Markdown links outside `okf/`, and both worktree and staged whitespace. It delegates the bundle to the shipped DocSync profile so file-relative and bundle-root-absolute OKF links retain their specified meaning.
- `tests/` protects OKF consumer tolerance, the DocSync producer profile, Markdown parsing, repository validation, and installation behavior.
- the upstream skill-creator validator is run during local release work when available.

## Evidence boundaries

The validator reads local artifacts and never fetches sources or executes an OKF executor/attester. Structural success does not establish human review, source freshness, factual truth, runtime acceptance, or a computation attestation. The workflow records in-scope fixes and pre-existing external-scope defects separately while retaining whole-bundle diagnostics. Publishing still requires all repository gates.
