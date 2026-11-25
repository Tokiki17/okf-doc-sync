#!/usr/bin/env python3
"""Validate the DocSync engineering repository."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "doc-sync"
DOCS_VALIDATOR = SKILL_ROOT / "scripts" / "validate_docs.py"
MIN_PYTHON = (3, 10)

REQUIRED_FILES = [
    ".github/workflows/ci.yml",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "docs/architecture.md",
    "docs/host-compatibility.md",
    "docs/index.md",
    "docs/maintenance.md",
    "pyproject.toml",
    "scripts/install.py",
    "skills/doc-sync/SKILL.md",
    "skills/doc-sync/agents/openai.yaml",
    "skills/doc-sync/references/doc-maintenance.md",
    "skills/doc-sync/scripts/validate_docs.py",
]


def load_docs_validator():
    spec = importlib.util.spec_from_file_location("validate_docs", DOCS_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the documentation validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def python_files(root: Path) -> list[Path]:
    validator = load_docs_validator()
    return [path for path in validator.list_project_files(root) if path.suffix == ".py"]


def python_compat_errors(root: Path | None = None) -> list[str]:
    """Require Python 3.10 syntax and standard-library-only imports."""
    root = root or REPO_ROOT
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    errors: list[str] = []
    for path in python_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative, feature_version=MIN_PYTHON)
        except SyntaxError as exc:
            errors.append(f"{relative}:{exc.lineno}: not valid Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} syntax: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top not in allowed:
                    errors.append(f"{relative}:{node.lineno}: imports non-standard-library module '{top}'")
    return errors


def git_diff_errors() -> list[str]:
    errors: list[str] = []
    for command in (["git", "diff", "--check"], ["git", "diff", "--cached", "--check"]):
        completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        if completed.returncode:
            message = completed.stdout.strip() or completed.stderr.strip()
            if message and message not in errors:
                errors.append(message)
    return errors


def main() -> int:
    errors = [f"missing required file: {path}" for path in REQUIRED_FILES if not (REPO_ROOT / path).is_file()]
    if (REPO_ROOT / "CLAUDE.md").exists():
        errors.append("CLAUDE.md is not part of the approved project contract; shared rules live in AGENTS.md")
    warnings: list[str] = []
    if not errors:
        validator = load_docs_validator()
        errors.extend(f"skills/doc-sync: {error}" for error in validator.validate_skill_tree(SKILL_ROOT, "doc-sync"))
        report = validator.validate_project(REPO_ROOT, strict=True, check_private_paths=True)
        errors.extend(report.errors)
        warnings.extend(report.warnings)
        errors.extend(python_compat_errors())
    if (REPO_ROOT / ".git").exists():
        errors.extend(git_diff_errors())
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
