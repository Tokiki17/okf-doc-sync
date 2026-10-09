#!/usr/bin/env python3
"""Validate the DocSync engineering repository."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "doc-sync"
OKF_VALIDATOR = SKILL_ROOT / "scripts" / "validate_okf.py"
IGNORED_MARKDOWN_DIRS = {".git", ".venv", "__pycache__"}
# Agent Skills specification and Anthropic authoring limits shared by all hosts.
MAX_DESCRIPTION_CHARS = 1024
MAX_SKILL_LINES = 500
# This repository is public: reject home-directory paths that identify a machine or user.
# The pattern is assembled so this file does not match itself.
HOME_PATH_PATTERN = re.compile(r"(?:/" + r"Users/|/" + r"home/)[A-Za-z0-9._-]+|[A-Za-z]:\\" + r"Users\\[A-Za-z0-9._-]+")
TEXT_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ""}


REQUIRED_FILES = [
    ".github/workflows/ci.yml",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "docs/architecture.md",
    "docs/index.md",
    "docs/maintenance.md",
    "docs/host-compatibility.md",
    "okf/index.md",
    "okf/log.md",
    "okf/concepts/governance/coverage-manifest.md",
    "scripts/install.py",
    "skills/doc-sync/SKILL.md",
    "skills/doc-sync/agents/openai.yaml",
    "skills/doc-sync/references/doc-maintenance.md",
    "skills/doc-sync/references/okf-v0.1.md",
    "skills/doc-sync/references/okf-v0.2.md",
    "skills/doc-sync/scripts/validate_okf.py",
]


def load_okf_validator():
    spec = importlib.util.spec_from_file_location("validate_okf", OKF_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load OKF validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def markdown_link_errors() -> list[str]:
    errors: list[str] = []
    okf_root = REPO_ROOT / "okf"
    validator = load_okf_validator()
    for path in sorted(REPO_ROOT.rglob("*.md")):
        relative_path = path.relative_to(REPO_ROOT)
        if any(part in IGNORED_MARKDOWN_DIRS for part in relative_path.parts):
            continue
        if path == okf_root or okf_root in path.parents:
            # The OKF validator below owns these links so a leading slash is
            # resolved from the bundle root under both supported OKF versions.
            continue
        text = path.read_text(encoding="utf-8")
        for target in validator.extract_markdown_link_targets(text):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#") or not parsed.path:
                continue
            decoded_path = unquote(parsed.path)
            candidate = (
                REPO_ROOT / decoded_path.lstrip("/")
                if decoded_path.startswith("/")
                else path.parent / decoded_path
            )
            if not candidate.exists():
                errors.append(f"{relative_path}: broken link '{target}'")
    return errors


def skill_errors() -> list[str]:
    errors: list[str] = []
    validator = load_okf_validator()
    skill_path = SKILL_ROOT / "SKILL.md"
    try:
        text = skill_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"SKILL.md is not valid UTF-8: {exc}"]
    if not text.startswith("---\n"):
        errors.append("SKILL.md must start with YAML frontmatter")
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not frontmatter_match:
        errors.append("SKILL.md frontmatter is not delimited correctly")
    else:
        try:
            frontmatter = validator.parse_yaml(frontmatter_match.group(1))
        except (RuntimeError, ValueError) as exc:
            errors.append(f"SKILL.md has invalid YAML frontmatter: {exc}")
            frontmatter = None
        if not isinstance(frontmatter, dict):
            errors.append("SKILL.md frontmatter must be a YAML mapping")
        else:
            if set(frontmatter) != {"name", "description"}:
                errors.append("SKILL.md frontmatter must contain only name and description")
            if frontmatter.get("name") != "doc-sync":
                errors.append("SKILL.md name must match the doc-sync directory")
            description = frontmatter.get("description")
            if not isinstance(description, str) or not description.strip():
                errors.append("SKILL.md description must be a non-empty string")
            elif len(description) > MAX_DESCRIPTION_CHARS:
                errors.append(f"SKILL.md description exceeds {MAX_DESCRIPTION_CHARS} characters")
            elif "<" in description or ">" in description:
                errors.append("SKILL.md description must not contain XML tags")
    if len(text.splitlines()) >= MAX_SKILL_LINES:
        errors.append(f"SKILL.md must stay under {MAX_SKILL_LINES} lines")
    lowered = text.lower()
    stale_phrases = ["okf support as an opt-in", "treat open knowledge format (okf) support as an opt-in"]
    for phrase in stale_phrases:
        if phrase in lowered:
            errors.append(f"SKILL.md contains retired opt-in wording: {phrase}")
    if "TODO" in text:
        errors.append("SKILL.md contains unresolved TODO text")
    metadata_path = SKILL_ROOT / "agents" / "openai.yaml"
    try:
        metadata_text = metadata_path.read_text(encoding="utf-8")
        metadata = validator.parse_yaml(metadata_text)
    except UnicodeDecodeError as exc:
        errors.append(f"agents/openai.yaml is not valid UTF-8: {exc}")
        metadata = None
    except (RuntimeError, ValueError) as exc:
        errors.append(f"agents/openai.yaml has invalid YAML: {exc}")
        metadata = None
    if not isinstance(metadata, dict):
        errors.append("agents/openai.yaml must be a YAML mapping")
    else:
        interface = metadata.get("interface")
        if not isinstance(interface, dict):
            errors.append("agents/openai.yaml requires an interface mapping")
        else:
            for required in ("display_name", "short_description", "default_prompt"):
                value = interface.get(required)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"agents/openai.yaml requires a non-empty interface.{required}")
            short_description = interface.get("short_description")
            if isinstance(short_description, str) and not 25 <= len(short_description.strip()) <= 64:
                errors.append("agents/openai.yaml short_description must contain 25-64 characters")
            default_prompt = interface.get("default_prompt")
            if isinstance(default_prompt, str) and "$doc-sync" not in default_prompt:
                errors.append("agents/openai.yaml default_prompt must invoke $doc-sync")
        policy = metadata.get("policy")
        if not isinstance(policy, dict) or policy.get("allow_implicit_invocation") is not True:
            errors.append("agents/openai.yaml must allow implicit invocation")
    return errors


def git_diff_errors() -> list[str]:
    errors: list[str] = []
    for command in (["git", "diff", "--check"], ["git", "diff", "--cached", "--check"]):
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            message = completed.stdout.strip() or completed.stderr.strip()
            if message and message not in errors:
                errors.append(message)
    return errors


def private_path_errors() -> list[str]:
    errors: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        relative_path = path.relative_to(REPO_ROOT)
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in IGNORED_MARKDOWN_DIRS or part.endswith(".egg-info") or part == "build" for part in relative_path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if HOME_PATH_PATTERN.search(line):
                errors.append(f"{relative_path}:{line_number}: machine-specific home path")
    return errors


def main() -> int:
    errors = [f"missing required file: {path}" for path in REQUIRED_FILES if not (REPO_ROOT / path).is_file()]
    if (REPO_ROOT / "CLAUDE.md").exists():
        errors.append("CLAUDE.md is not part of the approved project contract")
    if not errors:
        errors.extend(skill_errors())
        errors.extend(markdown_link_errors())
        errors.extend(private_path_errors())
        validator = load_okf_validator()
        result = validator.validate_bundle(
            REPO_ROOT / "okf",
            doc_sync_profile=True,
        )
        errors.extend(result.errors)
    git_dir = REPO_ROOT / ".git"
    if git_dir.exists():
        errors.extend(git_diff_errors())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
