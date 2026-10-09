# OKF v0.2 producer and migration reference

Read this for new bundles, a scoped v0.2 migration, or provenance/trust metadata. For a pinned v0.1 bundle use [the compatibility reference](okf-v0.1.md).

## Authority

- Canonical upstream: [GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format).
- Verified specification: [SPEC.md at ad30107](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/ad30107c31c06aec8a7d5636e0d1058118604e6f/SPEC.md), version **0.2**, checked 2026-09-05.
- The old [knowledge-catalog/okf directory is frozen](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/fbbc7975388288244dfc62aea0066600b25b7c47/okf/README.md). Future checks start at the new canonical repository.

Upstream requires concept frontmatter with a non-empty `type` and the prescribed structure of reserved files when present. Other metadata is optional, and unknown fields/types remain valid. The following DocSync profile is a deliberately stricter producer policy, not a claim that upstream requires all of it.

## DocSync v0.2 profile

Require root `index.md` with `okf_version: "0.2"`, root `log.md`, a `Coverage Manifest`, non-empty `title`, one-line `description`, `generated.by`, and a timezone-aware `generated.at` on every concept. Require index reachability and maintained local links to resolve. Use `--doc-sync-profile`; it also continues to accept the v0.1 profile selected by a v0.1 root.

Example concept at `okf/concepts/workflow.md`:

```yaml
---
type: Engineering Workflow
title: Documentation workflow
description: Records the project's maintained documentation contract.
generated:
  by: process:doc-sync
  at: 2026-09-05T06:00:00Z
sources:
  - id: project-guide
    resource: ../../README.md
    title: Project guide
---
```

Replace example values with observed facts. `process:doc-sync` may identify this workflow without asserting an unobserved model version. Generation records authorship, not verification.

## Provenance, trust, and lifecycle

| Field | Upstream meaning and DocSync handling |
| --- | --- |
| `resource` | Canonical URI of the asset being described; it is not automatically the first source. |
| `sources` | Optional list of derivation materials. Each entry needs a non-empty `resource`. Optional `id`, `title`, `author`, `usage_count`, `last_modified`, and extension keys are preserved. Record the materials supporting factual claims; ordinary navigation is not automatically provenance. |
| `sources[].resource` | An external URI, a local artifact path, or a scope description such as `all queries in BigQuery project X`. DocSync checks explicit paths starting with `./`, `../`, `/`, or containing a directory separator, including spaces in filenames. Write a single local file as `./file.md`; a bare value such as `project.dataset.table` remains a descriptor. General descriptor meaning cannot be proved from a string. |
| `generated` | A mapping with an actor `by`; `at` records the last meaningful content change. DocSync requires both. Actors use `human:<id>`, `process:<id>`, or `<producer>/<version>` with non-empty components; never invent a human actor. |
| `verified` | Optional `{by, at}` mapping or list of such events. Do not add it merely because Markdown or tests pass. Record what was actually verified against which sources. |
| `status` | Optional `draft`, `stable`, or `deprecated`; upstream defaults to `stable`. Keep operational current/fallback/pending distinctions in the body separately. |
| `stale_after` | Optional absolute datetime; stale on or after that instant. Do not invent a universal deadline. |
| `usage_window` | Optional `{from, to}` datetimes framing source usage counts; may be shared beside `sources` or overridden per entry. DocSync requires both endpoints in a supplied window, `from <= to`, and an effective window for any supplied `usage_count`; these are stricter producer checks. Usage is not a credibility score. |

Every supplied timestamp-valued field uses an ISO 8601 datetime with an explicit UTC offset, including `generated.at`, verification events, source `last_modified`, `stale_after`, and usage-window endpoints. Do not confuse when a concept was edited with when its source changed or its facts were confirmed.

For claim-level attribution, give the source a stable `id` and use matching Markdown footnotes:

```markdown
The project guide defines the workflow.[^project-guide]

[^project-guide]: Project guide
```

The source ID joins attribution to `sources`; the footnote prose is not a file path. IDs must be unique; each actual attribution reference needs a footnote definition and a matching source ID. A source may have an ID without a body footnote. Code, escaped text, image labels, and ordinary inline-link labels are not attribution. Optional families and malformed known fields are best-effort consumer diagnostics; maintained producers must repair their supplied metadata. The validator checks structure, source links, and attribution joins. It does not infer which ordinary external links support claims, fetch external sources, prove trust, execute attesters, or certify current operational state. Review factual source coverage separately.

## Migration from v0.1

1. Confirm migration is in scope and the project's validator/consumers support v0.2. Preserve explicit project pins until that decision is made.
2. Keep unknown keys and useful history. Replace the timestamp contract with `generated`; use a known author/workflow and an evidence-backed edit time. Preserve an older timestamp as history if useful; never invent its author.
3. Convert each actual provenance entry from the final numbered `# Citations` list into `sources`. Keep ordinary navigation as navigation. Do not turn the concept's `resource` into evidence without inspecting it.
4. Update claim attribution where useful; retain historical citations when they remain meaningful. v0.2 does not require a legacy citations section.
5. Update the root version, governance, living docs, and indexes in the same change; run the complete producer gate. Do not migrate another repository implicitly.

Legacy v0.1 fields remain readable, but a v0.2 DocSync producer cannot satisfy its `generated` requirement with `timestamp` alone. Unverified legacy claims remain unverified after conversion.

## Computation boundary

`Attested Computation` is an optional specialized type with a `runtime` contract and optional parameters, computation, executor, and attester metadata. DocSync preserves this material and checks the declared runtime structure where supported; it does not add an execution service. Upstream explicitly defers runtime wire formats, the attester ABI, sandboxing, and caching. A document pointing at executable code is not permission to run it, and structural validation is not an attestation.
