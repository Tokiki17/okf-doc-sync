---
type: Skill Contract
title: OKF and doc-sync standard
description: Defines the default combined completion gate for living documentation and OKF project knowledge.
tags: [codex, doc-sync, okf, governance]
generated:
  by: process:doc-sync
  at: 2026-11-20T15:26:48+09:00
sources:
  - id: skill
    resource: ../../../skills/doc-sync/SKILL.md
  - id: okf-spec
    resource: https://github.com/open-knowledge-format/open-knowledge-format/blob/527e81aff55992be21507e97004286789126f88c/SPEC.md
    title: OKF v0.3 specification
  - id: okf-reference
    resource: ../../../skills/doc-sync/references/okf.md
  - id: okf-migration
    resource: ../../../skills/doc-sync/references/okf-migration.md
  - id: maintenance-standard
    resource: ../../../skills/doc-sync/references/doc-maintenance.md
  - id: architecture
    resource: ../../../docs/architecture.md
---

# Contract

The canonical [`doc-sync` skill](../../../skills/doc-sync/SKILL.md) synchronizes authoritative living docs and an OKF bundle after confirmed project meaning changes. DocSync maintains only the current OKF version (v0.3); bundles declaring v0.1, v0.2, or no version are upgraded within their project's sync scope using a compact [migration guide](../../../skills/doc-sync/references/okf-migration.md).[^okf-migration] A durable project does not need to opt into OKF separately.

The skill is a host-neutral Agent Skill; see [Host compatibility](host-compatibility.md). Its [maintenance standard](../../../skills/doc-sync/references/doc-maintenance.md) decides which surfaces a change affects, including agent instruction files, where content belongs, and how one source of truth is kept, citing official model, harness, and industry sources.

Living docs remain authoritative. OKF provides progressive disclosure, metadata, citations, and project knowledge links. Historical artifacts remain historical unless the project explicitly treats them as current.

Generic OKF consumption remains tolerant of unknown versions, types, fields, missing optional indexes, and broken links. The stricter DocSync producer profile requires coverage, navigable concepts, `generated`, and structured `sources`, and reports older declared versions as migration work. It follows the [OKF v0.3 specification](https://github.com/open-knowledge-format/open-knowledge-format/blob/527e81aff55992be21507e97004286789126f88c/SPEC.md),[^okf-spec] now maintained in the `open-knowledge-format` organization after the GoogleCloudPlatform repository was deprecated, as summarized in the [OKF reference](../../../skills/doc-sync/references/okf.md).[^okf-reference] These are project policies beyond upstream conformance.

# Status discipline

Operational and project claims distinguish current active, inactive fallback, historical verification, pending verification, and retired/removed states.

Generation, verification, and source freshness are separate facts. In v0.3 only verifications at or after `generated.at` are current, so a meaningful rewrite leaves earlier verifications as history. Lifecycle `stable` does not establish runtime acceptance, and a structural pass does not justify a human verifier or an attestation.

# Scope discipline

Update living facts and concepts affected by the confirmed change; update navigation and coverage mappings only when they change. Valid governance entrypoints and unrelated concepts need no rewrite for a local edit. Durable initialization still establishes default OKF governance. Resolve routine documentation choices from available authorization and evidence. Fix in-scope defects; report pre-existing external-scope failures without claiming whole-bundle success or initiating unrelated repairs. A whole-project publishing gate remains binding. See [Host compatibility](host-compatibility.md).

[^okf-spec]: OKF v0.3 specification
[^okf-reference]: OKF reference
[^okf-migration]: OKF migration guide
