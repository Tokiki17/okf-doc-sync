from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


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
        self.root = Path(self._temp.name)

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
        self.write("docs/history/2024.md", "[Gone](gone.md) and `docs/gone.py`\n")
        report = self.validate(strict=True, historical_dirs=["docs/history"])
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])


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
        errors = self.validate(strict=True).errors
        self.assertEqual(
            errors,
            [
                "docs/sub/guide.md:2: code path 'scripts/missing.py' does not exist",
                "docs/sub/guide.md:2: code path './absent.txt' does not exist",
            ],
        )

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
        errors = self.validate().errors
        self.assertEqual(len(errors), 3, errors)
        self.assertIn("AGENTS.md:5: broken link 'missing-break.md' (does not exist)", errors)
        self.assertIn("AGENTS.md:5: code path 'scripts/missing.py' does not exist", errors)
        self.assertIn("docs/dots.md:3: broken link 'missing-dots.md' (does not exist)", errors)

    def test_crlf_blank_line_ends_unclosed_bracket(self) -> None:
        path = self.root / "AGENTS.md"
        path.write_bytes(b"Open [note\r\n\r\nSee [real](missing-crlf.md) ]\r\n")
        self.assertEqual(
            self.validate().errors,
            ["AGENTS.md:3: broken link 'missing-crlf.md' (does not exist)"],
        )

    def test_links_must_stay_inside_the_project(self) -> None:
        outside = Path(self._temp.name).parent / f"outside-{os.getpid()}.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink)
        self.write("AGENTS.md", f"[up](../{outside.name})\n[sym](docs/link.md)\n[abs](/docs/real.md)\n")
        self.write("docs/real.md", "# Real\n")
        try:
            (self.root / "docs" / "link.md").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        errors = self.validate().errors
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("escapes the project root", errors[0])
        self.assertIn("resolves outside the project root", errors[1])

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
