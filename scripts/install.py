#!/usr/bin/env python3
"""Install or compare the canonical doc-sync skill tree."""

from __future__ import annotations

import argparse
import errno
import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

# --check must not write anything, including bytecode for the loaded validator.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "skills" / "doc-sync"
SKILL_NAME = "doc-sync"
IGNORED_NAMES = {".DS_Store", "__pycache__"}
REQUIRED_FILES = ("SKILL.md", "agents/openai.yaml", "scripts/validate_docs.py")


HOST_HOMES = {
    "codex": ("CODEX_HOME", ".codex"),
    "claude": ("CLAUDE_CONFIG_DIR", ".claude"),
    "agents": (None, ".agents"),
}


def default_target(host: str = "codex") -> Path:
    env_name, home_name = HOST_HOMES[host]
    configured = os.environ.get(env_name) if env_name else None
    base = Path(configured).expanduser() if configured else Path.home() / home_name
    return base / "skills" / SKILL_NAME


def file_record(path: Path) -> tuple[str, bool]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    executable = bool(path.stat().st_mode & 0o111)
    return digest, executable


class SymlinkInTreeError(ValueError):
    """A managed skill tree contains a symlink, which installs never create."""


def tree_records(root: Path) -> dict[str, tuple[str, bool]]:
    records: dict[str, tuple[str, bool]] = {}
    if not root.exists():
        return records
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_NAMES for part in path.relative_to(root).parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise SymlinkInTreeError(f"symlinks are not supported in managed skill trees: {path}")
        if path.is_file():
            records[path.relative_to(root).as_posix()] = file_record(path)
    return records


def compare_trees(source: Path, target: Path) -> list[str]:
    source_records = tree_records(source)
    target_records = tree_records(target)
    differences: list[str] = []
    for relative in sorted(source_records.keys() - target_records.keys()):
        differences.append(f"missing from target: {relative}")
    for relative in sorted(target_records.keys() - source_records.keys()):
        differences.append(f"extra in target: {relative}")
    for relative in sorted(source_records.keys() & target_records.keys()):
        if source_records[relative] != target_records[relative]:
            differences.append(f"changed in target: {relative}")
    return differences


def load_source_validator(source: Path):
    validator_path = source / "scripts" / "validate_docs.py"
    spec = importlib.util.spec_from_file_location("doc_sync_source_validator", validator_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load source validator: {validator_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_source(source: Path) -> None:
    missing = [name for name in REQUIRED_FILES if not (source / name).is_file()]
    if missing:
        raise ValueError(f"canonical source is incomplete: {', '.join(missing)}")
    errors = load_source_validator(source).validate_skill_tree(source, SKILL_NAME)
    if errors:
        raise ValueError("canonical skill is invalid: " + "; ".join(errors))
    if not tree_records(source):
        raise ValueError("canonical source tree is empty")


def user_cache_root() -> Path:
    if os.name == "nt":
        configured = os.environ.get("LOCALAPPDATA")
        base = Path(configured) if configured else Path.home() / "AppData" / "Local"
    else:
        configured = os.environ.get("XDG_CACHE_HOME")
        base = Path(configured) if configured else Path.home() / ".cache"
    return base / "doc-sync-install"


def _inside_repository(path: Path) -> bool:
    return any((candidate / ".git").exists() for candidate in (path, *path.parents))


def work_root(target: Path) -> Path:
    """Return the staging and backup directory, always outside the skills root.

    Hosts load every directory containing SKILL.md under a skills root, so work
    files never live there. A standard <base>/skills/doc-sync target keeps them in
    <base>/.doc-sync-install; a shallow target or one inside a repository uses the
    user cache so no project tree is touched.
    """
    # abspath folds ".." without following a symlinked final component.
    target = Path(os.path.abspath(target))
    skills = target.parent
    base = skills.parent
    if skills.name == "skills" and base != base.parent and not _inside_repository(base):
        return base / ".doc-sync-install"
    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:16]
    return user_cache_root() / digest


def backup_path(target: Path) -> Path:
    return work_root(target) / "backup"


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _copy_tree(source: Path, destination: Path) -> None:
    try:
        shutil.copytree(source, destination, symlinks=True)
    except BaseException:
        _remove(destination)
        raise


def _move_tree(source: Path, destination: Path) -> None:
    """Rename on one device; copy then delete across devices (EXDEV)."""
    try:
        os.rename(source, destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        _copy_tree(source, destination)
        shutil.rmtree(source)


def install(source: Path, target: Path) -> None:
    if target.is_symlink():
        raise ValueError(f"refusing to replace symlink target: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    work = work_root(target)
    work.mkdir(parents=True, exist_ok=True)
    backup = work / "backup"
    temp_parent = Path(tempfile.mkdtemp(prefix="staging-", dir=work))
    staged = temp_parent / SKILL_NAME
    had_target = target.exists()
    backed_up = False
    writing_target = False
    try:
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))
        if compare_trees(source, staged):
            raise RuntimeError("staged skill failed parity verification")
        _remove(backup)
        if had_target:
            try:
                os.rename(target, backup)
                backed_up = True
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                _copy_tree(target, backup)
                backed_up = True
                writing_target = True
                shutil.rmtree(target)
        # From here the target may be partially written; recovery must clean it.
        writing_target = True
        _move_tree(staged, target)
        if compare_trees(source, target):
            raise RuntimeError("installed skill failed parity verification")
    except BaseException:
        if writing_target:
            _remove(target)
            if backed_up:
                _move_tree(backup, target)
        raise
    finally:
        if temp_parent.exists():
            shutil.rmtree(temp_parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        choices=sorted(HOST_HOMES),
        default="codex",
        help="agent host whose user skills directory is the default target",
    )
    parser.add_argument("--target", type=Path, default=None, help="installed skill directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare without writing")
    mode.add_argument("--dry-run", action="store_true", help="report the planned action")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace a divergent existing installation after keeping a rollback backup",
    )
    args = parser.parse_args(argv)
    target = Path(os.path.abspath((args.target or default_target(args.host)).expanduser()))
    try:
        if target.is_symlink():
            raise ValueError(f"refusing to manage symlink target: {target}")
        validate_source(SOURCE)
        try:
            differences = compare_trees(SOURCE, target)
        except SymlinkInTreeError as exc:
            # validate_source already rejected source symlinks, so this one is in
            # the existing target: report it as a difference so --force can back
            # the target up and replace it.
            differences = [f"unsupported symlink in target: {exc}"]
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if not target.exists():
            print(f"ERROR: installed skill is missing: {target}", file=sys.stderr)
            return 1
        if differences:
            for difference in differences:
                print(f"DIFF: {difference}", file=sys.stderr)
            return 1
        print(f"Installed skill is current: {target}")
        return 0

    if not differences and target.exists():
        print(f"Installed skill is already current: {target}")
        return 0

    action = "install" if not target.exists() else "replace divergent installation"
    if args.dry_run:
        print(f"Would {action}: {target}")
        print(f"Work directory: {work_root(target)}")
        for difference in differences:
            print(f"DIFF: {difference}")
        return 0

    if target.exists() and differences and not args.force:
        for difference in differences:
            print(f"DIFF: {difference}", file=sys.stderr)
        print("ERROR: target diverges; review it and rerun with --force", file=sys.stderr)
        return 3
    try:
        install(SOURCE, target)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: installation failed: {exc}", file=sys.stderr)
        return 4
    print(f"Installed doc-sync skill: {target}")
    print(f"Rollback backup and staging: {work_root(target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
