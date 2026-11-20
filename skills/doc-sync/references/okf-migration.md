# OKF migration guide

DocSync maintains only the current format described in [the OKF reference](okf.md). Read this guide when a bundle declares an earlier `okf_version`, or none. Upgrade it inside the project's authorized doc-sync scope; never migrate another repository implicitly.

## Historical sources

| Version | Pinned specification | Status |
| --- | --- | --- |
| 0.2 | [SPEC.md at ad30107](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/ad30107c31c06aec8a7d5636e0d1058118604e6f/SPEC.md) | Repository deprecated 2026-11-18 |
| 0.1 | [SPEC.md at ee67a5c](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/ee67a5ca27044ebe7c38385f5b6cffc2305a9c1a/okf/SPEC.md) | Directory frozen |

Cite these pinned files for historical semantics; moving `main` links describe later versions.

## Procedure

1. **Assess.** Run `validate_okf.py <bundle> --doc-sync-profile`. Older and undeclared bundles are still read, and the error list is the migration worklist. Consumer mode reports bare path fields that resolve only from the bundle root.
2. **Apply the version steps** below, oldest first. Keep unknown keys and useful body content.
3. **Finish.** Set root `okf_version: "0.3"` (optionally add `title`, one-line `description`, `license`); update governance and living docs that name the version; add a `log.md` entry; rerun the profile until it passes.

## From v0.1

- Replace `timestamp` with `generated: {by, at}`. Use the known workflow or author as the actor (for example `process:doc-sync`) and an evidence-backed date-time with an offset; never invent a `human:` author. Drop `timestamp` or keep it as an `x-` extension.
- Convert each provenance entry in the final numbered `# Citations` list to a `sources` entry with a stable `id`, and mark claims with `[^id]` footnotes. Keep ordinary navigation as links, and do not turn the concept's `resource` into a source without inspecting it. Remove the citations section once its entries are converted.
- The root index stops being version-only; nested indexes still take no frontmatter.
- Unverified legacy claims remain unverified; do not add `verified` during conversion.

## From v0.2

- Rewrite bare path fields written from the bundle root (`resource`, `sources[].resource`, `computation`, `executor.resource`, `attester.resource`) as `/`-prefixed or file-relative paths; v0.3 resolves bare values from the containing file's directory.
- Write `sources[].author` as an actor (`team:<id>` for groups).
- Leave `verified` events unchanged. v0.3 counts only verifications at or after `generated.at`, so some concepts drop a trust tier; that is the intended, safe reading.
- Optionally add `superseded_by` to deprecated concepts with a replacement, and date-only values where only a day is known (not for `generated.at` or `verified[].at`).
