---
type: Engineering Workflow
title: Installation and validation
description: Defines how the canonical skill is installed, compared, tested, and released.
tags: [installation, validation, codex]
generated:
  by: process:doc-sync
  at: 2026-11-01T19:15:09+08:00
sources:
  - id: installer
    resource: ../../../scripts/install.py
  - id: validation
    resource: ../../../skills/doc-sync/scripts/validate_okf.py
  - id: maintenance
    resource: ../../../docs/maintenance.md
---

# Source flow

[`skills/doc-sync/`](../../../skills/doc-sync/SKILL.md) is the unique editable source. [`scripts/install.py`](../../../scripts/install.py) deploys it to the user-level Codex skills directory and `--check` verifies exact file parity.

The working default remains the configured Codex home's `skills/doc-sync`; `--host agents` and `--host claude` target the shared `.agents` and Claude Code user skills directories, and `--target` supports any other root. See [Host compatibility](host-compatibility.md). Staging and the rollback backup live in `.doc-sync-install/` beside the skills root so hosts do not discover them as duplicate skills. Staging failures preserve the active installation; replacement failures restore the rollback backup. The installer does not replace symlink targets or manage duplicate discovered skills.

# Gates

- Unit tests separate permissive OKF conformance from the v0.1/v0.2 DocSync profiles and cover version dispatch, metadata, structured sources, coverage, index reachability, citation/footnote handling, maintained links, UTF-8, bundle-root containment, repository validation, and installation failures.
- Repository validation checks required files, parses Skill and UI metadata as YAML, verifies maintained links outside `okf/`, and checks both worktree and staged whitespace. It delegates bundle structure and links to `--doc-sync-profile`, preserving file-relative links to authoritative repository docs and bundle-root-absolute OKF links.
- Installation validates the canonical skill metadata before replacing the installed mirror.
- CI runs the full validation on Linux and the unit tests on Windows and macOS; tests that redirect the user home set both `HOME` and `USERPROFILE`.
- Local release validation also uses the installed Codex skill-creator checker when available.
- Git diff review protects historical docs and unrelated user changes.

Validator success proves structure, not factual source quality or status semantics; release review checks those claims against current evidence.

# Sources

- [Maintenance workflow](../../../docs/maintenance.md)
- [Coverage manifest](../governance/coverage-manifest.md)
