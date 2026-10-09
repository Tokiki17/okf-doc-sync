#!/usr/bin/env python3
"""Install or compare the canonical doc-sync skill tree."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "skills" / "doc-sync"
IGNORED_NAMES = {".DS_Store", "__pycache__"}


HOST_HOMES = {
    "codex": ("CODEX_HOME", ".codex"),
    "claude": ("CLAUDE_CONFIG_DIR", ".claude"),
    "agents": (None, ".agents"),
}


def default_target(host: str = "codex") -> Path:
    env_name, home_name = HOST_HOMES[host]
    configured = os.environ.get(env_name) if env_name else None
    base = Path(configured).expanduser() if configured else Path.home() / home_name
    return base / "skills" / "doc-sync"


def file_record(path: Path) -> tuple[str, bool]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    executable = bool(path.stat().st_mode & 0o111)
    return digest, executable


def tree_records(root: Path) -> dict[str, tuple[str, bool]]:
    records: dict[str, tuple[str, bool]] = {}
    if not root.exists():
        return records
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_NAMES for part in path.relative_to(root).parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"symlinks are not supported in managed skill trees: {path}")
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
    validator_path = source / "scripts" / "validate_okf.py"
    spec = importlib.util.spec_from_file_location("doc_sync_source_validator", validator_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load source validator: {validator_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_source(source: Path) -> None:
    required = [
        source / "SKILL.md",
        source / "agents" / "openai.yaml",
        source / "scripts" / "validate_okf.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"canonical source is incomplete: {', '.join(missing)}")
    validator = load_source_validator(source)
    skill_text = (source / "SKILL.md").read_text(encoding="utf-8")
    try:
        header, _ = validator.split_frontmatter(skill_text)
        metadata = validator.parse_yaml(header) if header is not None else None
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"canonical SKILL.md has invalid YAML frontmatter: {exc}") from exc
    if (
        not isinstance(metadata, dict)
        or set(metadata) != {"name", "description"}
        or metadata.get("name") != "doc-sync"
        or not isinstance(metadata.get("description"), str)
        or not metadata["description"].strip()
    ):
        raise ValueError("canonical SKILL.md has invalid or mismatched frontmatter")
    if "TODO" in skill_text:
        raise ValueError("canonical SKILL.md contains unresolved TODO text")
    try:
        agent_metadata = validator.parse_yaml(
            (source / "agents" / "openai.yaml").read_text(encoding="utf-8")
        )
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"canonical agents/openai.yaml has invalid YAML: {exc}") from exc
    interface = agent_metadata.get("interface") if isinstance(agent_metadata, dict) else None
    policy = agent_metadata.get("policy") if isinstance(agent_metadata, dict) else None
    short_description = interface.get("short_description") if isinstance(interface, dict) else None
    if (
        not isinstance(interface, dict)
        or any(
            not isinstance(interface.get(key), str) or not interface[key].strip()
            for key in ("display_name", "short_description", "default_prompt")
        )
        or "$doc-sync" not in interface["default_prompt"]
        or not isinstance(short_description, str)
        or not 25 <= len(short_description.strip()) <= 64
        or not isinstance(policy, dict)
        or policy.get("allow_implicit_invocation") is not True
    ):
        raise ValueError("canonical agents/openai.yaml has invalid metadata")
    if not tree_records(source):
        raise ValueError("canonical source tree is empty")


def work_root(target: Path) -> Path:
    # Hosts discover every directory containing SKILL.md under a skills root,
    # so staging and rollback copies live beside that root, never inside it.
    return target.parent.parent / ".doc-sync-install"


def backup_path(target: Path) -> Path:
    return work_root(target) / "backup"


def retire_legacy_backup(target: Path) -> None:
    legacy = target.parent / ".doc-sync-backup"
    if not legacy.is_dir() or legacy.is_symlink():
        return
    retired = work_root(target) / "legacy-backup"
    if retired.exists():
        shutil.rmtree(retired)
    legacy.rename(retired)


def install(source: Path, target: Path) -> None:
    if target.is_symlink():
        raise ValueError(f"refusing to replace symlink target: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    work_root(target).mkdir(parents=True, exist_ok=True)
    backup = backup_path(target)
    temp_parent = Path(tempfile.mkdtemp(prefix="staging-", dir=work_root(target)))
    staged = temp_parent / "doc-sync"
    moved_old = False
    installed_new = False
    try:
        shutil.copytree(
            source,
            staged,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"),
        )
        if compare_trees(source, staged):
            raise RuntimeError("staged skill failed parity verification")
        if backup.exists():
            if backup.is_dir() and not backup.is_symlink():
                shutil.rmtree(backup)
            else:
                backup.unlink()
        if target.exists():
            target.rename(backup)
            moved_old = True
        staged.rename(target)
        installed_new = True
        if compare_trees(source, target):
            raise RuntimeError("installed skill failed parity verification")
        retire_legacy_backup(target)
    except Exception:
        if installed_new and target.exists():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        if moved_old and backup.exists() and not target.exists():
            backup.rename(target)
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
    target = (args.target or default_target(args.host)).expanduser().absolute()
    try:
        if target.is_symlink():
            raise ValueError(f"refusing to manage symlink target: {target}")
        validate_source(SOURCE)
        differences = compare_trees(SOURCE, target)
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
        if not args.dry_run:
            work_root(target).mkdir(parents=True, exist_ok=True)
            retire_legacy_backup(target)
        print(f"Installed skill is already current: {target}")
        return 0

    action = "install" if not target.exists() else "replace divergent installation"
    if args.dry_run:
        print(f"Would {action}: {target}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
