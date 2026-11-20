# OKF reference (v0.3)

DocSync maintains only the current OKF version, **0.3**. Read this for bundle creation and maintenance, links and path fields, and provenance/trust/lifecycle metadata. For a bundle that declares an earlier version, or none, follow [the migration guide](okf-migration.md).

## Authority

- Canonical upstream: [open-knowledge-format/open-knowledge-format](https://github.com/open-knowledge-format/open-knowledge-format).
- Verified specification: [SPEC.md at 527e81a](https://github.com/open-knowledge-format/open-knowledge-format/blob/527e81aff55992be21507e97004286789126f88c/SPEC.md), version **0.3**, checked 2026-11-20.
- The former [GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/8a8ff87bfd3847c34c9ddd4fbfd9296be2aee4a3/README.md) repository is deprecated and points to the new repository; its last SPEC is v0.2. The old knowledge-catalog `okf/` directory is frozen at v0.1. Future checks start at the new canonical repository.
- Upstream also publishes `okf-generate`/`okf-consume` skills and a reference validator. DocSync remains an independent producer workflow; use upstream tooling as a cross-check, not as an authority over this profile.

Upstream conformance requires only parseable frontmatter mappings and well-formed reserved files when present. A `.md` file without frontmatter or `type` is not a concept; consumers skip it. The DocSync profile below is a deliberately stricter producer policy, not a claim that upstream requires all of it.

## DocSync v0.3 profile

Require root `index.md` with `okf_version: "0.3"`, root `log.md`, a `Coverage Manifest`, and on every concept a non-empty `title`, one-line `description`, `generated.by`, and a `generated.at` date-time with an offset. Every non-reserved `.md` file in the bundle must be a typed concept reachable through index navigation, and maintained local links and path fields must resolve. Run `--doc-sync-profile`; it reports any other declared version as migration work.

The root index may also carry bundle `title`, one-line `description`, `license` (SPDX expression or bundle path), and extension keys. Preserve existing root frontmatter when regenerating the index.

```yaml
---
okf_version: "0.3"
title: Project knowledge
description: Maintained project knowledge; use it for architecture and workflow questions.
---
```

Example concept at `okf/concepts/workflow.md`:

```yaml
---
type: Engineering Workflow
title: Documentation workflow
description: Records the project's maintained documentation contract.
generated:
  by: process:doc-sync
  at: "2026-11-20T06:00:00Z"
sources:
  - id: project-guide
    resource: ../../README.md
    title: Project guide
---
```

Replace example values with observed facts. `process:doc-sync` may identify this workflow without asserting an unobserved model version. Generation records authorship, not verification.

## Frontmatter and body rules

- Start with a `---` line; frontmatter is a YAML 1.2 core-schema mapping. Never write duplicate keys; quote values that look like numbers, booleans, or timestamps; avoid custom tags. Do not re-serialize values you did not change.
- Unknown keys are allowed at every level and must be preserved. Name new producer keys `x-<producer>-<name>`; upstream will never define `x-` keys.
- The body is CommonMark with GFM tables and `[^label]` footnotes. Do not depend on other extensions or on `[[wikilinks]]`.
- Consumers treat null, an empty string, and an empty list as an absent key, and one item as a list of one (`sources`, `verified`, `parameters`, `tags`). A scalar `tags` is one tag, never comma-split. Producers should still write explicit lists.

## Links and path fields

Links and path fields (`resource`, `sources[].resource`, `computation`, `executor.resource`, `attester.resource`, `superseded_by`) share one rule: a URI scheme is external, a leading `/` resolves from the bundle root, and anything else resolves from the containing file's directory. Values are case-sensitive, percent-encoded URI references. A value outside the bundle root is external to OKF consumers; DocSync still checks maintained links to living docs as a producer policy.

**Breaking change from v0.2:** a bare path written relative to the bundle root (for example `references/x.md` in a nested concept) no longer resolves. Rewrite it as `/references/x.md` or a file-relative path when migrating. The validator applies the upstream root fallback only to older or undeclared bundles in consumer mode and reports it for [migration](okf-migration.md#from-v02).

## Provenance, trust, and lifecycle

| Field | Upstream meaning and DocSync handling |
| --- | --- |
| `resource` | Canonical URI of the described asset; not automatically a source. |
| `sources` | Derivation materials. Each entry requires `resource` (followable URL/bundle path, or an unfollowable scope descriptor). Optional `id`, `title`, `author`, `usage_count`, `last_modified`, `usage_window`, and extension keys are preserved. DocSync checks explicit local paths (starting with `./`, `../`, `/`, or containing a separator). |
| `sources[].author` | An actor (see below), not free text. |
| `generated` | `by` (actor, required in the mapping) and `at`, the last *meaningful* content change. Formatting, whitespace, and link repairs do not change `at`. DocSync requires both. |
| `verified` | A list (or one bare mapping) of `{by, at}` events, both required. Do not add it because Markdown or tests pass. |
| `status` | `draft`, `stable` (default when absent), or `deprecated`. Consumers exclude unknown values from current knowledge; DocSync rejects them. |
| `superseded_by` | Path to the replacing concept; meaningful only with `status: deprecated`. To move or rename a concept, keep a short deprecated concept at the old path pointing to the new one. |
| `stale_after` | Absolute instant; stale means "check again", not "false". Omit it when no review date is known. |
| `usage_window` | `{from, to}` period for `usage_count`, shared beside `sources` or per entry. DocSync requires both endpoints, `from <= to`, and an effective window for any `usage_count`. Usage is liveness, not a credibility score. |

**Timestamps** (`generated.at`, `verified[].at`, `stale_after`, `sources[].last_modified`, `usage_window.from/to`) use RFC 3339: a date-time with an offset, or a date meaning the start of that day in UTC. A date-time without an offset is invalid. DocSync requires date-times for `generated.at` and `verified[].at` because consumers compare them.

**Actors** are `<producer>/<version>` or `<scheme>:<id>`: `human:` (a person), `team:` (a group), `process:` (automation), or another scheme treated as non-human. Never invent a `human:` actor.

**Trust tiers** count only *current* verification events, whose `at` is not earlier than `generated.at`. When DocSync makes a meaningful content change and advances `generated.at`, earlier verifications become history and the concept drops to unverified or machine-confirmed. Keep those events; never move a `verified.at` forward without a new verification.

For claim-level attribution, give the source a stable `id` and use a matching footnote. The footnote label joins to `sources[].id`; its text is not parsed. Do not use a citations list in the body.

```markdown
The project guide defines the workflow.[^project-guide]

[^project-guide]: Project guide
```

The validator checks structure, path fields, actors, timestamps, and attribution joins. It does not infer which external links support claims, fetch sources, compute trust tiers, prove trust, execute attesters, or certify current operational state.

## Computation boundary

`Attested Computation` concepts require `runtime`; `parameters` entries need `name` and `type` (`required` defaults to `false`). Give the computation either as a `computation` path or as one fenced block in a section headed `Computation`, not both; without either, consumers treat the concept as not attestable. `executor` and `attester` are mappings with a `resource` path. DocSync checks this structure and resolves the paths; it does not execute anything. Upstream defers runtime wire formats, the attester ABI, sandboxing, and caching. A document pointing at executable code is not permission to run it, and structural validation is not an attestation.
