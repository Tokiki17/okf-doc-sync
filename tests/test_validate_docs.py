from __future__ import annotations

import importlib.util
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "doc-sync" / "scripts" / "validate_docs.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_docs_under_test", VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load validate_docs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProjectTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = load_validator()
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve() / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def write(self, relative: str, text: str = "") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def validate(self, **kwargs):
        return self.validator.validate_project(self.root, **kwargs)


class ReachabilityTests(ProjectTestCase):
    def test_index_not_reached_from_entrypoint_cannot_launder_orphans(self) -> None:
        self.write("AGENTS.md", "# Agents\n\nNo routes yet.\n")
        self.write("docs/index.md", "- [A](a.md)\n")
        self.write("docs/a.md", "# A\n")
        report = self.validate()
        self.assertEqual(report.errors, [])
        self.assertIn("docs/index.md: not reachable from AGENTS.md", report.warnings)
        self.assertIn("docs/a.md: not reachable from AGENTS.md", report.warnings)
        strict = self.validate(strict=True)
        self.assertIn("docs/a.md: not reachable from AGENTS.md", strict.errors)

    def test_entry_and_index_edges(self) -> None:
        self.write("AGENTS.md", "Read [the index](docs/index.md) first.\n")
        self.write(
            "docs/index.md",
            "- [Linked](linked.md)\n- Imported: @imported.md\n- Path: `docs/backtick.md`\n",
        )
        self.write("docs/linked.md", "Ordinary doc mentioning `docs/plain-mention.md`.\n")
        self.write("docs/imported.md", "# Imported\n")
        self.write("docs/backtick.md", "# Backtick\n")
        self.write("docs/plain-mention.md", "# Only mentioned in body text\n")
        report = self.validate(strict=True)
        self.assertEqual(
            report.errors,
            ["docs/plain-mention.md: not reachable from AGENTS.md"],
        )

    def test_readme_is_the_fallback_entrypoint(self) -> None:
        self.write("README.md", "See [guide](docs/guide.md).\n")
        self.write("docs/guide.md", "# Guide\n")
        self.write("docs/orphan.md", "# Orphan\n")
        report = self.validate(strict=True)
        self.assertEqual(report.errors, ["docs/orphan.md: not reachable from README.md"])

    def test_claude_md_without_agents_import_is_flagged(self) -> None:
        self.write("AGENTS.md", "# Shared\n")
        self.write("CLAUDE.md", "Read AGENTS.md.\n")
        report = self.validate()
        self.assertTrue(any("@AGENTS.md" in warning for warning in report.warnings))
        self.write("CLAUDE.md", "@AGENTS.md\n\nClaude-only rule.\n")
        self.assertEqual(self.validate().warnings, [])

    def test_broken_claude_import_is_an_error(self) -> None:
        self.write("CLAUDE.md", "@docs/missing.md\n")
        report = self.validate()
        self.assertEqual(len(report.errors), 1)
        self.assertIn("broken import '@docs/missing.md'", report.errors[0])

    def test_historical_dir_is_exempt(self) -> None:
        self.write("AGENTS.md", "# Agents\n")
        for directory in ("docs/cli", "docs/History", "docs/superpowers/plans", "docs/archive"):
            self.write(f"{directory}/record.md", "[Gone](gone.md) and `docs/gone.py`\n")
        report = self.validate(strict=True, historical_dirs=["docs/cli"])
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_only_entrypoint_comments_outside_code_declare_historical_dirs(self) -> None:
        self.write(
            "AGENTS.md",
            "<!-- A plain comment with an unmatched backtick ` -->\n"
            "<!-- DOC-SYNC: Historical-Dirs = custom\\logs/, docs/declared docs/more -->\n\n"
            "<!-- doc-sync: historical-dir /docs/absolute ../docs/escape -->\n\n"
            "Example of an opener: `<!--`.\n\n"
            "```md\n<!-- doc-sync: historical-dir docs/fenced -->\n```\n\n"
            "    <!-- doc-sync: historical-dir docs/indented -->\n\n"
            "Example: `<!-- doc-sync: historical-dir docs/inline -->`.\n\n"
            "\\<!-- doc-sync: historical-dir docs/escaped -->\n\n"
            ">     <!-- doc-sync: historical-dir docs/quoted-indent -->\n\n"
            "> ~~~md\n> <!-- doc-sync: historical-dir docs/quoted-fence -->\n> ~~~\n\n"
            "- ```md\n  <!-- doc-sync: historical-dir docs/list-fence -->\n  ```\n\n"
            "# Heading\n    <!-- doc-sync: historical-dir docs/after-heading -->\n",
        )
        self.write("CLAUDE.md", "@AGENTS.md\n\n<!-- doc-sync: historical-dir docs/imported -->\n")
        self.write("README.md", "<!-- doc-sync: historical-dir docs/readme -->\n")
        for directory in ("custom/logs", "docs/declared", "docs/more", "docs/imported", "docs/cli"):
            self.write(f"{directory}/record.md", "[Gone](gone.md)\n")
        living = (
            "absolute", "after-heading", "escape", "escaped", "fenced", "indented",
            "inline", "list-fence", "quoted-fence", "quoted-indent", "readme",
        )
        for name in living:
            self.write(f"docs/{name}/record.md", "# Living\n")
        report = self.validate(strict=True, historical_dirs=["docs/cli"])
        self.assertEqual(
            report.errors,
            [f"docs/{name}/record.md: not reachable from AGENTS.md, CLAUDE.md" for name in living],
        )
        self.assertEqual(report.warnings, [])

    def test_fallback_readme_can_declare_historical_dirs(self) -> None:
        self.write("README.md", "<!-- doc-sync: historical-dir custom/logs -->\n")
        self.write("custom/logs/record.md", "[Gone](gone.md)\n")
        self.assertEqual(self.validate(strict=True).errors, [])


class LinkAndPathTests(ProjectTestCase):
    def test_backtick_paths_resolve_from_project_root_or_document(self) -> None:
        self.write("AGENTS.md", "[Guide](docs/sub/guide.md)\n")
        self.write("scripts/tool.py", "")
        self.write(
            "docs/sub/guide.md",
            "Run `scripts/tool.py:12` and read `./notes.txt`.\n"
            "Stale: `scripts/missing.py` and `./absent.txt`.\n"
            "Ignored: `python3 scripts/tool.py --check`, `unknown/dir/file.py`, `owner/repo`.\n",
        )
        self.write("docs/sub/notes.txt", "")
        for strict in (False, True):
            with self.subTest(strict=strict):
                report = self.validate(strict=strict)
                self.assertEqual(report.errors, [])
                self.assertEqual(
                    report.warnings,
                    [
                        "docs/sub/guide.md:2: code path 'scripts/missing.py' does not exist",
                        "docs/sub/guide.md:2: code path './absent.txt' does not exist",
                    ],
                )

    def test_document_relative_code_paths_can_fall_back_to_root(self) -> None:
        self.write("AGENTS.md", "[Guide](docs/sub/guide.md)\n")
        self.write("scripts/tool.py")
        self.write("../sibling/file.txt")
        self.write(
            "docs/sub/guide.md",
            "Use `./scripts/tool.py` and `../sibling/file.txt`.\n"
            "[Guide](./scripts/tool.py)\n",
        )
        report = self.validate(strict=True)
        self.assertEqual(report.errors, ["docs/sub/guide.md:2: broken link './scripts/tool.py' (does not exist)"])
        self.assertEqual(report.warnings, [])
        public = self.validate(strict=True, check_private_paths=True)
        self.assertEqual(public.errors, report.errors)
        self.assertEqual(len(public.warnings), 1, public.warnings)
        self.assertIn("escapes the project root", public.warnings[0])

    def test_strict_cli_exits_successfully_with_code_path_warnings(self) -> None:
        self.write("AGENTS.md", "Run `./missing.py`.\n")
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(self.validator.main([str(self.root), "--strict"]), 0)
        self.assertIn("WARNING:", stdout.getvalue())

    def test_root_code_path_tries_enclosing_subpackage(self) -> None:
        self.write("scripts/tool.py")
        self.write("subpkg/scripts/local.py")
        self.write("subpkg/references/ops.md", "Use `scripts/local.py`.\n")
        self.assertEqual(self.validate().warnings, [])
        self.assertEqual(self.validate().errors, [])

    def test_artifact_and_placeholder_code_paths_are_ignored(self) -> None:
        self.write("tests/example.py")
        self.write(
            "AGENTS.md",
            "`tests/subpkg/TestResults/run.trx` `tests/NNN/file.md` `tests/NNN-example.md`\n"
            "`tests/XXX/example.py` `tests/YYYY/example.py` `tests/.../example.py`\n",
        )
        report = self.validate(strict=True)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_heading_anchor_keeps_inline_code_text(self) -> None:
        self.write(
            "AGENTS.md",
            "[ok](docs/guide.md#using-foo_bar-safely)\n"
            "[dup](docs/guide.md#setup-1)\n"
            "[setext](docs/guide.md#overview)\n"
            "[cjk](docs/guide.md#安装与验证)\n"
            "[local](#agents)\n"
            "[bad](docs/guide.md#missing)\n",
        )
        self.write(
            "docs/guide.md",
            "Overview\n========\n\n## Using `foo_bar()` safely\n\n## Setup\n\n## Setup\n\n## 安装与验证\n",
        )
        self.write("AGENTS.md", "# Agents\n\n" + (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        errors = self.validate().errors
        self.assertEqual(errors, ["AGENTS.md:8: missing heading anchor 'docs/guide.md#missing'"])

    def test_code_is_masked_but_multiline_links_are_found(self) -> None:
        self.write(
            "AGENTS.md",
            "Intro with a [link that\nwraps](missing-wrapped.md).\n\n"
            "```md\n[fenced](missing-fenced.md)\n```\n\n"
            "~~~\n[tilde](missing-tilde.md)\n~~~\n\n"
            "    [indented](missing-indented.md)\n\n"
            "<!-- [comment](missing-comment.md)\n-->\n\n"
            "Inline `code [x](missing-inline.md)\nspanning lines` ends.\n\n"
            "- item\n    - [nested](missing-nested.md)\n",
        )
        errors = self.validate().errors
        self.assertEqual(
            errors,
            [
                "AGENTS.md:1: broken link 'missing-wrapped.md' (does not exist)",
                "AGENTS.md:21: broken link 'missing-nested.md' (does not exist)",
            ],
        )

    def test_reference_definitions_and_images(self) -> None:
        self.write("AGENTS.md", "[Ref][r] ![img](missing.png)\n\n[r]: missing_(v2).md\n")
        self.assertEqual(
            self.validate().errors,
            ["AGENTS.md:3: broken link 'missing_(v2).md' (does not exist)"],
        )

    def test_reference_definition_needs_a_clean_destination(self) -> None:
        self.write(
            "AGENTS.md",
            "# Agents\n\n"
            "[INFO]: server started\n"
            "[Option A]: read the guide first\n\n"
            '[r]: missing.md "Title"\n\n'
            "[r2]:\n"
            "  missing2.md\n",
        )
        self.assertEqual(
            self.validate().errors,
            [
                "AGENTS.md:6: broken link 'missing.md' (does not exist)",
                "AGENTS.md:9: broken link 'missing2.md' (does not exist)",
            ],
        )

    def test_leading_thematic_break_is_not_frontmatter(self) -> None:
        self.write("scripts/tool.py", "")
        self.write(
            "AGENTS.md",
            "---\n\n# Agents\n\n"
            "[gone](missing-break.md) and `scripts/missing.py`.\n"
            "[Dots](docs/dots.md) [Front](docs/front.md)\n\n"
            "---\n\nTail.\n",
        )
        self.write("docs/dots.md", "---\n\n[x](missing-dots.md)\n\n...\n")
        self.write(
            "docs/front.md",
            "---\n# comment\ntitle: Front\nrelated: [x](missing-front.md)\ntags:\n  - a\n---\n\n# Front\n",
        )
        report = self.validate()
        self.assertEqual(
            report.errors,
            [
                "AGENTS.md:5: broken link 'missing-break.md' (does not exist)",
                "docs/dots.md:3: broken link 'missing-dots.md' (does not exist)",
            ],
        )
        self.assertEqual(report.warnings, ["AGENTS.md:5: code path 'scripts/missing.py' does not exist"])

    def test_crlf_blank_line_ends_unclosed_bracket(self) -> None:
        path = self.root / "AGENTS.md"
        path.write_bytes(b"Open [note\r\n\r\nSee [real](missing-crlf.md) ]\r\n")
        self.assertEqual(
            self.validate().errors,
            ["AGENTS.md:3: broken link 'missing-crlf.md' (does not exist)"],
        )

    def test_sibling_links_and_imports_follow_workspace_or_public_mode(self) -> None:
        self.write("../sibling-repo/Guide.md", '# Outside\n\n<a id="details"></a>\n')
        self.write("AGENTS.md", "[up](../sibling-repo/Guide.md#outside)\n[abs](/docs/real.md)\n")
        self.write("docs/real.md", "# Real\n")
        self.write("CLAUDE.md", "@AGENTS.md\n@../sibling-repo/Guide.md\n")
        self.assertEqual(self.validate(strict=True).errors, [])
        self.assertEqual(self.validate(strict=True).warnings, [])
        public = self.validate(strict=True, check_private_paths=True)
        self.assertEqual(len(public.errors), 2, public.errors)
        self.assertTrue(all("escapes the project root" in error for error in public.errors))

        self.write(
            "AGENTS.md",
            "[html](../sibling-repo/Guide.md#details)\n"
            "[anchor](../sibling-repo/Guide.md#missing)\n"
            "[target](../sibling-repo/missing.md)\n"
            "[case](../sibling-repo/guide.md)\n",
        )
        self.write("CLAUDE.md", "@AGENTS.md\n@../sibling-repo/missing.md\n")
        errors = self.validate().errors
        self.assertEqual(len(errors), 4, errors)
        self.assertIn("missing heading anchor", errors[0])
        self.assertIn("does not exist", errors[1])
        self.assertIn("guide.md", errors[2])
        self.assertIn("broken import", errors[3])

    def test_symlink_targets_outside_project_follow_workspace_or_public_mode(self) -> None:
        outside = self.write("../sibling-repo/guide.md", "# Outside\n")
        self.write("AGENTS.md", "[sym](docs/link.md#outside)\n")
        (self.root / "docs").mkdir()
        try:
            (self.root / "docs" / "link.md").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(self.validate(strict=True).errors, [])
        errors = self.validate(strict=True, check_private_paths=True).errors
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("resolves outside the project root", errors[0])
        self.write("AGENTS.md", "[sym](docs/link.md#missing)\n")
        self.assertIn("missing heading anchor", self.validate().errors[0])

    def test_parent_segment_after_symlink_checks_the_actual_target(self) -> None:
        self.write("guide.md", "# Local\n")
        self.write("../sibling-repo/guide.md", "# External\n")
        outside = self.write("../sibling-repo/subpkg/notes.txt")
        try:
            (self.root / "subpkg").symlink_to(outside.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.write("AGENTS.md", "[guide](subpkg/../guide.md#external)\n")
        report = self.validate(strict=True)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])
        errors = self.validate(check_private_paths=True).errors
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("resolves outside the project root", errors[0])

    def test_public_path_boundaries_also_apply_to_historical_documents(self) -> None:
        self.write("../sibling-repo/guide.md", "# External\n")
        self.write("docs/archive/record.md", "[stale](gone.md) [external](../../../sibling-repo/guide.md)\n")
        self.assertEqual(self.validate(strict=True).errors, [])
        errors = self.validate(strict=True, check_private_paths=True).errors
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("escapes the project root", errors[0])

    def test_home_links_resolve_on_disk_and_are_rejected_in_public_mode(self) -> None:
        home = self.root.parent / "synthetic-home"
        guide = self.write("../synthetic-home/Guide.md", "# Details\n").resolve()
        with mock.patch.object(self.validator, "HOME_PATH_PATTERN", re.compile(re.escape(home.as_posix()))):
            self.write("AGENTS.md", f"[guide]({guide.as_posix()}#details)\n")
            self.assertEqual(self.validate().errors, [])
            self.assertEqual(self.validate().warnings, [])
            self.assertTrue(any("broken link" in error for error in self.validate(check_private_paths=True).errors))
            self.write(
                "AGENTS.md",
                f"[anchor]({guide.as_posix()}#missing)\n[missing]({home.as_posix()}/missing.md)\n",
            )
            errors = self.validate().errors
            self.assertEqual(len(errors), 2, errors)
            self.assertIn("missing heading anchor", errors[0])
            self.assertIn("does not exist", errors[1])

    def test_windows_home_link_is_checked_as_a_path_instead_of_a_url(self) -> None:
        home_path = "C:/" + "Users/synthetic-user/guide.md"
        self.write("AGENTS.md", f"[home]({home_path})\n[guide](Q:/synthetic/guide.md)\n")
        errors = self.validate(check_private_paths=True).errors
        self.assertTrue(any("broken link" in error and "machine-specific home path" in error for error in errors))
        self.assertTrue(any("Q:/synthetic/guide.md" in error and "escapes the project root" in error for error in errors))

    def test_home_import_is_checked_against_workspace_or_public_boundary(self) -> None:
        home = self.write("../synthetic-home/guide.md", "# Guide\n").resolve()
        self.write("CLAUDE.md", "@~/guide.md\n")
        with mock.patch.object(self.validator.os.path, "expanduser", return_value=str(home)):
            self.assertEqual(self.validate().errors, [])
            errors = self.validate(check_private_paths=True).errors
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("escapes the project root", errors[0])
            home.unlink()
            self.assertIn("does not exist", self.validate().errors[0])

    def test_link_case_must_match_exactly(self) -> None:
        self.write("AGENTS.md", "[guide](docs/guide.md)\n")
        self.write("docs/Guide.md", "# Guide\n")
        errors = self.validate().errors
        self.assertEqual(len(errors), 1)
        self.assertIn("broken link 'docs/guide.md'", errors[0])

    def test_private_paths(self) -> None:
        self.write("notes.md", "See /" + "Users/alice/project.\n")
        self.write("win.txt", "C:\\" + "Users\\bob\\x and C:/" + "Users/carol/y\n")
        self.write("ok.md", "See ~/.claude/skills and /" + "Users/<name>.\n")
        errors = self.validate(check_private_paths=True).errors
        self.assertEqual(errors, ["notes.md:1: machine-specific home path", "win.txt:1: machine-specific home path"])


class DiscoveryTests(ProjectTestCase):
    def test_non_git_walk_prunes_artifacts_and_hidden_directories(self) -> None:
        self.write(
            "AGENTS.md",
            "[Output](outputs/report.md#report) [CI](.github/guide.md) "
            "[Template](templates/guide.md#report)\n",
        )
        for relative in (
            "output/report.md", "outputs/report.md", "tmp/report.md", ".github/guide.md", "templates/guide.md",
        ):
            path = self.write(relative, "# Report\n\n[Gone](gone.md)\n")
            self.assertNotIn(path, self.validator.list_project_files(self.root))
        report = self.validate(strict=True)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])


@unittest.skipUnless(shutil.which("git"), "git unavailable")
class GitDiscoveryTests(ProjectTestCase):
    def git(self, *args, cwd=None) -> None:
        subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, check=True)

    def test_nested_code_path_with_no_matching_root_directory(self) -> None:
        self.git("init", "-q")
        self.write("subpkg/scripts/local.py")
        self.write("subpkg/references/ops.md", "Use `scripts/local.py` and `scripts/missing.py`.\n")
        self.git("add", "subpkg")

        report = self.validate(strict=True)
        self.assertEqual(report.errors, [])
        self.assertEqual(
            report.warnings,
            ["subpkg/references/ops.md:1: code path 'scripts/missing.py' does not exist"],
        )

    def test_tracked_directories_only_and_batched_ignore_checks(self) -> None:
        self.git("init", "-q")
        self.write(".gitignore", "/docs/sub/scripts/generated.py\n/scripts/cache.db\n/scripts/generated/\n")
        self.write("scripts/tool.py")
        self.write("output/asset.txt")
        self.write("scratch/asset.txt")
        self.write("AGENTS.md", "[Guide](docs/sub/guide.md)\n`output/absent.txt` `scratch/absent.txt`\n")
        self.git("add", "scripts/tool.py")
        self.assertEqual(self.validator._top_level_dirs(self.root), {"scripts"})

        nested = self.root / "scripts" / "subpkg"
        nested.mkdir()
        self.git("init", "-q", cwd=nested)
        outside = self.write("../sibling-repo/guide.md")
        try:
            (self.root / "scripts" / "linked").symlink_to(outside.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.write(
            "docs/sub/guide.md",
            "`scripts/generated.py` `scripts/cache.db` `scripts/generated/` `scripts/missing.py`\n"
            "`scripts/linked/missing.py` `scripts/subpkg/missing.py`\n",
        )
        with mock.patch.object(self.validator.subprocess, "run", wraps=subprocess.run) as run:
            report = self.validate(strict=True)
        self.assertEqual(report.errors, [])
        self.assertEqual(len(report.warnings), 3, report.warnings)
        for value in ("scripts/missing.py", "scripts/linked/missing.py", "scripts/subpkg/missing.py"):
            self.assertTrue(any(f"'{value}'" in warning for warning in report.warnings), report.warnings)
        checks = [call for call in run.call_args_list if call.args[0][:2] == ["git", "check-ignore"]]
        self.assertEqual(len(checks), 1)
        checked_paths = checks[0].kwargs["input"].split(b"\0")
        self.assertNotIn(b"scripts/linked/missing.py", checked_paths)
        self.assertNotIn(b"scripts/subpkg/missing.py", checked_paths)

    def test_skipped_markdown_is_still_scanned_for_private_paths(self) -> None:
        self.git("init", "-q")
        self.write(
            "AGENTS.md",
            "[Output](outputs/report.md#report) [Hidden](.claude/report.md#report) "
            "[Template](docs/templates/report.md#report)\n",
        )
        for directory in ("output", "outputs", "tmp", ".claude", "docs/vendor", "docs/templates"):
            self.write(f"{directory}/report.md", "# Report\n\n[Gone](gone.md)\n")
        self.write("output/report.md", "# Report\n\n[Gone](gone.md)\nSee /" + "home/synthetic-user/config.\n")
        self.git("add", "output", ".claude", "docs/vendor", "docs/templates")
        self.assertEqual(self.validate(strict=True).errors, [])
        public = self.validate(strict=True, check_private_paths=True)
        self.assertEqual(public.errors, ["output/report.md:4: machine-specific home path"])
        self.assertEqual(public.warnings, [])


class SkillTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = load_validator()
        self._temp = tempfile.TemporaryDirectory()
        self.skill = Path(self._temp.name) / "doc-sync"
        (self.skill / "agents").mkdir(parents=True)
        (self.skill / "SKILL.md").write_text(
            "---\nname: doc-sync\ndescription: Valid description\n---\n\n# Skill\n", encoding="utf-8"
        )
        (self.skill / "agents" / "openai.yaml").write_text(
            "interface:\n"
            '  display_name: "Doc Sync"\n'
            "  short_description: Synchronize maintained project knowledge\n"
            "  default_prompt: 'Use $doc-sync now.'  # comment\n"
            "\n"
            "policy:\n"
            "  allow_implicit_invocation: true\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def errors(self) -> list[str]:
        return self.validator.validate_skill_tree(self.skill)

    def test_valid_tree(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_frontmatter_errors_name_the_field(self) -> None:
        skill = self.skill / "SKILL.md"
        skill.write_text("---\nname: doc-sync\ndescription: broken: yaml\n---\n", encoding="utf-8")
        self.assertIn("field 'description'", self.errors()[0])
        skill.write_text("---\nname: other\ndescription: ok\ncompatibility: x\n---\n", encoding="utf-8")
        errors = self.errors()
        self.assertTrue(any("field 'compatibility'" in error for error in errors), errors)
        self.assertTrue(any("field 'name'" in error for error in errors), errors)
        skill.write_text("---\ndescription: Valid\nname: doc-sync\n---\n[gone](references/gone.md)\n", encoding="utf-8")
        self.assertEqual(self.errors(), ["SKILL.md:5: broken link 'references/gone.md' (does not exist)"])

    def test_agent_metadata_errors_name_the_field(self) -> None:
        metadata = self.skill / "agents" / "openai.yaml"
        metadata.write_text("interface:\n  display_name: [broken\n", encoding="utf-8")
        self.assertIn("field 'interface.display_name'", self.errors()[0])
        metadata.write_text(
            "interface:\n  display_name: Doc\n  short_description: Too short\n  default_prompt: no invocation\n",
            encoding="utf-8",
        )
        errors = self.errors()
        self.assertIn("agents/openai.yaml field 'interface.short_description': must contain 25-64 characters", errors)
        self.assertIn("agents/openai.yaml field 'interface.default_prompt': must invoke $doc-sync", errors)
        self.assertIn("agents/openai.yaml field 'policy.allow_implicit_invocation': must be true", errors)

    def test_size_limits(self) -> None:
        skill = self.skill / "SKILL.md"
        skill.write_text(f"---\nname: doc-sync\ndescription: {'x' * 1025}\n---\n", encoding="utf-8")
        self.assertIn("SKILL.md frontmatter field 'description': exceeds 1024 characters", self.errors())
        skill.write_text("---\nname: doc-sync\ndescription: Valid\n---\n" + "line\n" * 500, encoding="utf-8")
        self.assertIn("SKILL.md must stay under 500 lines", self.errors())


if __name__ == "__main__":
    unittest.main()
