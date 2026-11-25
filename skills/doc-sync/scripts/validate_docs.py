#!/usr/bin/env python3
"""Validate a project's living Markdown documentation.

Checks navigation from the project's real instruction entrypoint, local links
and heading anchors, backtick code paths, optional machine-specific home paths,
and Agent Skill metadata. Requires only the Python 3.10+ standard library.
"""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import posixpath
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
ARTIFACT_AND_VENDOR_DIRS = {
    "build", "dist", "out", "output", "outputs", "target", "tmp", "temp",
    "artifacts", "coverage", "TestResults", "bin", "obj", "vendor", "third_party", "upstream", "templates",
}
HISTORICAL_DIR_NAMES = {"history", "historical", "archive", "archived", "superpowers"}
HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
HISTORICAL_DIR_RE = re.compile(r"\s*doc-sync:\s*historical-dirs?(?:\s*=\s*|\s+)(.*)", re.I | re.S)
PLACEHOLDER_SEGMENT_RE = re.compile(r"NNN(?:-.*)?|XXX|YYYY|\.\.\.")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[/\\]")
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
QUOTE_MARKER_RE = re.compile(r" {0,3}>[ \t]?")
ATX_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
SETEXT_UNDERLINE_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
REFERENCE_DEFINITION_RE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$")
HTML_ANCHOR_RE = re.compile(r"<a\s[^>]*\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
IMPORT_RE = re.compile(r"(?:(?<=\s)|^)@([^\s`'\"()<>\[\]{}]+)", re.MULTILINE)
CODE_PATH_RE = re.compile(r"(?:\.{1,2}/)*[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)*/?")
BLANK_LINE_RE = re.compile(r"[ \t]*\r?\n")
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


FRONTMATTER_LINE_RE = re.compile(r"[A-Za-z0-9_.\"'-]+[ \t]*:|-(?:[ \t]|$)")


def _frontmatter_end(lines: list[str]) -> int | None:
    """Return the closing line index of YAML frontmatter, or None.

    A leading ``---`` is frontmatter only when a later line is exactly ``---``,
    the block does not start with a blank line (a thematic break followed by a
    paragraph), and every non-blank, non-comment line is indented or looks like
    a top-level YAML key or list item. Otherwise the text stays Markdown.
    """
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for end in range(1, len(lines)):
        if lines[end].rstrip("\r\n") == "---":
            break
    else:
        return None
    body = [line.rstrip("\r\n") for line in lines[1:end]]
    if body and not body[0].strip():
        return None
    for content in body:
        stripped = content.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if content[:1] in {" ", "\t"} or FRONTMATTER_LINE_RE.match(content):
            continue
        return None
    return end


def mask_blocks(text: str, *, keep_comments: bool = False) -> str:
    """Blank frontmatter, fenced and indented code blocks, and optionally HTML comments.

    Inline code is kept so heading anchors and backtick paths can be read.
    Offsets and line breaks are preserved.
    """
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    end = _frontmatter_end(lines)
    if end is not None:
        for position in range(end + 1):
            content = lines[position].rstrip("\r\n")
            output.append(_blank_line(content) + lines[position][len(content) :])
        index = end + 1

    fence_char: str | None = None
    fence_length = 0
    fence_indent = 0
    quote_depth = 0
    in_comment = False
    previous_paragraph = False
    previous_blank = True
    list_indents: list[int] = []
    for line in lines[index:]:
        content = line.rstrip("\r\n")
        newline = line[len(content) :]
        block_content = content
        if keep_comments:
            depth = 0
            while (not (fence_char or in_comment) or depth < quote_depth) and (
                quote := QUOTE_MARKER_RE.match(block_content)
            ):
                depth += 1
                block_content = block_content[quote.end() :]
            if depth != quote_depth:
                quote_depth = depth
                fence_char = None
                in_comment = previous_paragraph = False
                previous_blank = True
                list_indents.clear()
        if not block_content.strip():
            output.append(_blank_line(content) + newline)
            previous_blank = True
            previous_paragraph = False
            continue
        columns = _leading_columns(block_content)
        container = max((indent for indent in list_indents if indent <= columns), default=0)
        relative = columns - container
        stripped = block_content.lstrip(" \t")

        if keep_comments and fence_char and columns < fence_indent:
            fence_char = None
        if fence_char is not None:
            closing = (
                re.match(r"(`{3,}|~{3,})[ \t]*$", stripped)
                if not keep_comments or columns - fence_indent <= 3 else None
            )
            output.append(_blank_line(content) + newline)
            if closing and closing.group(1)[0] == fence_char and len(closing.group(1)) >= fence_length:
                fence_char = None
            previous_blank = False
            previous_paragraph = False
            continue

        if in_comment:
            masked, in_comment = _mask_comments(content, True)
            output.append((content if keep_comments else masked) + newline)
            previous_blank = False
            previous_paragraph = False
            continue

        if relative >= 4 and not previous_paragraph:
            output.append(_blank_line(content) + newline)
            previous_blank = False
            continue

        marker = LIST_MARKER_RE.match(stripped) if relative <= 3 else None
        fence_source = stripped[marker.end() :] if keep_comments and marker else stripped
        fence = re.match(r"(`{3,}|~{3,})(.*)$", fence_source) if relative <= 3 else None
        if fence and not (fence.group(1)[0] == "`" and "`" in fence.group(2)):
            fence_char = fence.group(1)[0]
            fence_length = len(fence.group(1))
            fence_indent = columns + max(marker.end(), 2) if marker else container
            output.append(_blank_line(content) + newline)
            previous_blank = False
            previous_paragraph = False
            continue

        if marker:
            list_indents = [indent for indent in list_indents if indent <= columns]
            list_indents.append(columns + max(marker.end(), 2))
        elif columns == 0 and previous_blank:
            list_indents.clear()
        elif previous_blank:
            list_indents = [indent for indent in list_indents if indent <= columns]

        comment_source = content
        if keep_comments and "<!--" in content and "`" in content:
            comment_source = _mask_inline_code(content, skip_comments=True)
        masked, in_comment = _mask_comments(comment_source, False)
        output.append((content if keep_comments else masked) + newline)
        previous_paragraph = not ATX_HEADING_RE.match(block_content) and not SETEXT_UNDERLINE_RE.match(block_content)
        previous_blank = False
    return "".join(output)


def _mask_comments(content: str, in_comment: bool) -> tuple[str, bool]:
    chars = list(content)
    index = 0
    while index < len(content):
        if not in_comment and content.startswith("<!--", index) and not _is_escaped(content, index):
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


def iter_code_spans(text: str, *, skip_comments: bool = False) -> list[tuple[int, int, str]]:
    """Return (start, end, content) for inline code spans; spans may cross lines in a paragraph."""
    spans: list[tuple[int, int, str]] = []
    index = 0
    for seg_start, seg_end in _paragraph_segments(text):
        index = max(index, seg_start)
        while index < seg_end:
            if skip_comments and text.startswith("<!--", index) and not _is_escaped(text, index):
                comment = HTML_COMMENT_RE.match(text, index)
                if comment:
                    index = comment.end()
                    continue
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


def _mask_inline_code(text: str, *, skip_comments: bool = False) -> str:
    chars = list(text)
    for start, end, _ in iter_code_spans(text, skip_comments=skip_comments):
        for position in range(start, end):
            if chars[position] not in "\r\n":
                chars[position] = " "
    return "".join(chars)


def mask_all_code(text: str, *, keep_comments: bool = False) -> str:
    """Blank block-level code plus inline code spans, including spans across lines."""
    return _mask_inline_code(mask_blocks(text, keep_comments=keep_comments), skip_comments=keep_comments)


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
        elif text[index] == "\n" and BLANK_LINE_RE.match(text, index + 1):
            # A blank line (LF or CRLF, optionally with spaces) ends the paragraph.
            return None
    return None


def _definition_target(rest: str) -> str | None:
    """Return the destination of a reference definition's remainder, or None.

    The remainder must be a destination optionally followed by whitespace and a
    single-line title; anything else means the line is ordinary text.
    """
    parsed = _parse_destination(rest, 0)
    if parsed is None:
        return None
    target, end = parsed
    trailing = rest[end:]
    if not trailing.strip():
        return target
    if trailing[:1] in " \t" and _skip_title(trailing, 0) == len(trailing):
        return target
    return None


def extract_links(text: str) -> list[tuple[str, int]]:
    """Return (destination, line) for inline and reference links, excluding images and code."""
    source = mask_all_code(text)
    # Every reference definition is checked, so reference-style uses need no second pass.
    links: list[tuple[str, int]] = []
    seen_labels: set[str] = set()
    chars = list(source)
    lines = source.splitlines(keepends=True)
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line)

    def blank(line_index: int) -> None:
        start = starts[line_index]
        for position in range(start, start + len(lines[line_index].rstrip("\r\n"))):
            chars[position] = " "

    skip_next = False
    for line_index, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        match = REFERENCE_DEFINITION_RE.match(line.rstrip("\r\n"))
        if not match or match.group(1).startswith("^"):
            continue
        rest = match.group(2)
        target_index = line_index
        if not rest.strip():
            # Destination on the following line: "[id]:\n  target".
            if line_index + 1 >= len(lines) or not lines[line_index + 1].strip():
                continue
            target_index = line_index + 1
            rest = lines[target_index].rstrip("\r\n")
        target = _definition_target(rest)
        if target is None:
            # Ordinary text such as "[INFO]: server started".
            continue
        label = _normalize_label(match.group(1))
        if label not in seen_labels:
            seen_labels.add(label)
            links.append((target, target_index + 1))
        blank(line_index)
        if target_index != line_index:
            blank(target_index)
            skip_next = True
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
        if part == "..":
            current /= part
            continue
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
    inside_root: bool = False
    private_violation: bool = False


def resolve_local(
    root: Path,
    base_dir: Path,
    decoded: str,
    *,
    check_private_paths: bool = True,
    root_relative: bool = True,
) -> ResolvedPath:
    """Check a local path's lexical boundary, exact case, and resolved location."""
    root = Path(os.path.abspath(root))
    if not root_relative and decoded.startswith(("~/", "~\\")):
        decoded = os.path.expanduser(decoded)
    home_match = HOME_PATH_PATTERN.match(decoded)
    absolute_windows = WINDOWS_ABSOLUTE_RE.match(decoded)
    if home_match:
        if check_private_paths:
            return ResolvedPath(Path(decoded), "machine-specific home path", private_violation=True)
        case_base = Path(home_match.group())
    else:
        case_base = root
    if home_match or absolute_windows:
        joined = Path(decoded)
        if not joined.is_absolute():
            if check_private_paths:
                return ResolvedPath(joined, "escapes the project root", private_violation=True)
            return ResolvedPath(joined, "does not exist")
    elif root_relative and decoded.startswith("/"):
        joined = root / decoded.lstrip("/")
    else:
        joined = base_dir.absolute() / decoded
    lexical = Path(os.path.abspath(joined))
    inside_root = lexical.is_relative_to(root)
    if check_private_paths and not inside_root:
        return ResolvedPath(lexical, "escapes the project root", private_violation=True)

    try:
        real = joined.resolve(strict=True)
    except (OSError, RuntimeError):
        return ResolvedPath(lexical, "does not exist")
    real_root = root.resolve()
    inside_root = inside_root and real.is_relative_to(real_root)
    if check_private_paths and not inside_root:
        return ResolvedPath(lexical, "resolves outside the project root", private_violation=True)

    try:
        case_base = Path(os.path.commonpath([case_base, lexical, joined]))
    except ValueError:
        # A different drive has no common prefix.
        case_base = Path(joined.anchor)
    if not joined.is_relative_to(case_base):
        case_base = Path(joined.anchor)
    if not _exact_case_exists(case_base, joined.relative_to(case_base).parts):
        return ResolvedPath(lexical, "differs in letter case from the file on disk")
    if ".." in joined.parts:
        # Folding a parent segment may change the destination after a symlink.
        try:
            same_target = lexical.samefile(real)
        except OSError:
            same_target = False
        if not same_target:
            lexical = root / real.relative_to(real_root) if inside_root else real
    return ResolvedPath(lexical, inside_root=inside_root)


def _local_link_target(target: str) -> tuple[str, str] | None:
    # A Windows drive letter otherwise looks like a URL scheme.
    path, _, fragment = target.partition("#")
    decoded = unquote(path.partition("?")[0])
    if HOME_PATH_PATTERN.match(decoded) or WINDOWS_ABSOLUTE_RE.match(decoded):
        return decoded, fragment
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("//"):
        return None
    return unquote(parsed.path), parsed.fragment


def _ignored_directory(name: str) -> bool:
    return name.startswith(".") or name in WALK_IGNORED_DIRS or name in ARTIFACT_AND_VENDOR_DIRS


def _direct_subdirectories(directory: Path) -> set[str]:
    try:
        with os.scandir(directory) as entries:
            return {entry.name for entry in entries if not _ignored_directory(entry.name) and entry.is_dir()}
    except OSError:
        return set()


def _top_level_dirs(root: Path) -> set[str]:
    tracked = _git_paths(root, "ls-files", "-z")
    if tracked is not None:
        names = {entry.split("/", 1)[0] for entry in tracked if "/" in entry}
        return {name for name in names if not _ignored_directory(name)}
    return _direct_subdirectories(root)


def code_path_candidate(content: str, candidate_dirs: set[str]) -> tuple[str, str] | None:
    """Classify backtick text as ('root'|'doc', path) when it names a project path."""
    value = LOCATION_SUFFIX_RE.sub("", content.strip())
    if not value or not CODE_PATH_RE.fullmatch(value):
        return None
    named = [segment for segment in value.split("/") if segment not in {"", ".", ".."}]
    if not named or any(
        segment in ARTIFACT_AND_VENDOR_DIRS
        or PLACEHOLDER_SEGMENT_RE.fullmatch(segment)
        or not re.search(r"[A-Za-z0-9]", segment)
        for segment in named
    ):
        return None
    if value.startswith("./") or value.startswith("../"):
        return "doc", value
    first, slash, _ = value.partition("/")
    if slash and first in candidate_dirs:
        return "root", value
    return None


# ---------------------------------------------------------------------------
# File enumeration


def _git_paths(root: Path, *args: str, input: bytes | None = None) -> list[str] | None:
    """Read a NUL-delimited Git path list, or return None when Git fails."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            input=input,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return [entry for entry in os.fsdecode(completed.stdout).split("\0") if entry]


def list_project_files(root: Path) -> list[Path]:
    """List files tracked or not ignored by git; fall back to a filtered walk."""
    entries = _git_paths(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if entries is not None:
        return sorted({root / entry for entry in entries if (root / entry).is_file()})
    files = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not _ignored_directory(name))
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


def _git_ignore_safe(root: Path, relative: Path) -> bool:
    prefix = root
    for part in relative.parts:
        prefix /= part
        if prefix.is_symlink() or (prefix / ".git").exists():
            return False
    return True


def _ignored_code_paths(root: Path, warnings: list[tuple[str, set[str]]]) -> set[str]:
    paths = {path for _, attempts in warnings for path in attempts}
    safe = sorted(path for path in paths if _git_ignore_safe(root, Path(path)))
    if not safe:
        return set()
    payload = os.fsencode("\0".join(safe) + "\0")
    ignored = _git_paths(root, "check-ignore", "-z", "--stdin", input=payload)
    return set(ignored or ())


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


def _historical_directories(root: Path, real_root: Path, directories: list[str] | tuple[str, ...]) -> list[str]:
    entries = [root / name for name in ENTRY_NAMES if (root / name).is_file()]
    declared = list(directories)
    for entry in entries or [root / FALLBACK_ENTRY]:
        if not entry.is_file() or not entry.resolve().is_relative_to(real_root):
            continue
        text = mask_all_code(_read_text(entry) or "", keep_comments=True)
        for comment in HTML_COMMENT_RE.finditer(text):
            if _is_escaped(text, comment.start()):
                continue
            match = HISTORICAL_DIR_RE.fullmatch(comment.group(1))
            if match:
                declared.extend(re.split(r"[,\s]+", match.group(1)))
    normalized = []
    for directory in declared:
        directory = directory.replace("\\", "/")
        if directory.startswith("/") or ntpath.splitdrive(directory)[0]:
            continue
        directory = posixpath.normpath(directory.strip("/"))
        if directory not in {".", ".."} and not directory.startswith("../"):
            normalized.append(directory)
    return normalized


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
    root = Path(os.path.abspath(root))
    real_root = root.resolve()
    historical = _historical_directories(root, real_root, historical_dirs)
    files = list_project_files(root)
    docs: dict[Path, _Doc] = {}
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        relative = path.relative_to(root)
        directories = relative.parts[:-1]
        if any(_ignored_directory(part) for part in directories):
            continue
        text = _read_text(path)
        if text is None or not path.resolve().is_relative_to(real_root):
            continue
        frozen = any(part.casefold() in HISTORICAL_DIR_NAMES for part in directories)
        frozen = frozen or _is_under(relative.parent.as_posix(), historical)
        docs[path] = _Doc(path, relative.as_posix(), text, frozen)

    top_dirs = _top_level_dirs(root)
    child_dirs: dict[Path, set[str]] = {}
    edges: dict[Path, set[Path]] = {}
    pending_warnings: list[tuple[str, set[str]]] = []
    for doc in docs.values():
        candidate_dirs = top_dirs.copy()
        parent = doc.path.parent
        while parent != root and parent.is_relative_to(root):
            if parent not in child_dirs:
                child_dirs[parent] = _direct_subdirectories(parent)
            candidate_dirs.update(child_dirs[parent])
            parent = parent.parent
        edges[doc.path] = _check_document(
            root, doc, docs, candidate_dirs, report, pending_warnings, check_private_paths=check_private_paths
        )

    ignored = _ignored_code_paths(root, pending_warnings)
    for warning, attempts in pending_warnings:
        if ignored.isdisjoint(attempts):
            report.warn(warning)
    _check_reachability(root, docs, edges, strict, report)
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


def _resolve_code_path(
    root: Path,
    base_dir: Path,
    kind: str,
    value: str,
    *,
    check_private_paths: bool,
) -> tuple[ResolvedPath, set[str]]:
    bases = [base_dir]
    if kind == "root":
        bases.extend(parent for parent in base_dir.parents if parent.is_relative_to(root))
    elif base_dir != root:
        bases.append(root)

    missing: set[str] = set()
    best_problem = None
    for base in bases:
        resolved = resolve_local(root, base, value, check_private_paths=check_private_paths)
        if not resolved.problem:
            return resolved, set()
        if resolved.problem == "does not exist":
            if resolved.path.is_relative_to(root):
                relative = resolved.path.relative_to(root).as_posix()
                missing.add(relative + "/" if value.endswith("/") else relative)
        elif best_problem is None:
            best_problem = resolved
    return best_problem or resolved, missing


def _check_document(
    root: Path,
    doc: _Doc,
    docs: dict[Path, _Doc],
    candidate_dirs: set[str],
    report: Report,
    pending_warnings: list[tuple[str, set[str]]],
    *,
    check_private_paths: bool,
) -> set[Path]:
    targets: set[Path] = set()
    base_dir = doc.path.parent
    for target, line in extract_links(doc.text):
        local = _local_link_target(target)
        if local is None:
            continue
        path, fragment = local
        location = f"{doc.relative}:{line}"
        if not path:
            if fragment and not doc.historical and not _has_anchor(doc.anchors, fragment):
                report.error(f"{location}: missing heading anchor '#{fragment}'")
            continue
        resolved = resolve_local(root, base_dir, path, check_private_paths=check_private_paths)
        if resolved.problem:
            if resolved.private_violation or not doc.historical:
                report.error(f"{location}: broken link '{target}' ({resolved.problem})")
            continue
        if resolved.inside_root and (markdown := _md_target(resolved.path)) is not None:
            targets.add(markdown)
        if fragment and not doc.historical and resolved.path.suffix.lower() == ".md":
            linked = docs.get(resolved.path)
            anchors = linked.anchors if linked else heading_anchors(_read_text(resolved.path) or "")
            if not _has_anchor(anchors, fragment):
                report.error(f"{location}: missing heading anchor '{target}'")

    if doc.is_navigation:
        for value, line in _imports(doc.text):
            resolved = resolve_local(root, base_dir, value, check_private_paths=check_private_paths, root_relative=False)
            if resolved.problem:
                # Only CLAUDE.md evaluates @imports; elsewhere '@name/pkg' is ordinary prose.
                if doc.path.name == "CLAUDE.md" and (resolved.private_violation or not doc.historical):
                    report.error(f"{doc.relative}:{line}: broken import '@{value}' ({resolved.problem})")
            elif resolved.inside_root and resolved.path.suffix.lower() == ".md":
                targets.add(resolved.path)

    masked = mask_blocks(doc.text)
    for start, _, content in iter_code_spans(masked):
        line = _line_of(masked, start)
        candidate = code_path_candidate(content, candidate_dirs)
        if candidate is not None:
            kind, value = candidate
            resolved, missing = _resolve_code_path(root, base_dir, kind, value, check_private_paths=check_private_paths)
            if resolved.problem:
                if not doc.historical:
                    warning = f"{doc.relative}:{line}: code path '{content}' {resolved.problem}"
                    pending_warnings.append((warning, missing))
                continue
            if doc.is_navigation and resolved.inside_root:
                markdown = _md_target(resolved.path)
                if markdown is not None:
                    targets.add(markdown)
        elif doc.is_navigation and re.fullmatch(r"[A-Za-z0-9_.-]+\.md", content.strip()):
            # A bare document name in an entrypoint or index navigates only when it exists.
            for base in (base_dir, root):
                resolved = resolve_local(root, base, content.strip(), check_private_paths=check_private_paths)
                if resolved.inside_root:
                    targets.add(resolved.path)
                    break
    return targets


def _check_reachability(
    root: Path,
    docs: dict[Path, _Doc],
    edges: dict[Path, set[Path]],
    strict: bool,
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
        local = _local_link_target(target)
        if local is None or not local[0]:
            continue
        resolved = resolve_local(skill_root, skill_root, local[0])
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
        help="reject outside-root links and imports, and machine-specific home paths in project files",
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
