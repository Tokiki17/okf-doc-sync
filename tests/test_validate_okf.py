from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "doc-sync" / "scripts" / "validate_okf.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_okf_under_test", VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load OKF validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ValidateOkfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = load_validator_module()

    def run_validator(self, bundle: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(bundle), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def write_minimal_conformant_bundle(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        concept = root / "thing.md"
        concept.write_text(
            "---\ntype: Unregistered Type\nproducer_extension: keep-me\n---\n\n# Thing\n",
            encoding="utf-8",
        )
        return concept

    def write_doc_sync_bundle(self, root: Path) -> Path:
        (root / "concepts").mkdir(parents=True, exist_ok=True)
        (root / "index.md").write_text(
            '---\nokf_version: "0.1"\n---\n\n'
            "# Index\n\n* [Coverage](concepts/coverage.md) - Coverage map.\n",
            encoding="utf-8",
        )
        (root / "log.md").write_text(
            "# Log\n\n## 2026-07-16\n\n* **Creation**: Added coverage.\n",
            encoding="utf-8",
        )
        concept = root / "concepts" / "coverage.md"
        concept.write_text(
            "---\n"
            "type: Coverage Manifest\n"
            "title: Coverage\n"
            "description: Maps maintained project knowledge.\n"
            "timestamp: 2026-07-16T09:00:00+08:00\n"
            "extension_key: preserved\n"
            "---\n\n"
            "# Coverage\n",
            encoding="utf-8",
        )
        return concept

    def test_minimal_unknown_bundle_passes_consumer_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_minimal_conformant_bundle(root)
            completed = self.run_validator(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_valid_doc_sync_profile_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_legacy_spine_flag_maps_to_doc_sync_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            completed = self.run_validator(root, "--require-doc-sync-spine")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_concept_requires_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_minimal_conformant_bundle(root)
            concept.write_text("---\ntitle: Missing type\n---\n\n# Thing\n", encoding="utf-8")
            completed = self.run_validator(root)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("non-empty string 'type'", completed.stderr)

    def test_broken_link_is_warning_unless_strict_or_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_doc_sync_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8") + "\n[Missing](missing.md)\n",
                encoding="utf-8",
            )
            permissive = self.run_validator(root)
            strict = self.run_validator(root, "--strict-links")
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(permissive.returncode, 0, permissive.stderr)
            self.assertIn("WARNING", permissive.stderr)
            self.assertEqual(strict.returncode, 1)
            self.assertEqual(profile.returncode, 1)

    def test_reference_style_broken_link_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_minimal_conformant_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8") + "\n[Missing][target]\n\n[target]: missing_(v2).md\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--strict-links")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("missing_(v2).md", completed.stderr)

    def test_nested_index_rejects_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            (root / "concepts" / "index.md").write_text(
                '---\nokf_version: "0.1"\n---\n\n# Concepts\n\n* [Coverage](coverage.md)\n',
                encoding="utf-8",
            )
            completed = self.run_validator(root)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("nested index.md", completed.stderr)

    def test_bundle_root_absolute_link_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_doc_sync_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8") + "\n[Root index](/index.md)\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--strict-links")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_local_link_cannot_escape_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "bundle"
            concept = self.write_doc_sync_bundle(root)
            (root.parent / "outside.md").write_text("outside\n", encoding="utf-8")
            concept.write_text(
                concept.read_text(encoding="utf-8") + "\n[Outside](/../outside.md)\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--strict-links")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("local link escapes the bundle", completed.stderr)

    def test_relative_link_may_reach_authoritative_doc_outside_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            root = repo / "okf"
            concept = self.write_doc_sync_bundle(root)
            (repo / "README.md").write_text("# Project\n", encoding="utf-8")
            concept.write_text(
                concept.read_text(encoding="utf-8") + "\n[Living source](../../README.md)\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_invalid_utf8_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_minimal_conformant_bundle(root)
            concept.write_bytes(b"\xff")
            completed = self.run_validator(root)
            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertIn("can't decode byte", completed.stderr)

    def test_profile_reports_every_missing_spine_part(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_minimal_conformant_bundle(root)
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("requires root index.md", completed.stderr)
            self.assertIn("requires root log.md", completed.stderr)
            self.assertIn('requires root okf_version: "0.1"', completed.stderr)
            self.assertIn("type 'Coverage Manifest'", completed.stderr)

    def test_root_index_version_must_be_a_string(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            (root / "index.md").write_text(
                "---\nokf_version: 0.1\n---\n\n# Index\n\n* [Coverage](concepts/coverage.md)\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("non-empty okf_version", completed.stderr)

    def test_unknown_version_warns_generically_and_fails_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            index = root / "index.md"
            index.write_text(index.read_text(encoding="utf-8").replace('"0.1"', '"9.9"'), encoding="utf-8")
            generic = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(generic.returncode, 0, generic.stderr)
            self.assertIn("unknown OKF version '9.9'", generic.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn('requires root okf_version: "0.1"', profile.stderr)

    def test_profile_requires_recommended_metadata(self) -> None:
        replacements = {
            "title": "title: Coverage\n",
            "description": "description: Maps maintained project knowledge.\n",
            "timestamp": "timestamp: 2026-07-16T09:00:00+08:00\n",
        }
        for field_name, source_line in replacements.items():
            with self.subTest(field=field_name), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                concept = self.write_doc_sync_bundle(root)
                concept.write_text(
                    concept.read_text(encoding="utf-8").replace(source_line, ""),
                    encoding="utf-8",
                )
                completed = self.run_validator(root, "--doc-sync-profile")
                self.assertEqual(completed.returncode, 1)
                self.assertIn(field_name, completed.stderr)

    def test_profile_rejects_multiline_description_and_naive_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_doc_sync_bundle(root)
            text = concept.read_text(encoding="utf-8")
            text = text.replace(
                "description: Maps maintained project knowledge.",
                "description: |\n  Maps maintained\n  project knowledge.",
            ).replace("2026-07-16T09:00:00+08:00", "2026-07-16T09:00:00")
            concept.write_text(text, encoding="utf-8")
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("description must be one line", completed.stderr)
            self.assertIn("timezone-aware", completed.stderr)

    def test_coverage_manifest_type_is_exact_but_whitespace_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_doc_sync_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace("Coverage Manifest", "Coverage Notes"),
                encoding="utf-8",
            )
            rejected = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(rejected.returncode, 1)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace("Coverage Notes", '" coverage   MANIFEST "'),
                encoding="utf-8",
            )
            accepted = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_profile_rejects_orphan_even_when_concept_body_links_to_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coverage = self.write_doc_sync_bundle(root)
            orphan = root / "concepts" / "orphan.md"
            orphan.write_text(
                "---\n"
                "type: Unregistered Type\n"
                "title: Orphan\n"
                "description: A deliberately orphaned concept.\n"
                "timestamp: 2026-07-16T09:00:00Z\n"
                "unknown: preserved\n"
                "---\n\n# Orphan\n",
                encoding="utf-8",
            )
            coverage.write_text(
                coverage.read_text(encoding="utf-8") + "\n[Orphan](orphan.md)\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("orphan.md", completed.stderr)
            self.assertIn("reachable from root index", completed.stderr)

    def test_nested_index_navigation_can_reach_concepts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            (root / "index.md").write_text(
                '---\nokf_version: "0.1"\n---\n\n# Index\n\n* [Concepts](concepts/index.md) - Concepts.\n',
                encoding="utf-8",
            )
            (root / "concepts" / "index.md").write_text(
                "# Concepts\n\n* [Coverage](coverage.md) - Coverage map.\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_four_space_nested_index_list_reaches_concept(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            (root / "index.md").write_text(
                '---\nokf_version: "0.1"\n---\n\n'
                "# Index\n\n* Knowledge\n"
                "    * [Coverage](concepts/coverage.md) - Coverage map.\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_profile_validates_resource_first_citations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_doc_sync_bundle(root)
            text = concept.read_text(encoding="utf-8").replace(
                "extension_key: preserved",
                "resource: https://example.com/source\nextension_key: preserved",
            )
            concept.write_text(text, encoding="utf-8")
            missing = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(missing.returncode, 1)
            self.assertIn("final # Citations", missing.stderr)
            concept.write_text(
                text + "\n# Citations\n\n[1] [Source](https://example.com/source)\n",
                encoding="utf-8",
            )
            valid = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_profile_accepts_reference_style_citation_with_document_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_doc_sync_bundle(root)
            text = concept.read_text(encoding="utf-8").replace(
                "extension_key: preserved",
                "resource: https://example.com/source\nextension_key: preserved",
            )
            concept.write_text(
                text
                + "\n# Citations\n\n[1] [Source][source]\n\n"
                + "[source]: https://example.com/source\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_profile_rejects_bad_citation_structure_and_uncited_external_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_doc_sync_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8")
                + "\n[External](https://example.com/uncited)\n"
                + "\n# Citations\n\n[2] [Other](https://example.com/other)\n"
                + "\n# Later\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("final level-one section", completed.stderr)
            self.assertIn("consecutive from [1]", completed.stderr)
            self.assertIn("missing from # Citations", completed.stderr)

    def test_markdown_scanner_handles_inline_reference_and_code_boundaries(self) -> None:
        text = r"""
[plain](plain.md)
[nested](a_(b).md "Title")
[angle](<a b.md> 'Title')
[full][Target ID]
[collapsed][]
[shortcut]

[target   id]: reference.md
[TARGET ID]: ignored-duplicate.md
[collapsed]: collapsed.md
[shortcut]: shortcut.md

![image](image.md)
![image-ref][Target ID]
`[inline-code](ignored.md)`

```md
[fenced](ignored-too.md)
```

    [indented](ignored-three.md)
    - [indented-code-marker](ignored-five.md)
    - code parent
        - [nested-indented-code-marker](ignored-six.md)
- Parent
    - [nested-list](nested-list.md)
- Code parent
        - [list-contained-code-marker](ignored-seven.md)
\[escaped](ignored-four.md)
"""
        self.assertEqual(
            self.validator.extract_markdown_link_targets(text),
            [
                "plain.md",
                "a_(b).md",
                "a b.md",
                "reference.md",
                "collapsed.md",
                "shortcut.md",
                "nested-list.md",
            ],
        )

    def test_profile_accepts_unknown_concept_types_and_extension_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_doc_sync_bundle(root)
            extension = root / "concepts" / "extension.md"
            extension.write_text(
                "---\n"
                "title: Extension Concept\n"
                "description: A one-line extension concept.\n"
                "type: Vendor Specific Concept\n"
                "timestamp: 2026-07-16T10:30:46Z\n"
                "x-vendor-field: preserved\n"
                "---\n\n# Extension Concept\n",
                encoding="utf-8",
            )
            with (root / "index.md").open("a", encoding="utf-8") as handle:
                handle.write("\n- [Extension Concept](concepts/extension.md)\n")

            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
