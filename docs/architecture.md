# Architecture

## Source and installation

`skills/doc-sync/` is the only editable source. `scripts/install.py` copies it into a host's skills directory (`--host <host>` or any `--target`) and verifies byte-for-byte parity. See [Host compatibility](host-compatibility.md) for supported `--host` presets and default targets.

```text
skills/doc-sync/  ->  scripts/install.py [--host HOST | --target DIR]  ->  <host>/skills/doc-sync/
   canonical                                                                installed mirror
```

- **Work root.** Hosts load every directory containing `SKILL.md` under a skills root, so staging and the rollback backup never live there. A standard `<base>/skills/doc-sync` target uses `<base>/.doc-sync-install/`. A shallow target, or one inside a repository (any ancestor holds `.git`), uses the user cache, `~/.cache/doc-sync-install/<hash>/` (`$XDG_CACHE_HOME` when set, `%LOCALAPPDATA%` on Windows), so no project tree gains install artifacts.
- **Replacement.** On one device the old target is renamed to the backup and the staged tree renamed into place. When the work root is on another device (`EXDEV`), the old target is first copied to the backup with symlinks preserved, and a marker is set before the new target is written. If anything fails after that marker, the partial target is removed, then the backup is restored if a target existed before, or the target is left absent.
- **Read-only modes.** `--check` and `--dry-run` write nothing, including bytecode for the loaded validator. `--check` fails on missing, extra, or content-divergent files.
- A divergent installation is replaced only with `--force`. Symlinked targets are refused. A symlink inside an existing target is reported as a difference rather than an error, so `--force` can move it into the backup unchanged and install a clean tree; the installed tree itself must contain no symlinks. Target paths are normalized with `os.path.abspath`, which folds `..` without following a symlinked final component.

## Documentation model

The skill keeps one layer of authoritative living docs; there is no parallel knowledge bundle. Each fact has one home, and docs record what the code cannot show: reasons, constraints, traps, and status in five states (`active`, `fallback`, `pending verification`, `historical`, `retired`).

A project's instruction entrypoint carries read-time routes (which contract to read before which kind of change, and when reading can stop) and one conditional write-time rule. This repository's [AGENTS.md](../AGENTS.md) is the reference example. The [maintenance standard](../skills/doc-sync/references/doc-maintenance.md) holds the cited rules.

## Validation

`skills/doc-sync/scripts/validate_docs.py` is shipped with the skill and uses only the Python 3.10+ standard library.

- **Two masking layers.** Block masking blanks frontmatter, fenced code (up to three leading spaces), indented code blocks, and HTML comments, but keeps 4-space nested list items and inline code text. Heading anchors and backtick paths are read from this layer, so a heading such as ``## Using `foo()` `` keeps its code text in the anchor. Full masking also blanks inline code spans, including spans that cross lines within a paragraph, and is the only layer used to extract Markdown links. A leading `---` counts as frontmatter only when a later line is exactly `---`, the first enclosed line is not blank, and every enclosed non-blank, non-comment line is indented or looks like a YAML key or list item; a leading thematic break stays Markdown.
- **Reachability.** Traversal starts only at the real entrypoint: root `AGENTS.md` and `CLAUDE.md`, or `README.md` when neither exists. A `docs/index.md` that the entrypoint does not reach is not a start point. Every reached document follows its Markdown links. Reached entrypoint and index files (`AGENTS.md`, `CLAUDE.md`, `README.md`, any `index.md`) also follow `@path` imports and backtick paths naming existing Markdown files. Backtick paths in ordinary documents are checked for existence but never count as navigation. Unreached `docs/**/*.md` outside `--historical-dir` are warnings, or errors with `--strict`. A root `CLAUDE.md` beside `AGENTS.md` without an `@AGENTS.md` import is a warning.
- **Links and anchors.** A line such as `[label]: target` is a reference definition only when the target is followed by nothing or a single-line title (the target may also sit alone on the next line); text such as `[INFO]: server started` is prose. A blank line, LF or CRLF, ends a link's bracket text. A leading `/` resolves from the project root; other links resolve from the document's directory. Each target must stay inside the root both lexically and after `resolve()`, match letter case segment by segment through `os.listdir`, and, for a `#fragment`, name a real heading (GitHub slug rules) or HTML anchor.
- **Backtick paths.** In non-historical docs, `<top_dir>/...` (first segment is a real top-level directory) resolves from the project root and `./...` or `../...` from the document's directory. Text with spaces, placeholders, or globs is ignored.
- **Private paths.** `--check-private-paths` enumerates files with `git ls-files -z --cached --others --exclude-standard` (falling back to a filtered walk) and rejects POSIX and Windows home-directory paths.
- **Skill metadata.** `validate_skill_tree()` checks `SKILL.md` frontmatter, size limits, local links, and optional `agents/openai.yaml`. Its minimal YAML reader accepts only block mappings of scalars, and every error names the offending field. `install.py` and `validate_repo.py` both call it.

`scripts/validate_repo.py` runs this repository's gate: required files, no `CLAUDE.md`, skill metadata, strict documentation checks with private-path rejection, a static check that every Python file parses as Python 3.10 (`ast.parse(..., feature_version=(3, 10))`) and imports only modules in `sys.stdlib_module_names`, and whitespace checks on the worktree and staged diffs. `tests/` covers the validator, installer recovery and isolation, and the repository gate.

## Evidence boundaries

The checks read local files only. A pass establishes structure and navigation, not that a documented fact is true, current, reviewed, or deployed. They do not measure whether a model finds hidden constraints or skips unneeded reading; that needs forward tests (see [Maintenance](maintenance.md#forward-testing)).
