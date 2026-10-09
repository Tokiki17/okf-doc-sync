# OKF v0.1 compatibility profile

Use this reference for existing v0.1 bundles. New bundles use [v0.2](okf-v0.2.md); preserve explicit project pins until a coordinated migration is in scope.

## Authority and verification

- Pinned normative source: [Open Knowledge Format v0.1 specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/ee67a5ca27044ebe7c38385f5b6cffc2305a9c1a/okf/SPEC.md).
- Current upstream: [GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format). The old repository's `okf/` is frozen.
- Compatibility policy checked: 2026-09-05. This is supported legacy production, not the latest upstream format.

Use the pinned specification for v0.1 semantics; a moving `main` link now describes v0.2 and cannot be cited as v0.1 authority.

## Producer conformance checklist

1. A bundle is a directory tree of UTF-8 Markdown files.
2. `index.md` and `log.md` are reserved at every hierarchy level and are not concept documents.
3. Every other `.md` file starts with parseable YAML frontmatter containing a non-empty string `type`.
4. `title`, `description`, `resource`, `tags`, and `timestamp` are optional. Preserve unknown extension fields.
5. `index.md` lists children for progressive disclosure. A root index may use frontmatter only to declare `okf_version: "0.1"`.
6. `log.md` groups entries under ISO `YYYY-MM-DD` headings, newest first.
7. Markdown bodies and links express relationships. Use citations when claims depend on external sources.
8. Keep generic OKF consumption permissive. For a durable project maintained by doc-sync, run the stricter DocSync producer profile described below.

## DocSync producer profile

Run `validate_okf.py <bundle> --doc-sync-profile` as the deterministic completion gate. Root `okf_version: "0.1"` selects this compatibility profile; `"0.2"` selects the v0.2 profile. The older `--require-doc-sync-spine` flag remains a compatibility alias.

The profile adds project-level producer requirements beyond upstream conformance:

- root `index.md` and `log.md`, with root `okf_version: "0.1"`;
- a concept whose normalized `type` is exactly `Coverage Manifest`;
- non-empty `title`, one-line `description`, and timezone-aware ISO 8601 `timestamp` on every concept;
- root-index navigation that reaches every concept, directly or through nested indexes;
- strict maintained links, including inline and reference-style Markdown links while ignoring code and images;
- a final, consecutively numbered `# Citations` section when external links or `resource` require provenance, with `resource` as citation `[1]`.

These checks prove structural completeness only. Source truth, description quality, coverage accuracy, and current/fallback/historical/pending/retired semantics still require evidence review.

## Consumer tolerance

Consumers must tolerate unknown types, unknown fields, missing optional metadata, missing indexes, and broken links. They should attempt best-effort consumption of an unfamiliar declared OKF version rather than refusing the bundle.

This is a consumption rule, not a reason for doc-sync to produce avoidable defects. The doc-sync completion gate may require maintained local links to resolve and may require the recommended navigation spine.

## Link-policy compatibility note

The v0.1 specification describes both bundle-root-absolute and relative Markdown links and recommends bundle-root-absolute links. A historical upstream implementation change emitted file-relative links so bundles render correctly on GitHub ([change #45](https://github.com/GoogleCloudPlatform/knowledge-catalog/commit/4c40ef103cd7)).

DocSync therefore:

- emits file-relative links for repository portability;
- accepts both specified link forms when reading or validating existing bundles;
- resolves a leading `/` relative to the bundle root rather than the repository root during OKF validation.
- rejects leading-slash paths that normalize outside the bundle root when strict link validation is enabled.
- permits file-relative links from `okf/` to authoritative repository living docs outside the bundle when those targets exist.

## Root index version exception

The index section says indexes contain no frontmatter, while the versioning section permits `okf_version: "0.1"` frontmatter in the bundle-root `index.md` as the only exception. Treat the versioning rule as the explicit exception and reject frontmatter in nested indexes.

## Project knowledge boundary

OKF concepts summarize and connect project knowledge. They do not automatically supersede `AGENTS.md`, `README*`, current specs, task boards, decision records, risk registers, or interface contracts. Each coverage manifest should make the source-of-truth relationship explicit.
