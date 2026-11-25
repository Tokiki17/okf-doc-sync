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

    def test_repository_is_python_310_and_standard_library_only(self) -> None:
        self.assertEqual(self.validator.python_compat_errors(), [])

    def test_python_compat_rejects_newer_syntax_and_third_party_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "third_party.py").write_text("import yaml\nfrom os import path\n", encoding="utf-8")
            (root / "newer.py").write_text(
                "try:\n    pass\nexcept* ValueError:\n    pass\n",
                encoding="utf-8",
            )
            errors = self.validator.python_compat_errors(root)
            self.assertEqual(len(errors), 2, errors)
            self.assertTrue(errors[0].startswith("newer.py:"))
            self.assertIn("not valid Python 3.10 syntax", errors[0])
            self.assertEqual(errors[1], "third_party.py:1: imports non-standard-library module 'yaml'")

    def test_git_diff_errors_checks_worktree_and_staged_diffs(self) -> None:
        failed = mock.Mock(returncode=1, stdout="staged whitespace", stderr="")
        passed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.validator.subprocess, "run", side_effect=[passed, failed]) as run:
            self.assertEqual(self.validator.git_diff_errors(), ["staged whitespace"])
        self.assertEqual(run.call_args_list[0].args[0], ["git", "diff", "--check"])
        self.assertEqual(run.call_args_list[1].args[0], ["git", "diff", "--cached", "--check"])


if __name__ == "__main__":
    unittest.main()
