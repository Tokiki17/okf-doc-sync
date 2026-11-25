#!/usr/bin/env python3
"""Validate a project's living Markdown documentation.

Checks navigation from the project's real instruction entrypoint, local links
and heading anchors, backtick code paths, optional machine-specific home paths,
and Agent Skill metadata. Requires only the Python 3.10+ standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit


ENTRY_NAMES = ("AGENTS.md", "CLAUDE.md")
FALLBACK_ENTRY = "README.md"
NAVIGATION_NAMES = {"AGENTS.md", "CLAUDE.md", "README.md", "index.md"}
WALK_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}
MAX_TEXT_BYTES = 2 * 1024 * 1024
# Agent Skills specification and Anthropic authoring limits shared by all hosts.
MAX_DESCRIPTION_CHARS = 1024
MAX_SKILL_LINES = 500
SHORT_DESCRIPTION_RANGE = (25, 64)
# Assembled so this file does not match its own pattern.
HOME_PATH_PATTERN = re.compile(
    r"(?:/" + r"Users/|/" + r"home/)[A-Za-z0-9._-]+"
    r"|[A-Za-z]:(?:\\|/)+" + r"Users(?:\\|/)+[A-Za-z0-9._-]+"
)
LIST_MARKER_RE = re.compile(r"(?:[-+*]|\d{1,9}[.)])(?:[ \t]+|$)")
ATX_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
SETEXT_UNDERLINE_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
REFERENCE_DEFINITION_RE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$")
HTML_ANCHOR_RE = re.compile(r"<a\s[^>]*\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
IMPORT_RE = re.compile(r"(?:(?<=\s)|^)@([^\s`'\"()<>\[\]{}]+)", re.MULTILINE)
CODE_PATH_RE = re.compile(r"(?:\.{1,2}/)*[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)*/?")
LOCATION_SUFFIX_RE = re.compile(r"(?::\d+(?:[:-]\d+)?|#L\d+(?:-L?\d+)?)$")


# ---------------------------------------------------------------------------
# Results


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


# ---------------------------------------------------------------------------
# Markdown masking


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _leading_columns(line: str) -> int:
    columns = 0
    for char in line:
        if char == " ":
            columns += 1
        elif char == "\t":
            columns += 4 - (columns % 4)
        else:
            break
    return columns


def _blank_line(content: str) -> str:
    return " " * len(content)


def mask_blocks(text: str) -> str:
    """Blank frontmatter, fenced and indented code blocks, and HTML comments.

    Inline code is kept so heading anchors and backtick paths can be read.
    Offsets and line breaks are preserved.
    """
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    if lines and lines[0].rstrip("\r\n") == "---":
        for end in range(1, len(lines)):
            if lines[end].rstrip("\r\n") in {"---", "..."}:
                for position in range(end + 1):
                    content = lines[position].rstrip("\r\n")
                    output.append(_blank_line(content) + lines[position][len(content) :])
                index = end + 1
                break

    fence_char: str | None = None
    fence_length = 0
    in_comment = False
    in_indented_code = False
    previous_paragraph = False
    previous_blank = True
    list_indents: list[int] = []
    for line in lines[index:]:
        content = line.rstrip("\r\n")
        newline = line[len(content) :]
        if not content.strip():
            output.append(_blank_line(content) + newline)
            previous_blank = True
            previous_paragraph = False
            continue
        columns = _leading_columns(content)
        container = max((indent for indent in list_indents if indent <= columns), default=0)
        relative = columns - container
        stripped = content.lstrip(" \t")

        if fence_char is not None:
            closing = re.match(r"(`{3,}|~{3,})[ \t]*$", stripped)
            output.append(_blank_line(content) + newline)
            if closing and closing.group(1)[0] == fence_char and len(closing.group(1)) >= fence_length:
                fence_char = None
            previous_blank = False
            previous_paragraph = False
            continue

        if in_comment:
            masked, in_comment = _mask_comments(content, True)
            output.append(masked + newline)
            previous_blank = False
            previous_paragraph = False
            continue

        if relative >= 4 and not previous_paragraph and (previous_blank or in_indented_code):
            output.append(_blank_line(content) + newline)
            in_indented_code = True
            previous_blank = False
            continue
        in_indented_code = False

        fence = re.match(r"(`{3,}|~{3,})(.*)$", stripped) if relative <= 3 else None
        if fence and not (fence.group(1)[0] == "`" and "`" in fence.group(2)):
            fence_char = fence.group(1)[0]
            fence_length = len(fence.group(1))
            output.append(_blank_line(content) + newline)
            previous_blank = False
            previous_paragraph = False
            continue

        marker = LIST_MARKER_RE.match(stripped) if relative <= 3 else None
        if marker:
            list_indents = [indent for indent in list_indents if indent <= columns]
            list_indents.append(columns + max(marker.end(), 2))
        elif columns == 0 and previous_blank:
            list_indents.clear()
        elif previous_blank:
            list_indents = [indent for indent in list_indents if indent <= columns]

        masked, in_comment = _mask_comments(content, False)
        output.append(masked + newline)
        previous_paragraph = not ATX_HEADING_RE.match(content) and not SETEXT_UNDERLINE_RE.match(content)
        previous_blank = False
    return "".join(output)


def _mask_comments(content: str, in_comment: bool) -> tuple[str, bool]:
    chars = list(content)
    index = 0
    while index < len(content):
        if not in_comment and content.startswith("<!--", index):
            in_comment = True
        if in_comment:
            if content.startswith("-->", index):
                for position in range(index, index + 3):
                    chars[position] = " "
                index += 3
                in_comment = False
                continue
            chars[index] = " "
        index += 1
    return "".join(chars), in_comment


def _paragraph_segments(text: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of runs of non-blank lines."""
    segments: list[tuple[int, int]] = []
    offset = 0
    start: int | None = None
    for line in text.splitlines(keepends=True):
        if line.strip():
            if start is None:
                start = offset
        elif start is not None:
            segments.append((start, offset))
            start = None
        offset += len(line)
    if start is not None:
        segments.append((start, offset))
    return segments


def iter_code_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, content) for inline code spans; spans may cross lines in a paragraph."""
    spans: list[tuple[int, int, str]] = []
    for seg_start, seg_end in _paragraph_segments(text):
        index = seg_start
        while index < seg_end:
            if text[index] != "`" or _is_escaped(text, index):
                index += 1
                continue
            run_end = index
            while run_end < seg_end and text[run_end] == "`":
                run_end += 1
            run = run_end - index
            cursor = run_end
            closing = -1
            while cursor < seg_end:
                if text[cursor] != "`":
                    cursor += 1
                    continue
                other_end = cursor
                while other_end < seg_end and text[other_end] == "`":
                    other_end += 1
                if other_end - cursor == run:
                    closing = cursor
                    break
                cursor = other_end
            if closing < 0:
                index = run_end
                continue
            content = re.sub(r"\r?\n", " ", text[run_end:closing])
            if len(content) >= 2 and content.startswith(" ") and content.endswith(" ") and content.strip():
                content = content[1:-1]
            spans.append((index, closing + run, content))
            index = closing + run
    return spans


def mask_all_code(text: str) -> str:
    """Blank block-level code plus inline code spans, including spans across lines."""
    masked = mask_blocks(text)
    chars = list(masked)
    for start, end, _ in iter_code_spans(masked):
        for position in range(start, end):
            if chars[position] not in "\r\n":
                chars[position] = " "
    return "".join(chars)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# ---------------------------------------------------------------------------
# Markdown links


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).casefold()


def _parse_destination(text: str, start: int) -> tuple[str, int] | None:
    index = start
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    if index >= len(text):
        return None
    if text[index] == "<":
        end = index + 1
        while end < len(text):
            if text[end] == ">" and not _is_escaped(text, end):
                return text[index + 1 : end], end + 1
            if text[end] in "\r\n":
                return None
            end += 1
        return None
    destination: list[str] = []
    depth = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text) and not text[index + 1].isalnum():
            destination.append(text[index + 1])
            index += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        elif char.isspace():
            break
        destination.append(char)
        index += 1
    if depth or not destination:
        return None
    return "".join(destination), index


def _skip_title(text: str, index: int) -> int | None:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    if index >= len(text) or text[index] == ")":
        return index
    opener = text[index]
    if opener not in "\"'(":
        return None
    closer = ")" if opener == "(" else opener
    index += 1
    while index < len(text):
        if text[index] == closer and not _is_escaped(text, index):
            index += 1
            while index < len(text) and text[index] in " \t\r\n":
                index += 1
            return index
        index += 1
    return None


def _closing_bracket(text: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening + 1, len(text)):
        if _is_escaped(text, index):
            continue
        if text[index] == "[":
            depth += 1
        elif text[index] == "]":
            if depth == 0:
                return index
            depth -= 1
        elif text[index] == "\n" and index + 1 < len(text) and text[index + 1] == "\n":
            return None
    return None


def extract_links(text: str) -> list[tuple[str, int]]:
    """Return (destination, line) for inline and reference links, excluding images and code."""
    source = mask_all_code(text)
    # Every reference definition is checked, so reference-style uses need no second pass.
    links: list[tuple[str, int]] = []
    seen_labels: set[str] = set()
    chars = list(source)
    offset = 0
    for number, line in enumerate(source.splitlines(keepends=True), start=1):
        content = line.rstrip("\r\n")
        match = REFERENCE_DEFINITION_RE.match(content)
        if match and not match.group(1).startswith("^"):
            parsed = _parse_destination(match.group(2), 0)
            if parsed is not None:
                label = _normalize_label(match.group(1))
                if label not in seen_labels:
                    seen_labels.add(label)
                    links.append((parsed[0], number))
                for position in range(offset, offset + len(content)):
                    chars[position] = " "
        offset += len(line)
    stripped = "".join(chars)

    index = 0
    while index < len(stripped):
        if stripped[index] != "[" or _is_escaped(stripped, index):
            index += 1
            continue
        closing = _closing_bracket(stripped, index)
        if closing is None:
            index += 1
            continue
        is_image = index > 0 and stripped[index - 1] == "!" and not _is_escaped(stripped, index - 1)
        after = closing + 1
        if after < len(stripped) and stripped[after] == "(":
            parsed = _parse_destination(stripped, after + 1)
            if parsed is not None:
                target, end = parsed
                title_end = _skip_title(stripped, end)
                if title_end is not None and title_end < len(stripped) and stripped[title_end] == ")":
                    if not is_image:
                        links.append((target, _line_of(stripped, index)))
                    index = title_end + 1
                    continue
        index = closing + 1
    return links


# ---------------------------------------------------------------------------
# Headings and anchors


def _heading_text(raw: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", raw)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def github_slug(raw: str) -> str:
    """Approximate GitHub's heading anchor algorithm (github-slugger)."""
    text = _heading_text(raw).strip().lower()
    output: list[str] = []
    for char in text:
        if char == " ":
            output.append("-")
        elif char in "-_":
            output.append(char)
        elif unicodedata.category(char)[0] in {"L", "N", "M"}:
            output.append(char)
    return "".join(output)


def heading_anchors(text: str) -> set[str]:
    masked = mask_blocks(text)
    lines = masked.splitlines()
    anchors: set[str] = set()
    counts: dict[str, int] = {}

    def add(raw: str) -> None:
        slug = github_slug(raw)
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")

    previous = ""
    for line in lines:
        atx = ATX_HEADING_RE.match(line)
        setext = SETEXT_UNDERLINE_RE.match(line)
        if atx:
            body = re.sub(r"[ \t]+#+[ \t]*$", "", atx.group(2) or "")
            body = "" if re.fullmatch(r"#+", body.strip()) else body
            add(body)
            previous = ""
            continue
        if (
            setext
            and previous.strip()
            and not ATX_HEADING_RE.match(previous)
            and not LIST_MARKER_RE.match(previous.lstrip())
            and _leading_columns(previous) < 4
        ):
            add(previous.strip())
            previous = ""
            continue
        previous = line
    for match in HTML_ANCHOR_RE.finditer(mask_all_code(text)):
        anchors.add(match.group(1))
    return anchors


# ---------------------------------------------------------------------------
# Paths


def _exact_case_exists(root: Path, parts: tuple[str, ...]) -> bool:
    current = root
    for part in parts:
        try:
            names = os.listdir(current)
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


@dataclass
class ResolvedPath:
    path: Path
    problem: str | None = None


def resolve_local(root: Path, base_dir: Path, decoded: str) -> ResolvedPath:
    """Resolve a local path under root with lexical, real-path, and exact-case checks."""
    root = root.absolute()
    if decoded.startswith("/"):
        joined = root / decoded.lstrip("/")
    else:
        joined = base_dir / decoded
    lexical = Path(os.path.normpath(joined))
    relative = os.path.relpath(lexical, root)
    if relative == ".." or relative.startswith(".." + os.sep) or os.path.isabs(relative):
        return ResolvedPath(lexical, "escapes the project root")
    parts = () if relative == "." else tuple(Path(relative).parts)
    if not _exact_case_exists(root, parts):
        if lexical.exists():
            return ResolvedPath(lexical, "differs in letter case from the file on disk")
        return ResolvedPath(lexical, "does not exist")
    try:
        real = lexical.resolve(strict=True)
    except OSError:
        return ResolvedPath(lexical, "does not exist")
    if not real.is_relative_to(root.resolve()):
        return ResolvedPath(lexical, "resolves outside the project root")
    return ResolvedPath(lexical)


def _top_level_dirs(root: Path) -> set[str]:
    try:
        return {
            name
            for name in os.listdir(root)
            if name not in WALK_IGNORED_DIRS and (root / name).is_dir()
        }
    except OSError:
        return set()


def code_path_candidate(content: str, top_dirs: set[str]) -> tuple[str, str] | None:
    """Classify backtick text as ('root'|'doc', path) when it names a project path."""
    value = LOCATION_SUFFIX_RE.sub("", content.strip())
    if not value or not CODE_PATH_RE.fullmatch(value):
        return None
    named = [segment for segment in value.split("/") if segment not in {"", ".", ".."}]
    if not named or not all(re.search(r"[A-Za-z0-9]", segment) for segment in named):
        return None  # Placeholders such as `./...` name no file.
    if value.startswith("./") or value.startswith("../"):
        return "doc", value
    first, slash, _ = value.partition("/")
    if slash and first in top_dirs:
        return "root", value
    return None


# ---------------------------------------------------------------------------
# File enumeration


def list_project_files(root: Path) -> list[Path]:
    """List files tracked or not ignored by git; fall back to a filtered walk."""
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError:
        completed = None
    if completed is not None and completed.returncode == 0:
        files = []
        for entry in completed.stdout.decode("utf-8", "surrogateescape").split("\0"):
            if entry:
                path = root / entry
                if path.is_file():
                    files.append(path)
        return sorted(set(files))
    files = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in WALK_IGNORED_DIRS)
        for name in filenames:
            files.append(Path(directory) / name)
    return sorted(files)


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------------------
# Project validation


@dataclass
class _Doc:
    path: Path
    relative: str
    text: str
    historical: bool
    _anchors: set[str] | None = None

    @property
    def anchors(self) -> set[str]:
        if self._anchors is None:
            self._anchors = heading_anchors(self.text)
        return self._anchors

    @property
    def is_navigation(self) -> bool:
        return self.path.name in NAVIGATION_NAMES


def _is_under(relative: str, directories: list[str]) -> bool:
    return any(relative == directory or relative.startswith(directory + "/") for directory in directories)


def _imports(text: str) -> list[tuple[str, int]]:
    masked = mask_all_code(text)
    results = []
    for match in IMPORT_RE.finditer(masked):
        value = match.group(1).rstrip(".,;:!?")
        if "/" in value or re.search(r"\.[A-Za-z0-9]+$", value):
            results.append((value, _line_of(masked, match.start())))
    return results


def validate_project(
    root: Path,
    *,
    strict: bool = False,
    historical_dirs: list[str] | tuple[str, ...] = (),
    check_private_paths: bool = False,
) -> Report:
    report = Report()
    root = root.absolute()
    historical = [directory.strip("/").replace("\\", "/") for directory in historical_dirs]
    files = list_project_files(root)
    docs: dict[Path, _Doc] = {}
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        text = _read_text(path)
        if text is None:
            continue
        relative = path.relative_to(root).as_posix()
        docs[path] = _Doc(path, relative, text, _is_under(relative, historical))

    top_dirs = _top_level_dirs(root)
    edges: dict[Path, set[Path]] = {}
    for doc in docs.values():
        edges[doc.path] = _check_document(root, doc, docs, top_dirs, report)

    _check_reachability(root, docs, edges, strict, historical, report)
    if check_private_paths:
        _check_private_paths(root, files, report)
    return report


def _has_anchor(anchors: set[str], fragment: str) -> bool:
    decoded = unquote(fragment)
    return decoded in anchors or decoded.lower() in anchors


def _md_target(path: Path) -> Path | None:
    if path.is_dir():
        for name in ("index.md", "README.md"):
            candidate = path / name
            if candidate.is_file():
                return candidate
        return None
    return path if path.suffix.lower() == ".md" else None


def _check_document(
    root: Path,
    doc: _Doc,
    docs: dict[Path, _Doc],
    top_dirs: set[str],
    report: Report,
) -> set[Path]:
    targets: set[Path] = set()
    base_dir = doc.path.parent
    for target, line in extract_links(doc.text):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith("//"):
            continue
        location = f"{doc.relative}:{line}"
        if not parsed.path:
            if parsed.fragment and not doc.historical and not _has_anchor(doc.anchors, parsed.fragment):
                report.error(f"{location}: missing heading anchor '#{parsed.fragment}'")
            continue
        resolved = resolve_local(root, base_dir, unquote(parsed.path))
        if resolved.problem:
            if not doc.historical:
                report.error(f"{location}: broken link '{target}' ({resolved.problem})")
            continue
        markdown = _md_target(resolved.path)
        if markdown is not None:
            targets.add(markdown.absolute())
        if parsed.fragment and not doc.historical and resolved.path.suffix.lower() == ".md":
            linked = docs.get(resolved.path)
            anchors = linked.anchors if linked else heading_anchors(_read_text(resolved.path) or "")
            if not _has_anchor(anchors, parsed.fragment):
                report.error(f"{location}: missing heading anchor '{target}'")

    if doc.is_navigation:
        for value, line in _imports(doc.text):
            if value.startswith("~") or os.path.isabs(value):
                continue
            resolved = resolve_local(root, base_dir, value)
            if resolved.problem:
                # Only CLAUDE.md evaluates @imports; elsewhere '@name/pkg' is ordinary prose.
                if doc.path.name == "CLAUDE.md" and not doc.historical:
                    report.error(f"{doc.relative}:{line}: broken import '@{value}' ({resolved.problem})")
            elif resolved.path.suffix.lower() == ".md":
                targets.add(resolved.path.absolute())

    masked = mask_blocks(doc.text)
    for start, _, content in iter_code_spans(masked):
        line = _line_of(masked, start)
        candidate = code_path_candidate(content, top_dirs)
        if candidate is not None:
            kind, value = candidate
            base = root if kind == "root" else base_dir
            resolved = resolve_local(root, base, LOCATION_SUFFIX_RE.sub("", value))
            if resolved.problem:
                if not doc.historical:
                    report.error(f"{doc.relative}:{line}: code path '{content}' {resolved.problem}")
                continue
            if doc.is_navigation:
                markdown = _md_target(resolved.path)
                if markdown is not None:
                    targets.add(markdown.absolute())
        elif doc.is_navigation and re.fullmatch(r"[A-Za-z0-9_.-]+\.md", content.strip()):
            # A bare document name in an entrypoint or index navigates only when it exists.
            for base in (base_dir, root):
                resolved = resolve_local(root, base, content.strip())
                if not resolved.problem:
                    targets.add(resolved.path.absolute())
                    break
    return targets


def _check_reachability(
    root: Path,
    docs: dict[Path, _Doc],
    edges: dict[Path, set[Path]],
    strict: bool,
    historical: list[str],
    report: Report,
) -> None:
    entries = [root / name for name in ENTRY_NAMES if (root / name) in docs]
    if not entries and (root / FALLBACK_ENTRY) in docs:
        entries = [root / FALLBACK_ENTRY]
    claude, agents = root / "CLAUDE.md", root / "AGENTS.md"
    if claude in docs and agents in docs:
        imported = {value for value, _ in _imports(docs[claude].text)}
        if not imported & {"AGENTS.md", "./AGENTS.md"}:
            report.warn("CLAUDE.md: AGENTS.md also exists but CLAUDE.md does not import it with '@AGENTS.md'")

    docs_dir = root / "docs"
    candidates = [
        doc
        for doc in docs.values()
        if docs_dir in doc.path.parents and not doc.historical
    ]
    if not entries:
        if candidates:
            message = "no instruction entrypoint (AGENTS.md, CLAUDE.md, or README.md) reaches docs/"
            (report.error if strict else report.warn)(message)
        return

    reached: set[Path] = set()
    queue = list(entries)
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        doc = docs.get(current)
        if doc is None:
            continue
        for target in edges.get(current, set()):
            if target not in reached and target in docs:
                queue.append(target)

    entry_names = ", ".join(entry.name for entry in entries)
    for doc in sorted(candidates, key=lambda item: item.relative):
        if doc.path not in reached:
            message = f"{doc.relative}: not reachable from {entry_names}"
            (report.error if strict else report.warn)(message)


def _check_private_paths(root: Path, files: list[Path], report: Report) -> None:
    for path in files:
        text = _read_text(path)
        if text is None:
            continue
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            if HOME_PATH_PATTERN.search(line):
                report.error(f"{relative}:{number}: machine-specific home path")


# ---------------------------------------------------------------------------
# Minimal YAML subset for skill metadata


class MetadataError(ValueError):
    """Invalid metadata that names the offending field."""

    def __init__(self, field_name: str | None, message: str) -> None:
        self.field = field_name
        super().__init__(f"field '{field_name}': {message}" if field_name else message)


def _strip_comment(value: str) -> str:
    match = re.search(r"(?:^|[ \t])#", value)
    return value[: match.start()].rstrip() if match else value.rstrip()


def _parse_scalar(raw: str, field_name: str, line: int) -> object:
    value = raw.strip()
    if value.startswith('"'):
        end = 1
        while end < len(value):
            if value[end] == "\\":
                end += 2
                continue
            if value[end] == '"':
                break
            end += 1
        if end >= len(value):
            raise MetadataError(field_name, f"line {line}: unterminated double-quoted string")
        if _strip_comment(value[end + 1 :]):
            raise MetadataError(field_name, f"line {line}: unexpected text after quoted string")
        try:
            return json.loads(value[: end + 1])
        except json.JSONDecodeError as exc:
            raise MetadataError(field_name, f"line {line}: invalid escape in quoted string ({exc.msg})") from exc
    if value.startswith("'"):
        end = 1
        while end < len(value):
            if value[end] == "'":
                if end + 1 < len(value) and value[end + 1] == "'":
                    end += 2
                    continue
                break
            end += 1
        if end >= len(value):
            raise MetadataError(field_name, f"line {line}: unterminated single-quoted string")
        if _strip_comment(value[end + 1 :]):
            raise MetadataError(field_name, f"line {line}: unexpected text after quoted string")
        return value[1:end].replace("''", "'")
    if value[:1] in {"[", "{"}:
        raise MetadataError(field_name, f"line {line}: flow collections are not supported; use a plain or quoted string")
    if value[:1] in {"|", ">"}:
        raise MetadataError(field_name, f"line {line}: block scalars are not supported; write the value on one line")
    if value[:1] in {"&", "*", "!", "%", "@", "`"}:
        raise MetadataError(field_name, f"line {line}: value starts with reserved YAML indicator '{value[0]}'; quote it")
    value = _strip_comment(value)
    if re.search(r":(?:[ \t]|$)", value):
        raise MetadataError(field_name, f"line {line}: plain value contains ': '; quote the value")
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~", ""}:
        return None
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    return value


def parse_simple_yaml(text: str) -> dict:
    """Parse nested block mappings of scalars, the subset skill metadata needs."""
    root: dict = {}
    stack: list[tuple[int, dict, str]] = [(0, root, "")]
    pending: tuple[dict, str, str, int] | None = None
    last_field: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        leading = raw[: len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in leading:
            raise MetadataError(last_field, f"line {number}: tabs are not allowed in indentation")
        indent = len(leading)
        content = raw.strip()
        if pending is not None:
            mapping, key, field_name, parent_indent = pending
            pending = None
            if indent > parent_indent:
                child: dict = {}
                mapping[key] = child
                stack.append((indent, child, field_name))
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        if indent != stack[-1][0]:
            hint = f" after field '{last_field}'" if last_field else ""
            raise MetadataError(
                last_field,
                f"line {number}: unexpected indentation{hint}; multi-line values are not supported",
            )
        _, mapping, prefix = stack[-1]
        if content.startswith("- ") or content == "-":
            raise MetadataError(prefix or last_field, f"line {number}: sequences are not supported")
        match = re.match(r"^([A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*:(?:[ \t]+(.*))?$", content)
        if not match:
            raise MetadataError(prefix or last_field, f"line {number}: expected 'key: value'")
        key, value = match.group(1), match.group(2)
        field_name = f"{prefix}.{key}" if prefix else key
        if key in mapping:
            raise MetadataError(field_name, f"line {number}: duplicate key")
        last_field = field_name
        if value is None or not _strip_comment(value):
            mapping[key] = None
            pending = (mapping, key, field_name, indent)
        else:
            mapping[key] = _parse_scalar(value, field_name, number)
    return root


def split_frontmatter(text: str) -> tuple[str | None, str]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        return None, text
    return match.group(1), text[match.end() :]


# ---------------------------------------------------------------------------
# Skill tree validation


def validate_skill_tree(skill_root: Path, expected_name: str | None = None) -> list[str]:
    """Validate a portable Agent Skill directory; every metadata error names its field."""
    skill_root = Path(skill_root)
    name = expected_name or skill_root.name
    errors: list[str] = []
    skill_path = skill_root / "SKILL.md"
    if not skill_path.is_file():
        return ["SKILL.md is missing"]
    try:
        text = skill_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"SKILL.md is not valid UTF-8: {exc}"]

    header, _ = split_frontmatter(text)
    if header is None:
        errors.append("SKILL.md must start with '---' delimited YAML frontmatter")
    else:
        try:
            metadata = parse_simple_yaml(header)
        except MetadataError as exc:
            errors.append(f"SKILL.md frontmatter {exc}")
        else:
            for key in sorted(set(metadata) - {"name", "description"}):
                errors.append(
                    f"SKILL.md frontmatter field '{key}': not allowed; portable skills use only name and description"
                )
            for key in ("name", "description"):
                if key not in metadata:
                    errors.append(f"SKILL.md frontmatter field '{key}': missing")
            if "name" in metadata and metadata["name"] != name:
                errors.append(f"SKILL.md frontmatter field 'name': must be '{name}' to match the skill directory")
            if "description" in metadata:
                description = metadata["description"]
                if not isinstance(description, str) or not description.strip():
                    errors.append("SKILL.md frontmatter field 'description': must be a non-empty string")
                elif len(description) > MAX_DESCRIPTION_CHARS:
                    errors.append(
                        f"SKILL.md frontmatter field 'description': exceeds {MAX_DESCRIPTION_CHARS} characters"
                    )
                elif "<" in description or ">" in description:
                    errors.append("SKILL.md frontmatter field 'description': must not contain angle brackets")
    if len(text.splitlines()) >= MAX_SKILL_LINES:
        errors.append(f"SKILL.md must stay under {MAX_SKILL_LINES} lines")
    if "TODO" in text:
        errors.append("SKILL.md contains unresolved TODO text")
    for target, line in extract_links(text):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        resolved = resolve_local(skill_root, skill_root, unquote(parsed.path))
        if resolved.problem:
            errors.append(f"SKILL.md:{line}: broken link '{target}' ({resolved.problem})")

    metadata_path = skill_root / "agents" / "openai.yaml"
    if metadata_path.is_file():
        errors.extend(_agent_metadata_errors(metadata_path, name))
    return errors


def _agent_metadata_errors(path: Path, name: str) -> list[str]:
    label = "agents/openai.yaml"
    try:
        metadata = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        return [f"{label} is not valid UTF-8: {exc}"]
    except MetadataError as exc:
        return [f"{label} {exc}"]
    errors: list[str] = []
    interface = metadata.get("interface")
    if not isinstance(interface, dict):
        errors.append(f"{label} field 'interface': must be a mapping")
    else:
        for key in ("display_name", "short_description", "default_prompt"):
            value = interface.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label} field 'interface.{key}': must be a non-empty string")
        short_description = interface.get("short_description")
        low, high = SHORT_DESCRIPTION_RANGE
        if isinstance(short_description, str) and short_description.strip():
            if not low <= len(short_description.strip()) <= high:
                errors.append(f"{label} field 'interface.short_description': must contain {low}-{high} characters")
        default_prompt = interface.get("default_prompt")
        if isinstance(default_prompt, str) and default_prompt.strip() and f"${name}" not in default_prompt:
            errors.append(f"{label} field 'interface.default_prompt': must invoke ${name}")
    policy = metadata.get("policy")
    if not isinstance(policy, dict) or policy.get("allow_implicit_invocation") is not True:
        errors.append(f"{label} field 'policy.allow_implicit_invocation': must be true")
    return errors


# ---------------------------------------------------------------------------
# Command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd(), help="project root (default: cwd)")
    parser.add_argument("--strict", action="store_true", help="report unreachable docs/ files as errors")
    parser.add_argument(
        "--historical-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="project-relative directory of frozen records; skipped by link, path, and reachability checks",
    )
    parser.add_argument(
        "--check-private-paths",
        action="store_true",
        help="reject machine-specific home-directory paths in project files",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="also validate an Agent Skill directory's metadata",
    )
    args = parser.parse_args(argv)
    root = args.root.expanduser()
    if not root.is_dir():
        print(f"ERROR: project root is not a directory: {root}", file=sys.stderr)
        return 2
    report = validate_project(
        root,
        strict=args.strict,
        historical_dirs=args.historical_dir,
        check_private_paths=args.check_private_paths,
    )
    for skill in args.skill:
        for error in validate_skill_tree(skill.expanduser()):
            report.error(f"{skill}: {error}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if report.errors:
        return 1
    print(f"Documentation checks passed ({len(report.warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
