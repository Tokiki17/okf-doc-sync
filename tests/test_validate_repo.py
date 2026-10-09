from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validate_repo.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_repo_under_test", VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load repository validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ValidateRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = load_validator_module()

    def test_non_okf_broken_link_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("[Missing](missing.md)\n", encoding="utf-8")
            with mock.patch.object(self.validator, "REPO_ROOT", root):
                self.assertEqual(
                    self.validator.markdown_link_errors(),
                    ["README.md: broken link 'missing.md'"],
                )

    def test_reference_style_and_parenthesized_links_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text(
                "[Missing][target]\n\n[target]: missing_(v2).md\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.validator, "REPO_ROOT", root):
                self.assertEqual(
                    self.validator.markdown_link_errors(),
                    ["README.md: broken link 'missing_(v2).md'"],
                )

    def test_okf_links_are_delegated_to_okf_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = root / "okf" / "concepts" / "thing.md"
            concept.parent.mkdir(parents=True)
            concept.write_text(
                "---\ntype: Reference\n---\n\n[Root index](/index.md)\n",
                encoding="utf-8",
            )
            (root / "okf" / "index.md").write_text("# Index\n", encoding="utf-8")
            with mock.patch.object(self.validator, "REPO_ROOT", root):
                self.assertEqual(self.validator.markdown_link_errors(), [])

    def test_ignored_environment_markdown_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            license_file = root / ".venv" / "package" / "LICENSE.md"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("[Dependency link](missing.md)\n", encoding="utf-8")
            with mock.patch.object(self.validator, "REPO_ROOT", root):
                self.assertEqual(self.validator.markdown_link_errors(), [])

    def write_skill_tree(self, root: Path) -> None:
        (root / "agents").mkdir(parents=True)
        (root / "SKILL.md").write_text(
            "---\nname: doc-sync\ndescription: Valid description\n---\n\n# Skill\n",
            encoding="utf-8",
        )
        (root / "agents" / "openai.yaml").write_text(
            "interface:\n"
            "  display_name: Doc Sync\n"
            "  short_description: Synchronize maintained project knowledge\n"
            "  default_prompt: Use $doc-sync now.\n"
            "policy:\n"
            "  allow_implicit_invocation: true\n",
            encoding="utf-8",
        )

    def test_malformed_skill_frontmatter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir)
            self.write_skill_tree(skill_root)
            (skill_root / "SKILL.md").write_text(
                "---\nname: doc-sync\ndescription: broken: yaml\n---\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.validator, "SKILL_ROOT", skill_root):
                errors = self.validator.skill_errors()
            self.assertTrue(any("invalid YAML frontmatter" in error for error in errors))

    def test_malformed_agent_metadata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir)
            self.write_skill_tree(skill_root)
            (skill_root / "agents" / "openai.yaml").write_text(
                "interface:\n  display_name: [broken\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.validator, "SKILL_ROOT", skill_root):
                errors = self.validator.skill_errors()
            self.assertTrue(any("invalid YAML" in error for error in errors))

    def test_skill_frontmatter_key_order_is_not_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir)
            self.write_skill_tree(skill_root)
            (skill_root / "SKILL.md").write_text(
                "---\ndescription: Valid description\nname: doc-sync\n---\n\n# Skill\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.validator, "SKILL_ROOT", skill_root):
                self.assertEqual(self.validator.skill_errors(), [])

    def test_home_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "notes.md").write_text("See /" + "Users/alice/project and ~/.claude/skills.\n", encoding="utf-8")
            (root / "ok.md").write_text("See ~/.codex/skills/doc-sync.\n", encoding="utf-8")
            with mock.patch.object(self.validator, "REPO_ROOT", root):
                errors = self.validator.private_path_errors()
            self.assertEqual(errors, ["notes.md:1: machine-specific home path"])

    def test_skill_respects_agent_skills_size_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir)
            self.write_skill_tree(skill_root)
            skill = skill_root / "SKILL.md"
            skill.write_text(f"---\nname: doc-sync\ndescription: {'x' * 1025}\n---\n", encoding="utf-8")
            with mock.patch.object(self.validator, "SKILL_ROOT", skill_root):
                errors = self.validator.skill_errors()
            self.assertIn("SKILL.md description exceeds 1024 characters", errors)
            skill.write_text("---\nname: doc-sync\ndescription: Valid\n---\n" + "line\n" * 500, encoding="utf-8")
            with mock.patch.object(self.validator, "SKILL_ROOT", skill_root):
                errors = self.validator.skill_errors()
            self.assertIn("SKILL.md must stay under 500 lines", errors)

    def test_short_description_must_match_skill_creator_length(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir)
            self.write_skill_tree(skill_root)
            metadata = skill_root / "agents" / "openai.yaml"
            metadata.write_text(
                metadata.read_text(encoding="utf-8").replace(
                    "Synchronize maintained project knowledge", "Too short"
                ),
                encoding="utf-8",
            )
            with mock.patch.object(self.validator, "SKILL_ROOT", skill_root):
                errors = self.validator.skill_errors()
            self.assertIn("agents/openai.yaml short_description must contain 25-64 characters", errors)

    def test_git_diff_errors_checks_worktree_and_staged_diffs(self) -> None:
        failed = mock.Mock(returncode=1, stdout="staged whitespace", stderr="")
        passed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.validator.subprocess, "run", side_effect=[passed, failed]) as run:
            self.assertEqual(self.validator.git_diff_errors(), ["staged whitespace"])
        self.assertEqual(run.call_args_list[0].args[0], ["git", "diff", "--check"])
        self.assertEqual(run.call_args_list[1].args[0], ["git", "diff", "--cached", "--check"])


if __name__ == "__main__":
    unittest.main()
