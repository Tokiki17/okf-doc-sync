from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install.py"


def load_installer_module():
    spec = importlib.util.spec_from_file_location("docsync_installer", INSTALLER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load installer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InstallTests(unittest.TestCase):
    def run_installer(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(INSTALLER), *args],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_first_install_idempotence_and_check(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doc sync ") as temp_dir:
            target = Path(temp_dir) / "skills" / "doc-sync"
            first = self.run_installer("--target", str(target))
            second = self.run_installer("--target", str(target))
            check = self.run_installer("--target", str(target), "--check")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertFalse(any(target.rglob("__pycache__")))
            self.assertFalse(any(target.rglob("*.pyc")))

    def test_drift_requires_force_and_force_keeps_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "skills" / "doc-sync"
            self.assertEqual(self.run_installer("--target", str(target)).returncode, 0)
            skill = target / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\nlocal drift\n", encoding="utf-8")
            refused = self.run_installer("--target", str(target))
            forced = self.run_installer("--target", str(target), "--force")
            check = self.run_installer("--target", str(target), "--check")
            self.assertEqual(refused.returncode, 3)
            self.assertIn("target diverges", refused.stderr)
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertTrue((target.parent.parent / ".doc-sync-install" / "backup" / "SKILL.md").is_file())

    def test_skills_root_keeps_only_the_installed_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "skills" / "doc-sync"
            legacy = target.parent / ".doc-sync-backup"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").write_text("old copy", encoding="utf-8")
            completed = self.run_installer("--target", str(target), "--force")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual([path.name for path in target.parent.iterdir()], ["doc-sync"])
            retired = target.parent.parent / ".doc-sync-install" / "legacy-backup" / "SKILL.md"
            self.assertEqual(retired.read_text(encoding="utf-8"), "old copy")

    def test_extra_and_missing_files_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "skills" / "doc-sync"
            self.assertEqual(self.run_installer("--target", str(target)).returncode, 0)
            (target / "extra.txt").write_text("extra", encoding="utf-8")
            (target / "agents" / "openai.yaml").unlink()
            check = self.run_installer("--target", str(target), "--check")
            self.assertEqual(check.returncode, 1)
            self.assertIn("extra in target", check.stderr)
            self.assertIn("missing from target", check.stderr)

    def test_codex_home_changes_default_target_without_touching_other_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir) / "Codex Home"
            other = codex_home / "skills" / "other-skill" / "SKILL.md"
            other.parent.mkdir(parents=True)
            other.write_text("keep me", encoding="utf-8")
            env = os.environ.copy()
            env["CODEX_HOME"] = str(codex_home)
            completed = self.run_installer(env=env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((codex_home / "skills" / "doc-sync" / "SKILL.md").is_file())
            self.assertEqual(other.read_text(encoding="utf-8"), "keep me")

    def test_claude_host_uses_claude_config_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            claude_home = Path(temp_dir) / "Claude Home"
            codex_home = Path(temp_dir) / "Codex Home"
            env = os.environ.copy()
            env["CLAUDE_CONFIG_DIR"] = str(claude_home)
            env["CODEX_HOME"] = str(codex_home)
            completed = self.run_installer("--host", "claude", env=env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((claude_home / "skills" / "doc-sync" / "SKILL.md").is_file())
            self.assertFalse(codex_home.exists())
            check = self.run_installer("--host", "claude", "--check", env=env)
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_agents_host_targets_shared_user_skills_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["HOME"] = temp_dir
            completed = self.run_installer("--host", "agents", "--dry-run", env=env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(str(Path(temp_dir) / ".agents" / "skills" / "doc-sync"), completed.stdout)
            self.assertFalse((Path(temp_dir) / ".agents").exists())

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "skills" / "doc-sync"
            completed = self.run_installer("--target", str(target), "--dry-run")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(target.exists())

    def test_symlink_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            actual = root / "actual"
            actual.mkdir()
            target = root / "doc-sync"
            target.symlink_to(actual, target_is_directory=True)
            completed = self.run_installer("--target", str(target), "--force")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("symlink target", completed.stderr)

    def test_failed_post_install_verification_restores_previous_target(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            target = root / "skills" / "doc-sync"
            source.mkdir()
            target.mkdir(parents=True)
            (source / "SKILL.md").write_text("new", encoding="utf-8")
            (target / "SKILL.md").write_text("old", encoding="utf-8")
            with mock.patch.object(installer, "compare_trees", side_effect=[[], ["failed"]]):
                with self.assertRaises(RuntimeError):
                    installer.install(source, target)
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "old")

    def test_staging_failure_preserves_existing_installation_and_backup(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            target = root / "skills" / "doc-sync"
            backup = target.parent.parent / ".doc-sync-install" / "backup"
            source.mkdir()
            target.mkdir(parents=True)
            backup.mkdir(parents=True)
            (source / "SKILL.md").write_text("new", encoding="utf-8")
            (target / "SKILL.md").write_text("old", encoding="utf-8")
            (backup / "SKILL.md").write_text("previous backup", encoding="utf-8")
            with mock.patch.object(installer.shutil, "copytree", side_effect=OSError("copy failed")):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    installer.install(source, target)
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "old")
            self.assertEqual((backup / "SKILL.md").read_text(encoding="utf-8"), "previous backup")
            self.assertFalse(list((target.parent.parent / ".doc-sync-install").glob("staging-*")))

    def test_source_validation_rejects_malformed_skill_yaml(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "doc-sync"
            shutil.copytree(REPO_ROOT / "skills" / "doc-sync", source)
            (source / "SKILL.md").write_text(
                "---\nname: doc-sync\ndescription: broken: yaml\n---\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid YAML frontmatter"):
                installer.validate_source(source)

    def test_source_validation_rejects_malformed_agent_yaml(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "doc-sync"
            shutil.copytree(REPO_ROOT / "skills" / "doc-sync", source)
            (source / "agents" / "openai.yaml").write_text(
                "interface:\n  display_name: [broken\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid YAML"):
                installer.validate_source(source)

    def test_source_validation_accepts_reversed_skill_frontmatter_order(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "doc-sync"
            shutil.copytree(REPO_ROOT / "skills" / "doc-sync", source)
            skill_path = source / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            _, body = text.split("---\n", 2)[1:]
            description = next(
                line.removeprefix("description: ")
                for line in text.splitlines()
                if line.startswith("description: ")
            )
            skill_path.write_text(
                f"---\ndescription: {description}\nname: doc-sync\n---\n{body}",
                encoding="utf-8",
            )
            installer.validate_source(source)


if __name__ == "__main__":
    unittest.main()
