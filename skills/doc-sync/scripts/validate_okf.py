#!/usr/bin/env python3
"""Validate OKF v0.1/v0.2 bundles and the stricter DocSync producer profile."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


FRONTMATTER_DELIMITER = "---"
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
REFERENCE_DEFINITION_RE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$")
FOOTNOTE_DEFINITION_RE = re.compile(r"^ {0,3}\[\^([^\]\n]+)\]:", re.MULTILINE)
FOOTNOTE_REFERENCE_RE = re.compile(r"(?<!\[)\[\^([^\]\n]+)\]")
RESERVED_NAMES = {"index.md", "log.md"}
SUPPORTED_OKF_VERSIONS = {"0.1", "0.2"}
LEGACY_OKF_VERSION = "0.1"
CURRENT_OKF_VERSION = "0.2"


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


def validate_concept(path: Path, result: ValidationResult) -> ConceptDocument | None:
    try:
        header, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        result.errors.append(f"{path}: {exc}")
        return None
    if header is None:
        result.errors.append(f"{path}: concept is missing YAML frontmatter")
        return None
    try:
        metadata = parse_yaml(header)
    except (RuntimeError, ValueError) as exc:
        result.errors.append(f"{path}: invalid YAML frontmatter: {exc}")
        return None
    if not isinstance(metadata, dict):
        result.errors.append(f"{path}: frontmatter must be a YAML mapping")
        return None
    concept_type = metadata.get("type")
    if not isinstance(concept_type, str) or not concept_type.strip():
        result.errors.append(f"{path}: frontmatter requires a non-empty string 'type'")
        return None
    return ConceptDocument(path=path, metadata=metadata, frontmatter=header, body=body)


def validate_index(
    path: Path,
    bundle_root: Path,
    result: ValidationResult,
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
        try:
            parsed = parse_yaml(header)
        except (RuntimeError, ValueError) as exc:
            result.errors.append(f"{path}: invalid root index frontmatter: {exc}")
            parsed = None
        if not isinstance(parsed, dict):
            result.errors.append(f"{path}: root index frontmatter must be a YAML mapping")
        elif (
            set(parsed) != {"okf_version"}
            or not isinstance(parsed["okf_version"], str)
            or not parsed["okf_version"].strip()
        ):
            result.errors.append(
                f"{path}: root index frontmatter may contain only a non-empty okf_version"
            )
        else:
            metadata = parsed
            version = parsed["okf_version"].strip()
            if version not in SUPPORTED_OKF_VERSIONS:
                result.warnings.append(
                    f"{path}: unknown OKF version '{version}'; attempting best-effort validation"
                )
    if not re.search(r"^#\s+\S", body, re.MULTILINE):
        result.errors.append(f"{path}: index.md requires at least one Markdown heading")
    if not extract_markdown_link_targets(body):
        result.errors.append(f"{path}: index.md requires at least one Markdown link entry")
    return metadata


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


def _valid_timezone_timestamp(value: Any) -> bool:
    return _parse_timezone_timestamp(value) is not None


def _parse_timezone_timestamp(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None and value.utcoffset() is not None else None
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _valid_legacy_timestamp(value: Any, frontmatter: str) -> bool:
    match = re.search(r"^timestamp:[ \t]*(.+?)[ \t]*$", frontmatter, re.MULTILINE)
    if not match:
        return False
    candidate = match.group(1).strip().strip("\"'")
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


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
        if field_name not in value:
            _metadata_problem(concept, result, profile, f"{label}.{field_name} is required")
            continue
        parsed = _parse_timezone_timestamp(value[field_name])
        if parsed is None:
            _metadata_problem(
                concept,
                result,
                profile,
                f"{label}.{field_name} must be a timezone-aware ISO 8601 timestamp",
            )
        else:
            timestamps[field_name] = parsed
    if len(timestamps) == 2 and timestamps["from"] > timestamps["to"]:
        _metadata_problem(concept, result, profile, f"{label}.from must not be after {label}.to")


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
    if not _non_empty_string(value):
        return False
    actor = value.strip()
    if actor.startswith(("human:", "process:")):
        return bool(actor.split(":", 1)[1].strip())
    if "/" not in actor:
        return False
    producer, version = actor.split("/", 1)
    return bool(producer.strip() and version.strip())


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


def _validate_source_links(
    concept: ConceptDocument,
    bundle_root: Path,
    result: ValidationResult,
    strict_links: bool,
) -> None:
    sources = concept.metadata.get("sources")
    if not isinstance(sources, list):
        return
    for source in sources:
        if not isinstance(source, dict):
            continue
        resource = source.get("resource")
        if not isinstance(resource, str):
            continue
        try:
            if not _looks_like_local_path(resource):
                continue
            candidate, problem = _local_candidate(concept.path, bundle_root, resource)
        except ValueError as exc:
            _metadata_problem(
                concept, result, strict_links, f"invalid source resource '{resource}': {exc}"
            )
            continue
        if candidate is None:
            continue
        if problem == "escapes":
            message = f"{concept.path}: local link escapes the bundle '{resource}'"
        elif candidate.exists():
            continue
        else:
            message = f"{concept.path}: broken local link '{resource}'"
        if strict_links:
            result.errors.append(message)
        else:
            result.warnings.append(message)


def validate_v02_metadata(
    concept: ConceptDocument,
    bundle_root: Path,
    result: ValidationResult,
    profile: bool,
    strict_links: bool,
) -> None:
    metadata = concept.metadata
    generated = metadata.get("generated")
    if "generated" in metadata:
        if not isinstance(generated, dict):
            _metadata_problem(concept, result, profile, "generated must be a mapping")
        else:
            if not _non_empty_string(generated.get("by")):
                _metadata_problem(concept, result, profile, "generated.by must be a non-empty string")
            elif not _valid_actor(generated["by"]):
                _metadata_problem(concept, result, profile, "generated.by must follow the OKF actor convention")
            if "at" in generated and not _valid_timezone_timestamp(generated["at"]):
                _metadata_problem(concept, result, profile, "generated.at must be a timezone-aware ISO 8601 timestamp")
    elif profile:
        result.errors.append(f"{concept.path}: DocSync profile requires generated.by and generated.at")
    if profile and isinstance(generated, dict) and not _valid_timezone_timestamp(generated.get("at")):
        result.errors.append(f"{concept.path}: DocSync profile requires generated.at to be a timezone-aware ISO 8601 timestamp")

    verified = metadata.get("verified")
    if "verified" in metadata:
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
                if not _valid_timezone_timestamp(event.get("at")):
                    _metadata_problem(concept, result, profile, f"{label}.at must be a timezone-aware ISO 8601 timestamp")

    if "status" in metadata and (
        not isinstance(metadata["status"], str)
        or metadata["status"] not in {"draft", "stable", "deprecated"}
    ):
        _metadata_problem(concept, result, profile, "status must be draft, stable, or deprecated")
    if "stale_after" in metadata and not _valid_timezone_timestamp(metadata["stale_after"]):
        _metadata_problem(concept, result, profile, "stale_after must be a timezone-aware ISO 8601 timestamp")
    if "usage_window" in metadata:
        _validate_usage_window(concept, metadata["usage_window"], result, profile, "usage_window")

    sources = metadata.get("sources")
    source_ids: set[str] = set()
    shared_usage_window = metadata.get("usage_window")
    has_valid_shared_window = isinstance(shared_usage_window, dict) and all(
        _valid_timezone_timestamp(shared_usage_window.get(field_name))
        for field_name in ("from", "to")
    )
    if "sources" in metadata:
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
                for field_name in ("id", "title", "author"):
                    if field_name in source and not _non_empty_string(source[field_name]):
                        _metadata_problem(concept, result, profile, f"{label}.{field_name} must be a non-empty string")
                if _non_empty_string(source.get("id")):
                    source_id = source["id"].strip()
                    if source_id in source_ids:
                        _metadata_problem(concept, result, profile, f"duplicate sources[].id '{source_id}'")
                    source_ids.add(source_id)
                if "usage_count" in source and (isinstance(source["usage_count"], bool) or not isinstance(source["usage_count"], int) or source["usage_count"] < 0):
                    _metadata_problem(concept, result, profile, f"{label}.usage_count must be a non-negative integer")
                has_valid_source_window = isinstance(source.get("usage_window"), dict) and all(
                    _valid_timezone_timestamp(source["usage_window"].get(field_name))
                    for field_name in ("from", "to")
                )
                has_effective_window = (
                    has_valid_source_window if "usage_window" in source else has_valid_shared_window
                )
                if "usage_count" in source and not has_effective_window:
                    _metadata_problem(concept, result, profile, f"{label}.usage_count requires a shared or source usage_window")
                if "last_modified" in source and not _valid_timezone_timestamp(source["last_modified"]):
                    _metadata_problem(concept, result, profile, f"{label}.last_modified must be a timezone-aware ISO 8601 timestamp")
                if "usage_window" in source:
                    _validate_usage_window(concept, source["usage_window"], result, profile, f"{label}.usage_window")
        _validate_source_links(concept, bundle_root, result, strict_links)
    if _normalized_type(metadata.get("type")) == "attested computation" and not _non_empty_string(metadata.get("runtime")):
        _metadata_problem(concept, result, profile, "Attested Computation runtime must be a non-empty string")

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


def _external_target(target: str) -> bool:
    parsed = urlsplit(target)
    return bool(parsed.scheme or parsed.netloc)


def _validate_citations(concept: ConceptDocument, result: ValidationResult) -> None:
    masked = mask_markdown_code(concept.body)
    reference_definitions, _ = _reference_definitions(masked)
    headings = list(H1_RE.finditer(masked))
    citation_headings = [match for match in headings if match.group(1).strip().casefold() == "citations"]
    resource = concept.metadata.get("resource")
    resource_required = isinstance(resource, str) and bool(resource.strip())
    external_before = [
        target for target in extract_markdown_link_targets(concept.body) if _external_target(target)
    ]
    if not citation_headings:
        if resource_required or external_before:
            result.errors.append(f"{concept.path}: DocSync profile requires a final # Citations section")
        return
    if len(citation_headings) > 1:
        result.errors.append(f"{concept.path}: DocSync profile allows only one # Citations section")
        return
    heading = citation_headings[0]
    if headings[-1].start() != heading.start():
        result.errors.append(f"{concept.path}: # Citations must be the final level-one section")
    before = concept.body[: heading.start()]
    section = concept.body[heading.end() :]
    entries: list[tuple[int, str]] = []
    for line in section.splitlines():
        match = re.match(r"^\s*\[(\d+)\]\s+(.+?)\s*$", line)
        if match:
            targets = extract_markdown_link_targets(
                match.group(2),
                reference_definitions=reference_definitions,
            )
            if not targets:
                result.errors.append(f"{concept.path}: citation [{match.group(1)}] requires a link")
            else:
                entries.append((int(match.group(1)), targets[0]))
    if not entries:
        result.errors.append(f"{concept.path}: # Citations must contain numbered link entries")
        return
    numbers = [number for number, _ in entries]
    if numbers != list(range(1, len(entries) + 1)):
        result.errors.append(f"{concept.path}: citation numbers must be consecutive from [1]")
    citation_targets = [target for _, target in entries]
    if resource_required and citation_targets[0] != resource.strip():
        result.errors.append(f"{concept.path}: citation [1] must match frontmatter resource")
    for target in extract_markdown_link_targets(before):
        if _external_target(target) and target not in citation_targets:
            result.errors.append(f"{concept.path}: external link is missing from # Citations: {target}")


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
    if version not in SUPPORTED_OKF_VERSIONS:
        result.errors.append(
            f'{bundle_root}: DocSync profile requires root okf_version: "{LEGACY_OKF_VERSION}" or "{CURRENT_OKF_VERSION}"'
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
        if version == LEGACY_OKF_VERSION:
            if not _valid_legacy_timestamp(concept.metadata.get("timestamp"), concept.frontmatter):
                result.errors.append(
                    f"{concept.path}: DocSync profile requires a timezone-aware ISO 8601 timestamp"
                )
            _validate_citations(concept, result)
        elif version == CURRENT_OKF_VERSION:
            validate_v02_metadata(concept, bundle_root, result, profile=True, strict_links=True)

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
    markdown_files = sorted(bundle_root.rglob("*.md"))
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
            metadata = validate_index(path, bundle_root, result)
            if path.parent == bundle_root:
                root_index_metadata = metadata
        elif path.name == "log.md":
            validate_log(path, result)
        else:
            concept = validate_concept(path, result)
            if concept is not None:
                concepts.append(concept)
        validate_links(path, bundle_root, result, strict_links or profile_enabled)
    version = root_index_metadata.get("okf_version") if root_index_metadata else None
    if version == CURRENT_OKF_VERSION and not profile_enabled:
        for concept in concepts:
            validate_v02_metadata(
                concept,
                bundle_root,
                result,
                profile=profile_enabled,
                strict_links=strict_links or profile_enabled,
            )
    if profile_enabled:
        validate_doc_sync_profile(
            bundle_root,
            concepts,
            index_paths,
            root_index_metadata,
            result,
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
        help="apply the stricter DocSync v0.1/v0.2 producer completion profile",
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
