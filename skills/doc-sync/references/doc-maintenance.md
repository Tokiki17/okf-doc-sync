# Documentation maintenance standard

Read this to decide whether a confirmed change affects documentation, where the affected fact lives, and how to keep the project entrypoint useful. Rules marked with a source tag are distilled from the [sources](#sources); untagged rules are DocSync policy.

## Contents

- When documentation must change
- Surface checklist
- One source of truth
- Status states
- Placement
- Project entrypoint
- Agent instruction files
- Shareable content
- Review and verification
- Sources

## When documentation must change

- Change documentation in the same change as the code it describes; reviewers treat a missing doc update as incomplete work. [Google, GitLab]
- A change needs documentation when it alters behavior, a constraint, a command, a status, or a path that a doc or the entrypoint already describes, or when it creates a rule that later sessions must follow. Deprecations and removals count. [GitLab, Google]
- A change confined to one module's internals, with an unchanged contract, needs no documentation edit. Leave the docs untouched rather than adding a note that nothing changed.

## Surface checklist

Walk the rows that match the confirmed change; skip the rest.

| Change | Surfaces to check |
| --- | --- |
| User-visible behavior | README overview, tutorials and how-to guides, reference, changelog or release notes |
| Interface, CLI, configuration, schema, environment variable | Reference docs, examples, docstrings and API comments, sample configs |
| Build, test, run, release commands; layout; conventions | Agent instruction files, README getting started, `CONTRIBUTING` |
| Hidden constraint, design reason, or trap | Its single authoritative doc, and an entrypoint route if readers would otherwise miss it. Two frequent traps: parallel ID or enum spaces across files that are easy to confuse, and static configuration or data file conventions the code does not validate on load. Look for them when a change touches them or existing docs hint at them; routine tidying does not require reverse-engineering the whole codebase |
| Architecture or significant decision | A new decision record and the architecture overview; mark replaced decisions as superseded |
| Deprecation or removal | Notice with replacement and timeline; delete docs for removed features; changelog |
| Status claim | Every place stating that status, using the states below |
| Cross-repository dependency | The other side's docs when in scope, otherwise a recorded follow-up |

## One source of truth

- Keep one authoritative location per fact and link to it elsewhere. Duplicated text drifts. [Google]
- Prefer a small set of fresh, accurate docs over a large stale set. Delete inaccurate docs first; when unsure whether to migrate a doc, leave it behind. [Google]
- Do not hide unfinished or obsolete content in comments; remove it. [GitLab]
- Focus on what the code cannot show: reasons, constraints, external limits, traps, and status. Do not restate signatures, file listings, or behavior a reader sees by opening the code. [Claude Code best practices]

## Status states

Use exactly these labels when a doc states whether something is in force, and keep them distinct:

| State | Meaning |
| --- | --- |
| `active` | In force now; grounded in current code, configuration, runtime, or user confirmation |
| `fallback` | Present and usable, but not the path currently taken |
| `pending verification` | Implemented or claimed, not yet confirmed |
| `historical` | A dated record of past state; never rewritten into a current claim |
| `retired` | Removed; keep only where a reader needs to know it is gone |

A passing test or validator proves structure, not that a feature is `active`, deployed, or reviewed.

## Placement

- Classify new content by reader need and keep the kinds separate: tutorials teach, how-to guides solve one task, reference describes the machinery, explanation gives the why. [Diátaxis]
- A README states what the directory holds, what to read first, and links to docs kept elsewhere. [Google]
- Design docs become records of decisions after implementation, not current guides. [Google] Record significant decisions with title, context, decision, status, and consequences; when a decision is reversed, keep the old record and mark it superseded with a link to its replacement. [ADR]
- Keep a changelog for people: newest version first, grouped by Added, Changed, Deprecated, Removed, Fixed, and Security. [Keep a Changelog]

## Project entrypoint

The entrypoint is the instruction file a host loads first. Its job is routing, not content.

- **Reuse what exists.** Keep the project's current entrypoint structure and any existing rule equivalent to the write-time rule in `SKILL.md`. Do not reword an equivalent rule.
- **Route only hidden constraints.** A route names a kind of change, the contract to read before making it, and when reading can stop. Add a route only where a reader working from the code would otherwise break a constraint. Name the trap without copying mutable defaults, numbers, or tables from the target doc, which would drift and let readers skip opening the contract. [Google, Claude Code best practices]
- **Verify every route.** Before writing a route, open its target section and confirm it fully defines each concept the route names. When the code has look-alike concepts with different meanings or values, such as two separate ID spaces, never route the undefined one to a section that defines only the other; a reader who trusts the route will stop reading and copy the wrong value.
- **State the no-read boundary.** Say which changes need no doc reading, so readers do not pre-read the project for routine edits.
- **Size.** As a tidying reference, not a gate, an entrypoint that routes to more than about 10 documents or runs past about 120 lines usually mixes content into routing; move content into the routed docs.
- **Routine syncs.** Edit a route only when its target, trigger, or boundary changed, or a new hidden constraint appeared. A correct entrypoint needs no rewrite for each change.
- **Reachability.** Every maintained file under `docs/` should be reachable from the entrypoint through links, an index, `@path` imports, or backtick paths in an entrypoint or index. An index that the entrypoint never reaches does not count.
- **Frozen records.** The checker recognizes directories named `history`, `historical`, `archive`, `archived`, or `superpowers` regardless of case. For another directory, put `<!-- doc-sync: historical-dir custom/logs -->` in the root instruction entrypoint or pass `--historical-dir`. The plural form `historical-dirs` also accepts comma- or whitespace-separated project-relative directories and an optional equals sign. Place declarations outside code blocks and inline code spans.

## Agent instruction files

- `AGENTS.md` is the cross-tool "README for agents". The nearest file to the edited path wins, and explicit user prompts override it. Treat it as living documentation. [AGENTS.md]
- Include only what an agent cannot infer: commands it cannot guess, non-default style rules, test instructions, repository etiquette, architecture decisions, environment quirks, and gotchas. Exclude what the code shows, standard conventions, detailed API docs (link instead), frequently changing data, and file-by-file descriptions. For each line, ask whether removing it would cause mistakes. [Claude Code best practices]
- Keep files short and free of contradictions; long or conflicting files reduce adherence. Move rarely needed procedures into linked docs or skills. [Claude Code memory, Claude Code best practices]
- Host loading rules that affect duplication:

| Host | Reads | Avoid duplication by |
| --- | --- | --- |
| Codex | `AGENTS.override.md` or `AGENTS.md` per directory from root to the working directory, within a combined size cap | Keeping shared rules in `AGENTS.md` and overrides near the specialized code [Codex AGENTS.md] |
| Claude Code | `CLAUDE.md`; reads `AGENTS.md` directly when no project `CLAUDE.md` exists | Omitting `CLAUDE.md` unless Claude-specific rules exist; otherwise starting it with an `@AGENTS.md` import and adding only Claude-specific lines [Claude Code memory] |
| Other `AGENTS.md` tools | `AGENTS.md` (alongside tool-specific files such as `GEMINI.md` when present, or after configuration) | Keeping shared project rules in `AGENTS.md` instead of copying them into tool-specific files [AGENTS.md] |

## Shareable content

- Before writing to a repository that is or may become public, keep machine-specific absolute paths, usernames, private project or employer names, and personal records out of it; use repository-relative paths and generic descriptions.
- Keep links resolvable from a fresh checkout. For references outside a shareable repository, cite a public URL or use plain text. The checker supports sibling checkout links in a local workspace. Run it with `--check-private-paths` for shareable content.

## Review and verification

- Authors remain responsible for the technical accuracy of AI-generated documentation. [GitLab]
- Verify with checks that pass or fail: resolve changed links and anchors, run documented commands where feasible, and run the bundled checker. Report the evidence, not only the conclusion. [Claude Code best practices]
- Fix defects the change introduced or that lie in the authorized scope. Report pre-existing defects outside it with location and impact instead of widening the task or claiming a full pass.

## Sources

Checked 2026-11-25. Re-check a source before relying on a rule that may have changed.

- [Google] [Documentation best practices](https://google.github.io/styleguide/docguide/best_practices.html), Google style guides.
- [GitLab] [Documentation workflow](https://docs.gitlab.com/development/documentation/workflow/), GitLab development docs.
- [Diátaxis] [Diátaxis documentation framework](https://diataxis.fr/).
- [ADR] [Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions), Michael Nygard.
- [Keep a Changelog] [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
- [AGENTS.md] [AGENTS.md open format](https://agents.md/).
- [Codex AGENTS.md] [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), OpenAI Codex docs.
- [Claude Code memory] [How Claude remembers your project](https://code.claude.com/docs/en/memory), Claude Code docs.
- [Claude Code best practices] [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices).
