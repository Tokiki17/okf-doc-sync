---
type: Coverage Manifest
title: Documentation and OKF coverage
description: Maps DocSync concerns to their authoritative living documents and knowledge concepts.
tags: [governance, coverage, documentation]
generated:
  by: process:doc-sync
  at: 2026-10-09T14:58:36+08:00
sources:
  - id: governance
    resource: ../../../AGENTS.md
  - id: navigation
    resource: ../../../docs/index.md
---

# Coverage

| Concern | Authoritative living source | OKF concept | Status |
| --- | --- | --- | --- |
| Skill behavior | [`skills/doc-sync/SKILL.md`](../../../skills/doc-sync/SKILL.md) | [Skill contract](../engineering/skill-contract.md) | Current active |
| Repository governance | [`AGENTS.md`](../../../AGENTS.md) | [Skill contract](../engineering/skill-contract.md) and [Installation and validation](../engineering/install-and-validation.md) | Current active |
| Project overview | [`README.md`](../../../README.md) | [OKF index](../../index.md) | Current active |
| Source/install boundary | [Architecture](../../../docs/architecture.md) | [Installation and validation](../engineering/install-and-validation.md) | Current active |
| Maintenance and release | [Maintenance](../../../docs/maintenance.md) | [Installation and validation](../engineering/install-and-validation.md) | Current active |
| Automated validation | [`scripts/validate_repo.py`](../../../scripts/validate_repo.py) and [`tests/`](../../../tests/) | [Installation and validation](../engineering/install-and-validation.md) | Current active |
| Continuous integration | [CI workflow](../../../.github/workflows/ci.yml) | [Installation and validation](../engineering/install-and-validation.md) | Current active |
| Project navigation | [Documentation index](../../../docs/index.md) | [OKF index](../../index.md) | Current active |
| Format interpretation | [OKF v0.2 reference](../../../skills/doc-sync/references/okf-v0.2.md) and [v0.1 compatibility](../../../skills/doc-sync/references/okf-v0.1.md) | [Skill contract](../engineering/skill-contract.md) | Current active |
| Markdown and profile validation | [`validate_okf.py`](../../../skills/doc-sync/scripts/validate_okf.py) | [Installation and validation](../engineering/install-and-validation.md) | Current active |
| Host portability and installation | [Host compatibility](../../../docs/host-compatibility.md) | [Host compatibility](../engineering/host-compatibility.md) | Current active policy |
| Documentation maintenance rules | [Maintenance standard](../../../skills/doc-sync/references/doc-maintenance.md) | [Skill contract](../engineering/skill-contract.md) | Current active; sources checked 2026-10-09 |

# Coverage boundaries

- **Vendored copies**: projects that vendor doc-sync update their copy when they next enter doc-sync scope; this repository does not bulk-edit them.
- **Behavior evidence**: repository checks cover structure and parity, not cross-host triggering quality.
