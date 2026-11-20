# okf-doc-sync knowledge update log

## 2026-11-20

* **OKF v0.3, latest only**: Upstream moved to [open-knowledge-format/open-knowledge-format](https://github.com/open-knowledge-format/open-knowledge-format) and the GoogleCloudPlatform repository was deprecated at `8a8ff87`. DocSync now maintains only v0.3, pinned to SPEC `527e81a` in the [OKF reference](../skills/doc-sync/references/okf.md). The v0.1 and v0.2 references and producer profiles are retired; the validator reads older bundles and reports them for migration with the compact [migration guide](../skills/doc-sync/references/okf-migration.md). This bundle migrated to v0.3 with root bundle metadata; its path fields were already file-relative. The [skill contract](concepts/engineering/skill-contract.md), [installation and validation](concepts/engineering/install-and-validation.md), and [coverage manifest](concepts/governance/coverage-manifest.md) record the change.

* [Delegation](../skills/doc-sync/references/delegation.md) now uses existing authorization or a saved preference on ordinary runs. Hosts without a policy use the main session. Persistent setup is invoked on request, and previously chosen reconfirmation policies still apply.

* **Delegated execution**: Added a host-neutral [delegation reference](../skills/doc-sync/references/delegation.md). It recommends a mid-capability tier, requires model options to come from the current host's exposed interface, official docs, or source code, and asks the user to choose explicitly. Setup, run after an agent installs the skill or at first use, proposes a delegation rule for the user-level instructions and narrow exceptions for conflicting rules, applied only after approval. It asks again only when the chosen option disappears or a better-ranked option appears, and keeps wording-only edits in the main session. [Host compatibility](concepts/engineering/host-compatibility.md) and the coverage manifest record it. No host adapter or installer change; behavior on real hosts is not yet forward-tested.

## 2026-11-01

* **Windows test portability**: The `--host agents` installer test now isolates the home directory through `USERPROFILE` as well as `HOME`, fixing a Windows-only failure reported against `771303b`. CI adds a Windows and macOS unit-test job; [installation and validation](concepts/engineering/install-and-validation.md) records the platform coverage. Production path logic is unchanged.

## 2026-10-09

* **Public release**: Published the host-neutral `doc-sync` Agent Skill, its OKF validator, installer, tests, and [maintenance standard](../skills/doc-sync/references/doc-maintenance.md) under MIT as the canonical source, with a fresh history. Personal synchronization records stay in a private repository. Added a [shareable-content rule](../skills/doc-sync/references/doc-maintenance.md#shareable-content) and a repository check that rejects home-directory paths. Upstream OKF `main` was at the pinned `ad30107`.
