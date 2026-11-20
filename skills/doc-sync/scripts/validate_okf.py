#!/usr/bin/env python3
"""Validate OKF v0.3 bundles and the stricter DocSync producer profile.

Earlier versions are read best-effort; the profile reports them for migration.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


FRONTMATTER_DELIMITER = "---"
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
REFERENCE_DEFINITION_RE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$")
FOOTNOTE_DEFINITION_RE = re.compile(r"^ {0,3}\[\^([^\]\n]+)\]:", re.MULTILINE)
FOOTNOTE_REFERENCE_RE = re.compile(r"(?<!\[)\[\^([^\]\n]+)\]")
RESERVED_NAMES = {"index.md", "log.md"}
CURRENT_OKF_VERSION = "0.3"
# Earlier versions are read best-effort and migrated, not maintained as producer profiles.
LEGACY_OKF_VERSIONS = {"0.1", "0.2"}
MIGRATION_GUIDE = "references/okf-migration.md"
ROOT_INDEX_STRING_KEYS = ("title", "description", "license")
RFC3339_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RFC3339_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
PRODUCER_ACTOR_RE = re.compile(r"^[^\s/:]+/\S+$")
SCHEME_ACTOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$")
ATX_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ConceptDocument:
    path: Path
    metadata: dict[str, Any]
    frontmatter: str
    body: str


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            header = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return header, body
    raise ValueError("frontmatter is missing its closing --- delimiter")


def parse_yaml(text: str) -> Any:
    """Parse YAML with PyYAML when available, then macOS/system Ruby as a fallback."""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        pass
    except Exception as exc:  # pragma: no cover - exact parser exception varies
        raise ValueError(str(exc)) from exc

    ruby = shutil.which("ruby")
    if not ruby:
        raise RuntimeError(
            "no YAML parser available; install PyYAML or provide Ruby with its yaml library"
        )
    program = (
        "require 'json'; require 'yaml'; require 'date'; require 'time'; "
        "value = YAML.safe_load(STDIN.read, permitted_classes: [Date, Time], aliases: true); "
        "def normalize(value); case value; when Time then value.iso8601; when Date then value.iso8601; "
        "when Array then value.map { |item| normalize(item) }; when Hash then value.transform_values { |item| normalize(item) }; "
        "else value; end; end; STDOUT.write(JSON.generate(normalize(value)))"
    )
    completed = subprocess.run(
        [ruby, "-e", program],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or "Ruby YAML parser failed"
        raise ValueError(message)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ruby YAML parser returned invalid JSON: {exc}") from exc


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _mask_inline_code(line: str) -> str:
    chars = list(line)
    index = 0
    while index < len(line):
        if line[index] != "`" or _is_escaped(line, index):
            index += 1
            continue
        run_end = index
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        delimiter = line[index:run_end]
        closing = line.find(delimiter, run_end)
        if closing < 0:
            index = run_end
            continue
        for position in range(index, closing + len(delimiter)):
            if chars[position] not in "\r\n":
                chars[position] = " "
        index = closing + len(delimiter)
    return "".join(chars)


def _leading_indentation_columns(line: str) -> int:
    columns = 0
    for char in line:
        if char == " ":
            columns += 1
        elif char == "\t":
            columns += 4 - (columns % 4)
        else:
            break
    return columns


def mask_markdown_code(text: str) -> str:
    """Mask fenced, indented, and inline code while preserving offsets and lines."""
    output: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    in_html_comment = False
    list_contexts: list[tuple[int, int, int]] = []
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        newline = line[len(content) :]
        stripped = content.lstrip(" ")
        indent = len(content) - len(stripped)
        indentation_columns = _leading_indentation_columns(content)
        list_marker = re.match(
            r"(?:[-+*]|\d+[.)])[ \t]+",
            content.lstrip(" \t"),
        )
        has_parent_list = any(
            content_indent <= indentation_columns < code_indent
            for _, content_indent, code_indent in list_contexts
        )
        real_list_item = list_marker is not None and (
            indentation_columns < 4 or has_parent_list
        )
        nested_list_item = real_list_item and has_parent_list
        if real_list_item:
            list_contexts = [
                context
                for context in list_contexts
                if context[0] < indentation_columns
            ]
            content_indent = indentation_columns + list_marker.end()
            list_contexts.append(
                (indentation_columns, content_indent, content_indent + 4)
            )
        elif content.strip() and indentation_columns == 0:
            list_contexts.clear()
        fence_match = re.match(r"(`{3,}|~{3,})", stripped) if indent <= 3 else None
        if fence_char is not None:
            closing = (
                fence_match is not None
                and fence_match.group(1)[0] == fence_char
                and len(fence_match.group(1)) >= fence_length
                and not stripped[len(fence_match.group(1)) :].strip()
            )
            output.append(" " * len(content) + newline)
            if closing:
                fence_char = None
                fence_length = 0
            continue
        if fence_match:
            fence_char = fence_match.group(1)[0]
            fence_length = len(fence_match.group(1))
            output.append(" " * len(content) + newline)
            continue
        indented = content.startswith("    ") or content.startswith("\t")
        if indented and not nested_list_item:
            output.append(" " * len(content) + newline)
            continue

        chars = list(content)
        index = 0
        while index < len(content):
            if not in_html_comment and content.startswith("<!--", index):
                in_html_comment = True
            if in_html_comment:
                chars[index] = " "
                if content.startswith("-->", index):
                    for position in range(index, min(index + 3, len(chars))):
                        chars[position] = " "
                    index += 3
                    in_html_comment = False
                    continue
            index += 1
        output.append(_mask_inline_code("".join(chars)) + newline)
    return "".join(output)


def normalize_reference_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).casefold()


def _unescape_markdown(value: str) -> str:
    return re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~ ])", r"\1", value)


def _parse_destination(text: str, start: int) -> tuple[str, int] | None:
    index = start
    while index < len(text) and text[index] in " \t":
        index += 1
    if index >= len(text):
        return None
    if text[index] == "<":
        end = index + 1
        while end < len(text):
            if text[end] == ">" and not _is_escaped(text, end):
                return _unescape_markdown(text[index + 1 : end]), end + 1
            if text[end] in "\r\n":
                return None
            end += 1
        return None

    destination: list[str] = []
    depth = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            destination.append(text[index + 1])
            index += 2
            continue
        if char == "(":
            depth += 1
            destination.append(char)
            index += 1
            continue
        if char == ")":
            if depth == 0:
                break
            depth -= 1
            destination.append(char)
            index += 1
            continue
        if char.isspace() and depth == 0:
            break
        destination.append(char)
        index += 1
    if depth or not destination:
        return None
    return "".join(destination), index


def _skip_optional_title(text: str, index: int) -> int | None:
    while index < len(text) and text[index] in " \t":
        index += 1
    if index >= len(text) or text[index] == ")":
        return index
    opener = text[index]
    if opener not in {'"', "'", "("}:
        return None
    closer = ")" if opener == "(" else opener
    index += 1
    while index < len(text):
        if text[index] == closer and not _is_escaped(text, index):
            index += 1
            while index < len(text) and text[index] in " \t":
                index += 1
            return index
        if text[index] in "\r\n":
            return None
        index += 1
    return None


def _find_closing_bracket(text: str, opening: int) -> int | None:
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
        elif text[index] in "\r\n":
            return None
    return None


def _reference_definitions(masked: str) -> tuple[dict[str, str], list[tuple[int, int]]]:
    definitions: dict[str, str] = {}
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in masked.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        match = REFERENCE_DEFINITION_RE.match(content)
        if match:
            parsed = _parse_destination(match.group(2), 0)
            if parsed is not None:
                target, end = parsed
                trailing = match.group(2)[end:]
                if not trailing.strip() or _valid_reference_title(trailing):
                    label = normalize_reference_label(match.group(1))
                    if not label.startswith("^"):
                        definitions.setdefault(label, target)
                        spans.append((offset, offset + len(content)))
        offset += len(line)
    return definitions, spans


def _valid_reference_title(trailing: str) -> bool:
    value = trailing.strip()
    if not value:
        return True
    opener = value[0]
    if opener not in {'"', "'", "("}:
        return False
    closer = ")" if opener == "(" else opener
    return len(value) >= 2 and value[-1] == closer and not _is_escaped(value, len(value) - 1)


def extract_markdown_link_targets(
    text: str,
    reference_definitions: dict[str, str] | None = None,
) -> list[str]:
    """Extract non-image inline and reference-link destinations from Markdown."""
    masked = mask_markdown_code(text)
    local_definitions, definition_spans = _reference_definitions(masked)
    definitions = dict(reference_definitions or {})
    for label, target in local_definitions.items():
        definitions.setdefault(label, target)
    chars = list(masked)
    for start, end in definition_spans:
        for index in range(start, end):
            if chars[index] not in "\r\n":
                chars[index] = " "
    source = "".join(chars)

    targets: list[str] = []
    index = 0
    while index < len(source):
        if source[index] != "[" or _is_escaped(source, index):
            index += 1
            continue
        closing = _find_closing_bracket(source, index)
        if closing is None:
            index += 1
            continue
        if index > 0 and source[index - 1] == "!" and not _is_escaped(source, index - 1):
            next_index = closing + 1
            if next_index < len(source) and source[next_index] == "(":
                parsed = _parse_destination(source, next_index + 1)
                if parsed is not None:
                    _, after_target = parsed
                    after_title = _skip_optional_title(source, after_target)
                    if after_title is not None and after_title < len(source) and source[after_title] == ")":
                        index = after_title + 1
                        continue
            elif next_index < len(source) and source[next_index] == "[":
                reference_end = _find_closing_bracket(source, next_index)
                if reference_end is not None:
                    index = reference_end + 1
                    continue
            index = next_index
            continue
        label = source[index + 1 : closing]
        next_index = closing + 1
        if next_index < len(source) and source[next_index] == "(":
            parsed = _parse_destination(source, next_index + 1)
            if parsed is not None:
                target, after_target = parsed
                after_title = _skip_optional_title(source, after_target)
                if after_title is not None and after_title < len(source) and source[after_title] == ")":
                    targets.append(target)
                    index = after_title + 1
                    continue
        elif next_index < len(source) and source[next_index] == "[":
            reference_end = _find_closing_bracket(source, next_index)
            if reference_end is not None:
                reference = source[next_index + 1 : reference_end] or label
                target = definitions.get(normalize_reference_label(reference))
                if target is not None:
                    targets.append(target)
                    index = reference_end + 1
                    continue
        else:
            target = definitions.get(normalize_reference_label(label))
            if target is not None:
                targets.append(target)
                index = closing + 1
                continue
        index = closing + 1
    return targets


def _not_a_concept(path: Path, result: ValidationResult, profile: bool, reason: str) -> None:
    """OKF section 3.2: a Markdown file without frontmatter or type is not a concept."""
    if profile:
        result.errors.append(
            f"{path}: DocSync profile requires every non-reserved bundle Markdown file to be a typed concept ({reason})"
        )
    else:
        result.warnings.append(f"{path}: not an OKF concept and skipped ({reason})")


def validate_concept(path: Path, result: ValidationResult, profile: bool = False) -> ConceptDocument | None:
    try:
        header, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        result.errors.append(f"{path}: {exc}")
        return None
    if header is None:
        _not_a_concept(path, result, profile, "concept is missing YAML frontmatter")
        return None
    try:
        metadata = parse_yaml(header)
    except (RuntimeError, ValueError) as exc:
        result.errors.append(f"{path}: invalid YAML frontmatter: {exc}")
        return None
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        result.errors.append(f"{path}: frontmatter must be a YAML mapping")
        return None
    concept_type = metadata.get("type")
    if not isinstance(concept_type, str) or not concept_type.strip():
        _not_a_concept(path, result, profile, "frontmatter requires a non-empty string 'type'")
        return None
    return ConceptDocument(path=path, metadata=metadata, frontmatter=header, body=body)


def read_declared_version(bundle_root: Path) -> str | None:
    """Return the root index okf_version string, if one is declared and readable."""
    try:
        header, _ = split_frontmatter((bundle_root / "index.md").read_text(encoding="utf-8"))
        parsed = parse_yaml(header) if header is not None else None
    except (OSError, UnicodeDecodeError, ValueError, RuntimeError):
        return None
    if not isinstance(parsed, dict):
        return None
    version = parsed.get("okf_version")
    return version.strip() if isinstance(version, str) and version.strip() else None


def _version_notice(version: str) -> str:
    if version in LEGACY_OKF_VERSIONS:
        return (
            f"bundle declares OKF v{version}; DocSync maintains only v{CURRENT_OKF_VERSION}. "
            f"Migrate it with {MIGRATION_GUIDE}"
        )
    return f"unknown OKF version '{version}'; attempting best-effort validation with v{CURRENT_OKF_VERSION} rules"


def validate_index(
    path: Path,
    bundle_root: Path,
    result: ValidationResult,
    profile: bool = False,
) -> dict[str, Any] | None:
    try:
        header, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        result.errors.append(f"{path}: {exc}")
        return None
    metadata: dict[str, Any] | None = None
    is_root = path.parent == bundle_root
    if header is not None and not is_root:
        result.errors.append(f"{path}: nested index.md must not contain frontmatter")
    if header is not None and is_root:
        metadata = _validate_root_index_metadata(path, bundle_root, header, result, profile)
    if not re.search(r"^#\s+\S", body, re.MULTILINE):
        result.errors.append(f"{path}: index.md requires at least one Markdown heading")
    if not extract_markdown_link_targets(body):
        result.errors.append(f"{path}: index.md requires at least one Markdown link entry")
    return metadata


def _validate_root_index_metadata(
    path: Path,
    bundle_root: Path,
    header: str,
    result: ValidationResult,
    profile: bool,
) -> dict[str, Any] | None:
    """Check bundle metadata: okf_version, title, description, license, extension keys (section 8.1)."""
    try:
        parsed = parse_yaml(header)
    except (RuntimeError, ValueError) as exc:
        result.errors.append(f"{path}: invalid root index frontmatter: {exc}")
        return None
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        result.errors.append(f"{path}: root index frontmatter must be a YAML mapping")
        return None
    version = parsed.get("okf_version")
    if not _blank(version) and not _non_empty_string(version):
        result.errors.append(f"{path}: root index okf_version must be a non-empty quoted string")
        return None
    for key in ROOT_INDEX_STRING_KEYS:
        value = parsed.get(key)
        if _blank(value):
            continue
        if not _non_empty_string(value):
            message = f"{path}: root index {key} must be a non-empty string"
            (result.errors if profile else result.warnings).append(message)
        elif key == "description" and "\n" in value.strip() and profile:
            result.errors.append(f"{path}: DocSync profile root index description must be one line")
    license_value = parsed.get("license")
    if _non_empty_string(license_value) and _looks_like_local_path(license_value):
        candidate, problem = _local_candidate(path, bundle_root, license_value)
        if candidate is not None and (problem or not candidate.exists()):
            message = f"{path}: root index license path does not resolve in the bundle '{license_value}'"
            (result.errors if profile else result.warnings).append(message)
    if _non_empty_string(version):
        if version.strip() != CURRENT_OKF_VERSION:
            result.warnings.append(f"{path}: {_version_notice(version.strip())}")
    else:
        result.warnings.append(f"{path}: root index frontmatter does not declare okf_version")
    return parsed


def validate_log(path: Path, result: ValidationResult) -> None:
    try:
        header, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        result.errors.append(f"{path}: {exc}")
        return
    if header is not None:
        result.errors.append(f"{path}: log.md must not contain frontmatter")
    headings = H2_RE.findall(body)
    if not headings:
        result.errors.append(f"{path}: log.md requires YYYY-MM-DD level-two date headings")
        return
    dates: list[date] = []
    for heading in headings:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", heading):
            result.errors.append(f"{path}: invalid log heading '## {heading}'")
            continue
        try:
            dates.append(date.fromisoformat(heading))
        except ValueError:
            result.errors.append(f"{path}: invalid ISO date heading '## {heading}'")
    if dates != sorted(dates, reverse=True):
        result.errors.append(f"{path}: log date headings must be newest first")


def _local_candidate(path: Path, bundle_root: Path, target: str) -> tuple[Path | None, str | None]:
    parsed = urlsplit(target.strip())
    if parsed.scheme or parsed.netloc or target.startswith("#") or not parsed.path:
        return None, None
    decoded_path = unquote(parsed.path)
    bundle_absolute = decoded_path.startswith("/")
    candidate = bundle_root / decoded_path.lstrip("/") if bundle_absolute else path.parent / decoded_path
    resolved_candidate = candidate.resolve(strict=False)
    if bundle_absolute and not resolved_candidate.is_relative_to(bundle_root.resolve(strict=False)):
        return resolved_candidate, "escapes"
    return resolved_candidate, None


def validate_links(
    path: Path,
    bundle_root: Path,
    result: ValidationResult,
    strict_links: bool,
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    for target in extract_markdown_link_targets(text):
        candidate, problem = _local_candidate(path, bundle_root, target)
        if candidate is None:
            continue
        if problem == "escapes":
            message = f"{path}: local link escapes the bundle '{target}'"
        elif candidate.exists():
            continue
        else:
            message = f"{path}: broken local link '{target}'"
        if strict_links:
            result.errors.append(message)
        else:
            result.warnings.append(message)


def _normalized_type(value: Any) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold() if isinstance(value, str) else ""


def _metadata_problem(
    concept: ConceptDocument, result: ValidationResult, profile: bool, message: str
) -> None:
    rendered = f"{concept.path}: {message}"
    if profile:
        result.errors.append(rendered)
    else:
        result.warnings.append(rendered)


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _blank(value: Any) -> bool:
    """Section 11.2: null, an empty string, and an empty list mean an absent key."""
    return value is None or (isinstance(value, str) and not value.strip()) or value == []


def _as_list(value: Any) -> list[Any]:
    """Section 11.2: one item stands for a list with one item."""
    if _blank(value):
        return []
    return value if isinstance(value, list) else [value]


def _parse_okf_timestamp(value: Any) -> datetime | None:
    """Parse the two RFC 3339 forms of section 5: a date-time with an offset, or a date (UTC midnight)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None and value.utcoffset() is not None else None
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    try:
        if RFC3339_DATE_RE.match(candidate):
            day = date.fromisoformat(candidate)
            return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        if RFC3339_DATETIME_RE.match(candidate):
            return datetime.fromisoformat(candidate.upper().replace("Z", "+00:00"))
    except ValueError:
        return None
    return None


def _is_date_only(value: Any) -> bool:
    if isinstance(value, datetime):
        return False
    if isinstance(value, date):
        return True
    return isinstance(value, str) and bool(RFC3339_DATE_RE.match(value.strip()))


TIMESTAMP_RULE = "an RFC 3339 date-time with an offset or a date"


def _validate_usage_window(
    concept: ConceptDocument,
    value: Any,
    result: ValidationResult,
    profile: bool,
    label: str,
) -> None:
    if not isinstance(value, dict):
        _metadata_problem(concept, result, profile, f"{label} must be a mapping")
        return
    timestamps: dict[str, datetime] = {}
    for field_name in ("from", "to"):
        if _blank(value.get(field_name)):
            _metadata_problem(concept, result, profile, f"{label}.{field_name} is required")
            continue
        parsed = _parse_okf_timestamp(value[field_name])
        if parsed is None:
            _metadata_problem(concept, result, profile, f"{label}.{field_name} must be {TIMESTAMP_RULE}")
        else:
            timestamps[field_name] = parsed
    if len(timestamps) == 2 and timestamps["from"] > timestamps["to"]:
        _metadata_problem(concept, result, profile, f"{label}.from must not be after {label}.to")


def _valid_window(value: Any) -> bool:
    return isinstance(value, dict) and all(
        _parse_okf_timestamp(value.get(field_name)) is not None for field_name in ("from", "to")
    )


def _looks_like_local_path(value: str) -> bool:
    """Recognize unambiguous local paths without rejecting source scope descriptors."""
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("#"):
        return False
    path = parsed.path
    if path.startswith(("/", "./", "../")):
        return True
    return "/" in path


def _valid_actor(value: Any) -> bool:
    """Section 7: <producer>/<version>, or <scheme>:<id> with any scheme."""
    if not _non_empty_string(value):
        return False
    actor = value.strip()
    return bool(PRODUCER_ACTOR_RE.match(actor) or SCHEME_ACTOR_RE.match(actor))


def _duplicate_keys(frontmatter: str) -> list[str]:
    """Return dotted paths of repeated mapping keys (section 4)."""
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        seen: set[str] = set()
        repeated: list[str] = []
        for match in re.finditer(r"^([A-Za-z0-9_.\-]+)[ \t]*:", frontmatter, re.MULTILINE):
            key = match.group(1)
            if key in seen and key not in repeated:
                repeated.append(key)
            seen.add(key)
        return repeated
    try:
        root = yaml.compose(frontmatter, Loader=yaml.SafeLoader)
    except Exception:  # pragma: no cover - parse errors are reported elsewhere
        return []
    repeated = []

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, yaml.MappingNode):
            seen_keys: set[str] = set()
            for key_node, value_node in node.value:
                key = str(getattr(key_node, "value", ""))
                label = f"{prefix}.{key}" if prefix else key
                if key in seen_keys and label not in repeated:
                    repeated.append(label)
                seen_keys.add(key)
                walk(value_node, label)
        elif isinstance(node, yaml.SequenceNode):
            for index, item in enumerate(node.value):
                walk(item, f"{prefix}[{index}]")

    walk(root, "")
    return repeated


def _computation_fence_count(body: str) -> int:
    """Count fenced code blocks in the first section headed Computation (section 10.3)."""
    level: int | None = None
    count = 0
    fence: str | None = None
    for line in body.splitlines():
        stripped = line.lstrip(" ")
        if fence is not None:
            if stripped.startswith(fence) and not stripped[len(fence):].strip(fence[0]).strip():
                fence = None
            continue
        fence_match = re.match(r"(`{3,}|~{3,})", stripped) if len(line) - len(stripped) <= 3 else None
        if fence_match:
            fence = fence_match.group(1)
            if level is not None:
                count += 1
            continue
        heading = ATX_HEADING_RE.match(line)
        if heading:
            depth = len(heading.group(1))
            if level is not None and depth <= level:
                break
            if level is None and heading.group(2).strip().casefold() == "computation":
                level = depth
    return count


def _footnote_references(body: str) -> set[str]:
    references: set[str] = set()
    for match in FOOTNOTE_REFERENCE_RE.finditer(body):
        start = match.start()
        if _is_escaped(body, start) or (start > 0 and body[start - 1] == "!"):
            continue
        if body[match.end() : match.end() + 1] == "(":
            parsed = _parse_destination(body, match.end() + 1)
            if parsed is not None:
                _, after_target = parsed
                after_title = _skip_optional_title(body, after_target)
                if after_title is not None and body[after_title : after_title + 1] == ")":
                    continue
        outer_open = body.rfind("[", 0, start)
        if outer_open >= 0:
            outer_close = _find_closing_bracket(body, outer_open)
            if outer_close is not None and outer_close > start and body[outer_close + 1 : outer_close + 2] == "(":
                continue
        references.add(match.group(1))
    return references


def _check_path_field(
    concept: ConceptDocument,
    bundle_root: Path,
    result: ValidationResult,
    strict_links: bool,
    label: str,
    value: Any,
    declared_version: str | None,
    descriptor_allowed: bool = False,
) -> None:
    """Resolve a path field (section 6.2); scope descriptors are skipped where allowed."""
    if not isinstance(value, str) or not value.strip():
        return
    try:
        if descriptor_allowed and not _looks_like_local_path(value):
            return
        candidate, problem = _local_candidate(concept.path, bundle_root, value)
    except ValueError as exc:
        kind = "source resource" if label.startswith("sources[") else label
        _metadata_problem(concept, result, strict_links, f"invalid {kind} '{value}': {exc}")
        return
    if candidate is None:
        return
    if problem == "escapes":
        message = f"{concept.path}: local link escapes the bundle '{value}'"
    elif candidate.exists():
        return
    else:
        decoded = unquote(urlsplit(value.strip()).path)
        if (
            not strict_links
            and (declared_version is None or declared_version in LEGACY_OKF_VERSIONS)
            and not decoded.startswith(("/", "./", "../"))
        ):
            # Section 6.2: v0.2-or-earlier and undeclared bundles may resolve a bare path from the root.
            fallback = (bundle_root / decoded).resolve(strict=False)
            if fallback.is_relative_to(bundle_root.resolve(strict=False)) and fallback.exists():
                result.warnings.append(
                    f"{concept.path}: {label} '{value}' resolves only from the bundle root; "
                    f"rewrite it as '/{decoded}' when migrating to v{CURRENT_OKF_VERSION}"
                )
                return
        message = f"{concept.path}: broken local link '{value}'"
    if strict_links:
        result.errors.append(message)
    else:
        result.warnings.append(message)


def _validate_attested_computation(
    concept: ConceptDocument,
    bundle_root: Path,
    result: ValidationResult,
    profile: bool,
    strict_links: bool,
    declared_version: str | None,
) -> None:
    metadata = concept.metadata
    if not _non_empty_string(metadata.get("runtime")):
        _metadata_problem(concept, result, profile, "Attested Computation runtime must be a non-empty string")
    for index, parameter in enumerate(_as_list(metadata.get("parameters"))):
        label = f"parameters[{index}]"
        if not isinstance(parameter, dict):
            _metadata_problem(concept, result, profile, f"{label} must be a mapping")
            continue
        for key in ("name", "type"):
            if not _non_empty_string(parameter.get(key)):
                _metadata_problem(concept, result, profile, f"{label}.{key} must be a non-empty string")
        if not _blank(parameter.get("required")) and not isinstance(parameter["required"], bool):
            _metadata_problem(concept, result, profile, f"{label}.required must be a boolean")
    computation = metadata.get("computation")
    fences = _computation_fence_count(concept.body)
    if not _blank(computation):
        if not isinstance(computation, str):
            _metadata_problem(concept, result, profile, "computation must be a path string")
        else:
            _check_path_field(
                concept, bundle_root, result, strict_links, "computation", computation, declared_version
            )
        if fences:
            result.warnings.append(
                f"{concept.path}: computation is set, so the fenced block in the Computation section is ignored"
            )
    elif fences == 0:
        result.warnings.append(
            f"{concept.path}: no computation field or fenced block in a Computation section; "
            "consumers treat this Attested Computation as not attestable"
        )
    elif fences > 1:
        result.warnings.append(
            f"{concept.path}: the Computation section has {fences} fenced blocks; consumers use the first"
        )
    for key in ("executor", "attester"):
        value = metadata.get(key)
        if _blank(value):
            continue
        if not isinstance(value, dict) or not _non_empty_string(value.get("resource")):
            _metadata_problem(concept, result, profile, f"{key} must be a mapping with a non-empty resource")
            continue
        _check_path_field(
            concept, bundle_root, result, strict_links, f"{key}.resource", value["resource"], declared_version
        )
        if key == "executor" and not _blank(value.get("receipt")) and not all(
            _non_empty_string(item) for item in _as_list(value.get("receipt"))
        ):
            _metadata_problem(concept, result, profile, "executor.receipt must list field names")


def validate_concept_metadata(
    concept: ConceptDocument,
    bundle_root: Path,
    result: ValidationResult,
    profile: bool,
    strict_links: bool,
    declared_version: str | None = CURRENT_OKF_VERSION,
) -> None:
    """Check the provenance, trust, lifecycle, and computation families (sections 5, 7, 10)."""
    metadata = concept.metadata

    def present(key: str) -> bool:
        return not _blank(metadata.get(key))

    for key in _duplicate_keys(concept.frontmatter):
        _metadata_problem(concept, result, profile, f"frontmatter repeats the key '{key}'")

    generated = metadata.get("generated")
    if present("generated"):
        if not isinstance(generated, dict):
            _metadata_problem(concept, result, profile, "generated must be a mapping")
        else:
            if not _non_empty_string(generated.get("by")):
                _metadata_problem(concept, result, profile, "generated.by must be a non-empty string")
            elif not _valid_actor(generated["by"]):
                _metadata_problem(concept, result, profile, "generated.by must follow the OKF actor convention")
            if not _blank(generated.get("at")) and _parse_okf_timestamp(generated["at"]) is None:
                _metadata_problem(concept, result, profile, f"generated.at must be {TIMESTAMP_RULE}")
    elif profile:
        result.errors.append(f"{concept.path}: DocSync profile requires generated.by and generated.at")
    if profile and isinstance(generated, dict):
        generated_at = generated.get("at")
        if _parse_okf_timestamp(generated_at) is None or _is_date_only(generated_at):
            result.errors.append(
                f"{concept.path}: DocSync profile requires generated.at to be a timezone-aware date-time"
            )

    verified = metadata.get("verified")
    if present("verified"):
        events = [verified] if isinstance(verified, dict) else verified
        if not isinstance(events, list):
            _metadata_problem(concept, result, profile, "verified must be a mapping or list of mappings")
        else:
            for index, event in enumerate(events):
                label = f"verified[{index}]"
                if not isinstance(event, dict):
                    _metadata_problem(concept, result, profile, f"{label} must be a mapping")
                    continue
                if not _non_empty_string(event.get("by")):
                    _metadata_problem(concept, result, profile, f"{label}.by must be a non-empty string")
                elif not _valid_actor(event["by"]):
                    _metadata_problem(concept, result, profile, f"{label}.by must follow the OKF actor convention")
                if _parse_okf_timestamp(event.get("at")) is None:
                    _metadata_problem(concept, result, profile, f"{label}.at must be {TIMESTAMP_RULE}")
                elif profile and _is_date_only(event.get("at")):
                    result.errors.append(
                        f"{concept.path}: DocSync profile requires {label}.at to be a timezone-aware date-time"
                    )

    status = metadata.get("status")
    if present("status") and (
        not isinstance(status, str) or status not in {"draft", "stable", "deprecated"}
    ):
        _metadata_problem(concept, result, profile, "status must be draft, stable, or deprecated")
    if present("superseded_by"):
        superseded_by = metadata["superseded_by"]
        if status != "deprecated":
            _metadata_problem(concept, result, profile, "superseded_by requires status: deprecated")
        if not isinstance(superseded_by, str):
            _metadata_problem(concept, result, profile, "superseded_by must be a path string")
        else:
            _check_path_field(
                concept, bundle_root, result, strict_links, "superseded_by", superseded_by, declared_version
            )
    if present("stale_after") and _parse_okf_timestamp(metadata["stale_after"]) is None:
        _metadata_problem(concept, result, profile, f"stale_after must be {TIMESTAMP_RULE}")
    if present("usage_window"):
        _validate_usage_window(concept, metadata["usage_window"], result, profile, "usage_window")
    if present("resource"):
        _check_path_field(
            concept,
            bundle_root,
            result,
            strict_links,
            "resource",
            metadata["resource"],
            declared_version,
            descriptor_allowed=True,
        )

    sources = metadata.get("sources")
    if isinstance(sources, dict):
        sources = [sources]
    source_ids: set[str] = set()
    has_valid_shared_window = _valid_window(metadata.get("usage_window"))
    if present("sources"):
        if not isinstance(sources, list):
            _metadata_problem(concept, result, profile, "sources must be a list of mappings")
        else:
            for index, source in enumerate(sources):
                label = f"sources[{index}]"
                if not isinstance(source, dict):
                    _metadata_problem(concept, result, profile, f"{label} must be a mapping")
                    continue
                if not _non_empty_string(source.get("resource")):
                    _metadata_problem(concept, result, profile, f"{label}.resource must be a non-empty string")
                else:
                    _check_path_field(
                        concept,
                        bundle_root,
                        result,
                        strict_links,
                        f"{label}.resource",
                        source["resource"],
                        declared_version,
                        descriptor_allowed=True,
                    )
                for field_name in ("id", "title", "author"):
                    if not _blank(source.get(field_name)) and not _non_empty_string(source[field_name]):
                        _metadata_problem(concept, result, profile, f"{label}.{field_name} must be a non-empty string")
                if _non_empty_string(source.get("author")) and not _valid_actor(source["author"]):
                    _metadata_problem(concept, result, profile, f"{label}.author must follow the OKF actor convention")
                if _non_empty_string(source.get("id")):
                    source_id = source["id"].strip()
                    if source_id in source_ids:
                        _metadata_problem(concept, result, profile, f"duplicate sources[].id '{source_id}'")
                    source_ids.add(source_id)
                usage_count = source.get("usage_count")
                has_usage_count = not _blank(usage_count)
                if has_usage_count and (isinstance(usage_count, bool) or not isinstance(usage_count, int) or usage_count < 0):
                    _metadata_problem(concept, result, profile, f"{label}.usage_count must be a non-negative integer")
                source_window_present = not _blank(source.get("usage_window"))
                has_effective_window = (
                    _valid_window(source.get("usage_window")) if source_window_present else has_valid_shared_window
                )
                if has_usage_count and not has_effective_window:
                    _metadata_problem(concept, result, profile, f"{label}.usage_count requires a shared or source usage_window")
                if not _blank(source.get("last_modified")) and _parse_okf_timestamp(source["last_modified"]) is None:
                    _metadata_problem(concept, result, profile, f"{label}.last_modified must be {TIMESTAMP_RULE}")
                if source_window_present:
                    _validate_usage_window(concept, source["usage_window"], result, profile, f"{label}.usage_window")
    if _normalized_type(metadata.get("type")) == "attested computation":
        _validate_attested_computation(concept, bundle_root, result, profile, strict_links, declared_version)

    masked_body = mask_markdown_code(concept.body)
    body_without_definitions = re.sub(
        r"^ {0,3}\[\^[^\]\n]+\]:.*$", "", masked_body, flags=re.MULTILINE
    )
    footnote_references = _footnote_references(body_without_definitions)
    footnote_definitions = set(FOOTNOTE_DEFINITION_RE.findall(masked_body))
    for source_id in footnote_references:
        if source_id not in source_ids:
            _metadata_problem(
                concept,
                result,
                profile,
                f"footnote source '{source_id}' is missing from sources[].id",
            )
        if source_id not in footnote_definitions:
            _metadata_problem(
                concept, result, profile, f"footnote '{source_id}' is missing its Markdown definition"
            )


def _index_reachable_concepts(bundle_root: Path, index_paths: list[Path]) -> set[Path]:
    known_indexes = {path.resolve(strict=False) for path in index_paths}
    root_index = (bundle_root / "index.md").resolve(strict=False)
    pending = [root_index] if root_index in known_indexes else []
    visited_indexes: set[Path] = set()
    concepts: set[Path] = set()
    while pending:
        index_path = pending.pop()
        if index_path in visited_indexes:
            continue
        visited_indexes.add(index_path)
        try:
            _, body = split_frontmatter(index_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        for target in extract_markdown_link_targets(body):
            candidate, problem = _local_candidate(index_path, bundle_root, target)
            if candidate is None or problem:
                continue
            if candidate.is_dir():
                candidate = (candidate / "index.md").resolve(strict=False)
            if candidate in known_indexes:
                pending.append(candidate)
            elif (
                candidate.is_relative_to(bundle_root.resolve(strict=False))
                and candidate.suffix.casefold() == ".md"
                and candidate.name not in RESERVED_NAMES
            ):
                concepts.add(candidate)
    return concepts


def validate_doc_sync_profile(
    bundle_root: Path,
    concepts: list[ConceptDocument],
    index_paths: list[Path],
    root_index_metadata: dict[str, Any] | None,
    result: ValidationResult,
) -> None:
    for reserved_name in ("index.md", "log.md"):
        if not (bundle_root / reserved_name).is_file():
            result.errors.append(f"{bundle_root}: DocSync profile requires root {reserved_name}")
    version = root_index_metadata.get("okf_version") if root_index_metadata else None
    version = version.strip() if isinstance(version, str) else None
    if version != CURRENT_OKF_VERSION:
        notice = f"; {_version_notice(version)}" if version else ""
        result.errors.append(
            f'{bundle_root}: DocSync profile requires root okf_version: "{CURRENT_OKF_VERSION}"{notice}'
        )

    for concept in concepts:
        for field_name in ("title", "description"):
            value = concept.metadata.get(field_name)
            if not isinstance(value, str) or not value.strip():
                result.errors.append(
                    f"{concept.path}: DocSync profile requires a non-empty string '{field_name}'"
                )
        description = concept.metadata.get("description")
        if isinstance(description, str) and "\n" in description:
            result.errors.append(f"{concept.path}: DocSync profile description must be one line")
        validate_concept_metadata(
            concept, bundle_root, result, profile=True, strict_links=True, declared_version=version
        )

    has_coverage_manifest = any(
        _normalized_type(concept.metadata.get("type")) == "coverage manifest"
        for concept in concepts
    )
    if not has_coverage_manifest:
        result.errors.append(
            f"{bundle_root}: DocSync profile requires a concept with type 'Coverage Manifest'"
        )

    reachable = _index_reachable_concepts(bundle_root, index_paths)
    for concept in concepts:
        if concept.path.resolve(strict=False) not in reachable:
            result.errors.append(
                f"{concept.path}: DocSync profile requires every concept to be reachable from root index navigation"
            )


def validate_bundle(
    bundle_root: Path,
    strict_links: bool = False,
    doc_sync_profile: bool = False,
    require_doc_sync_spine: bool = False,
) -> ValidationResult:
    result = ValidationResult()
    if not bundle_root.is_dir():
        result.errors.append(f"{bundle_root}: bundle directory does not exist")
        return result
    declared_version = read_declared_version(bundle_root)
    resolved_root = bundle_root.resolve(strict=False)
    # Section 3.2: dot-paths and files outside the bundle root are not part of the bundle.
    markdown_files = [
        path
        for path in sorted(bundle_root.rglob("*.md"))
        if not any(part.startswith(".") for part in path.relative_to(bundle_root).parts)
        and path.resolve(strict=False).is_relative_to(resolved_root)
    ]
    if not markdown_files:
        result.errors.append(f"{bundle_root}: bundle contains no Markdown files")
        return result

    profile_enabled = doc_sync_profile or require_doc_sync_spine
    concepts: list[ConceptDocument] = []
    index_paths: list[Path] = []
    root_index_metadata: dict[str, Any] | None = None
    for path in markdown_files:
        if path.name == "index.md":
            index_paths.append(path)
            metadata = validate_index(path, bundle_root, result, profile_enabled)
            if path.parent == bundle_root:
                root_index_metadata = metadata
        elif path.name == "log.md":
            validate_log(path, result)
        else:
            concept = validate_concept(path, result, profile_enabled)
            if concept is not None:
                concepts.append(concept)
        validate_links(path, bundle_root, result, strict_links or profile_enabled)
    if profile_enabled:
        validate_doc_sync_profile(bundle_root, concepts, index_paths, root_index_metadata, result)
    else:
        for concept in concepts:
            validate_concept_metadata(
                concept, bundle_root, result, profile=False, strict_links=strict_links,
                declared_version=declared_version,
            )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="path to the OKF bundle root")
    parser.add_argument(
        "--strict-links",
        action="store_true",
        help="treat broken local links as producer errors instead of consumer warnings",
    )
    parser.add_argument(
        "--doc-sync-profile",
        action="store_true",
        help=f"apply the stricter DocSync OKF v{CURRENT_OKF_VERSION} producer completion profile",
    )
    parser.add_argument(
        "--require-doc-sync-spine",
        action="store_true",
        help="deprecated compatibility alias for --doc-sync-profile",
    )
    args = parser.parse_args(argv)
    result = validate_bundle(
        args.bundle.resolve(),
        strict_links=args.strict_links,
        doc_sync_profile=args.doc_sync_profile,
        require_doc_sync_spine=args.require_doc_sync_spine,
    )
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if result.ok:
        print(f"OKF validation passed: {args.bundle}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
