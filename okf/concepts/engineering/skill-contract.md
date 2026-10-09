---
type: Skill Contract
title: OKF and doc-sync standard
description: Defines the default combined completion gate for living documentation and OKF project knowledge.
tags: [codex, doc-sync, okf, governance]
generated:
  by: process:doc-sync
  at: 2026-10-09T14:58:36+08:00
sources:
  - id: skill
    resource: ../../../skills/doc-sync/SKILL.md
  - id: okf-spec
    resource: https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/ad30107c31c06aec8a7d5636e0d1058118604e6f/SPEC.md
  - id: maintenance-standard
    resource: ../../../skills/doc-sync/references/doc-maintenance.md
  - id: architecture
    resource: ../../../docs/architecture.md
---

# Contract

The canonical [`doc-sync` skill](../../../skills/doc-sync/SKILL.md) synchronizes authoritative living docs and an OKF bundle after confirmed project meaning changes. New bundles use v0.2; existing project version pins are preserved. A durable project does not need to opt into OKF separately.

The skill is a host-neutral Agent Skill; see [Host compatibility](host-compatibility.md). Its [maintenance standard](../../../skills/doc-sync/references/doc-maintenance.md) decides which surfaces a change affects, including agent instruction files, where content belongs, and how one source of truth is kept, citing official model, harness, and industry sources.

Living docs remain authoritative. OKF provides progressive disclosure, metadata, citations, and project knowledge links. Historical artifacts remain historical unless the project explicitly treats them as current.

Generic OKF consumption remains tolerant of unknown versions, types, fields, missing optional indexes, and broken links. DocSync selects a stricter producer profile from root `okf_version`. Both versions require coverage and navigable concepts; v0.1 uses `timestamp` and citations, while v0.2 uses `generated` and structured `sources`. These are project policies beyond upstream conformance.

# Status discipline

Operational and project claims distinguish current active, inactive fallback, historical verification, pending verification, and retired/removed states.

In v0.2, generation, verification, and source freshness are separate facts. Lifecycle `stable` does not establish runtime acceptance, and a structural pass does not justify a human verifier or an attestation.

# Scope discipline

Update living facts and concepts affected by the confirmed change; update navigation and coverage mappings only when they change. Valid governance entrypoints and unrelated concepts need no rewrite for a local edit. Durable initialization still establishes default OKF governance. Resolve routine documentation choices from available authorization and evidence. Fix in-scope defects; report pre-existing external-scope failures without claiming whole-bundle success or initiating unrelated repairs. A whole-project publishing gate remains binding. See [Host compatibility](host-compatibility.md).
