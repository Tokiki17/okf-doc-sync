# Documentation maintenance standard

Read this to decide which documentation a confirmed change affects, where new content belongs, and how to avoid duplicated or dead content. Each rule cites its source; the [source list](#sources) records when it was checked.

## Contents

- When documentation must change
- Surface checklist
- Placement
- One source of truth
- Shareable content
- Agent instruction files
- Review and verification
- Sources

## When documentation must change

- Change documentation in the same change as the code it describes; reviewers treat missing doc updates as incomplete work. [Google, GitLab]
- Documentation is required when user-, operator-, or integrator-visible behavior, UI, API, configuration, installation, or a documented process changes, and when something is deprecated or removed. A purely internal change with an unchanged contract usually needs no user documentation, but still check agent instruction files, comments, and docstrings it invalidates. [GitLab, Google]

## Surface checklist

Walk the rows that match the confirmed change; skip the rest.

| Change | Surfaces to check |
| --- | --- |
| Feature or user-visible behavior | README overview, tutorials and how-to guides, reference, changelog or release notes |
| Interface, CLI, configuration, schema, environment variable | Reference docs, examples, docstrings and API comments, sample configs |
| Build, test, run, release commands; layout; conventions | Agent instruction files (`AGENTS.md`, host files), README getting started, `CONTRIBUTING` |
| Architecture or significant decision | A new decision record; the architecture overview; mark replaced decisions as superseded instead of rewriting them |
| Deprecation or removal | Deprecation notice with replacement and timeline; delete docs for removed features; changelog |
| Status claim (active, pending, retired) | Every place stating that status; keep the state labels distinct |
| Cross-repository dependency | The other side's docs when in scope, otherwise a recorded follow-up |
| Project knowledge | OKF concepts, coverage manifest, indexes, and update log |

## Placement

- Classify new content by reader need and keep the kinds separate: tutorials teach, how-to guides solve one task, reference describes the machinery, explanation gives the why. [Diátaxis]
- A README states what the directory holds, what to read first, who maintains it, and links to docs kept elsewhere. A docs directory covers getting started, testing, debugging, and releasing. [Google]
- Design docs and PRDs become records of decisions after implementation, not current guides. [Google] Record significant decisions with title, context, decision, status, and consequences; when a decision is reversed, keep the old record and mark it superseded with a link to its replacement. [ADR]
- Keep a changelog for people: newest version first, grouped by Added, Changed, Deprecated, Removed, Fixed, and Security, with an Unreleased section. [Keep a Changelog]

## One source of truth

- Keep one authoritative location per fact; link to it elsewhere. Duplicated text drifts. [Google]
- Prefer a small set of fresh, accurate docs over a large stale set. Delete inaccurate docs first; when unsure whether to migrate a doc, leave it behind. [Google]
- Do not hide unfinished or premature content in comments; remove it until it is ready. [GitLab]
- OKF concepts summarize and link authoritative docs; they do not restate them in full.

## Shareable content

- Before writing to a repository that is or may become public, keep machine-specific absolute paths, usernames, private project or employer names, and personal records out of it; use repository-relative paths and generic descriptions, and keep such records in a private location.
- Keep links resolvable from a fresh checkout. Links to sibling checkouts or local files break for every other reader; cite a public URL or plain text instead.

## Agent instruction files

- `AGENTS.md` is the cross-tool "README for agents": project overview, build and test commands, code style, testing, and security notes. The nearest file to the edited path wins, and explicit user prompts override it. Treat it as living documentation. [AGENTS.md]
- Include only what an agent cannot infer: commands it cannot guess, non-default style rules, test instructions, repository etiquette, project-specific architecture decisions, environment quirks, and non-obvious gotchas. Exclude what the code shows, standard conventions, detailed API docs (link instead), frequently changing data, long tutorials, and file-by-file descriptions. For each line, ask whether removing it would cause mistakes. [Claude Code best practices]
- Keep files short and free of contradictions; long or conflicting files reduce adherence. Move rarely needed procedures into skills or linked docs. [Claude Code memory, Claude Code best practices]
- Host loading rules that affect duplication:

| Host | Reads | Avoid duplication by |
| --- | --- | --- |
| Codex | `AGENTS.override.md` or `AGENTS.md` per directory from root to the working directory, within a combined size cap | Keeping shared rules in `AGENTS.md` and overrides near the specialized code [Codex AGENTS.md] |
| Claude Code | `CLAUDE.md`; reads `AGENTS.md` directly when no project `CLAUDE.md` exists | Omitting `CLAUDE.md` unless Claude-specific rules exist; otherwise starting it with an `@AGENTS.md` import and adding only Claude-specific lines. A sentence telling Claude to read `AGENTS.md` is weaker than the import [Claude Code memory] |
| Other `AGENTS.md` tools | `AGENTS.md`, sometimes after configuration | Pointing the tool at `AGENTS.md` instead of copying it [AGENTS.md] |

## Review and verification

- Authors remain responsible for the technical accuracy of AI-generated documentation; it still needs review. [GitLab]
- Verify with a check that produces a pass or fail: resolve changed links, run documented commands and examples where feasible, and run the bundle validator. Report the evidence, not only the conclusion. [Claude Code best practices]

## Sources

Checked 2026-10-09. Re-check a source before relying on a rule that may have changed.

- [Google] [Documentation best practices](https://google.github.io/styleguide/docguide/best_practices.html), Google style guides.
- [GitLab] [Documentation workflow](https://docs.gitlab.com/development/documentation/workflow/), GitLab development docs.
- [Diátaxis] [Diátaxis documentation framework](https://diataxis.fr/).
- [ADR] [Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions), Michael Nygard.
- [Keep a Changelog] [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
- [AGENTS.md] [AGENTS.md open format](https://agents.md/).
- [Codex AGENTS.md] [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), OpenAI Codex docs.
- [Claude Code memory] [How Claude remembers your project](https://code.claude.com/docs/en/memory), Claude Code docs.
- [Claude Code best practices] [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices).
