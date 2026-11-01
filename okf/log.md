# okf-doc-sync knowledge update log

## 2026-11-01

* **Windows test portability**: The `--host agents` installer test now isolates the home directory through `USERPROFILE` as well as `HOME`, fixing a Windows-only failure reported against `771303b`. CI adds a Windows and macOS unit-test job; [installation and validation](concepts/engineering/install-and-validation.md) records the platform coverage. Production path logic is unchanged.

## 2026-10-09

* **Public release**: Published the host-neutral `doc-sync` Agent Skill, its OKF validator, installer, tests, and [maintenance standard](../skills/doc-sync/references/doc-maintenance.md) under MIT as the canonical source, with a fresh history. Personal synchronization records stay in a private repository. Added a [shareable-content rule](../skills/doc-sync/references/doc-maintenance.md#shareable-content) and a repository check that rejects home-directory paths. Upstream OKF `main` was at the pinned `ad30107`.
