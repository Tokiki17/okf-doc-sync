from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "doc-sync" / "scripts" / "validate_okf.py"
GENERATED = "generated: { by: 'process:doc-sync', at: '2026-11-20T10:00:00+08:00' }"


class ValidateOkfSpecTests(unittest.TestCase):
    def run_validator(self, bundle: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(bundle), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def write_bundle(self, root: Path, version: str = "0.3", extra: str = "") -> Path:
        (root / "concepts").mkdir(parents=True)
        (root / "index.md").write_text(
            f'---\nokf_version: "{version}"\n---\n\n# Index\n\n* [Coverage](concepts/coverage.md)\n',
            encoding="utf-8",
        )
        (root / "log.md").write_text("# Log\n\n## 2026-11-20\n\n* Created.\n", encoding="utf-8")
        concept = root / "concepts" / "coverage.md"
        concept.write_text(
            "---\n"
            "type: Coverage Manifest\n"
            "title: Coverage\n"
            "description: Maps maintained knowledge.\n"
            f"{GENERATED}\n"
            f"{extra}"
            "---\n\n# Coverage\n",
            encoding="utf-8",
        )
        return concept

    def both(self, root: Path) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
        return self.run_validator(root), self.run_validator(root, "--doc-sync-profile")

    def test_profile_accepts_minimal_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root)
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertEqual(profile.returncode, 0, profile.stderr)
            self.assertEqual(profile.stderr, "")

    def test_root_index_accepts_bundle_metadata_and_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root)
            (root / "LICENSE.txt").write_text("MIT\n", encoding="utf-8")
            for license_value in ("MIT", "./LICENSE.txt"):
                with self.subTest(license=license_value):
                    (root / "index.md").write_text(
                        '---\nokf_version: "0.3"\ntitle: Project knowledge\n'
                        "description: Maintained project knowledge.\n"
                        f"license: {license_value}\nx-acme-owner: docs\n---\n\n"
                        "# Index\n\n* [Coverage](concepts/coverage.md)\n",
                        encoding="utf-8",
                    )
                    consumer, profile = self.both(root)
                    self.assertEqual(consumer.returncode, 0, consumer.stderr)
                    self.assertEqual(profile.returncode, 0, profile.stderr)

    def test_root_index_metadata_shape_and_license_path_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root)
            (root / "index.md").write_text(
                '---\nokf_version: "0.3"\ntitle: 42\nlicense: ./missing/LICENSE\n---\n\n'
                "# Index\n\n* [Coverage](concepts/coverage.md)\n",
                encoding="utf-8",
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("root index title", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("root index title", profile.stderr)
            self.assertIn("license path", profile.stderr)

    def test_untyped_markdown_is_skipped_with_warning_but_fails_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root)
            (root / "README.md").write_text("# Readme\n", encoding="utf-8")
            (root / "notes.md").write_text("---\ntitle: Notes\n---\n\n# Notes\n", encoding="utf-8")
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("not an OKF concept", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("README.md", profile.stderr)
            self.assertIn("notes.md", profile.stderr)

    def test_dot_paths_are_not_part_of_the_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root)
            (root / ".drafts").mkdir()
            (root / ".drafts" / "draft.md").write_text("no frontmatter\n", encoding="utf-8")
            consumer, profile = self.both(root)
            self.assertEqual(profile.returncode, 0, profile.stderr)
            self.assertNotIn("draft.md", consumer.stderr)

    def test_accepts_date_only_and_native_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(
                root,
                extra=(
                    "stale_after: 2027-01-01\n"
                    "sources:\n  - resource: https://example.com\n    last_modified: '2026-11-01'\n"
                    "    usage_count: 3\n"
                    "usage_window: { from: '2026-10-01', to: 2026-10-31T00:00:00Z }\n"
                ),
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertEqual(profile.returncode, 0, profile.stderr)

    def test_rejects_date_time_without_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root, extra="stale_after: '2027-01-01T00:00:00'\n")
            consumer, profile = self.both(root)
            self.assertIn("stale_after", consumer.stderr)
            self.assertEqual(profile.returncode, 1)

    def test_profile_requires_date_time_for_trust_comparisons(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_bundle(root, extra="verified: { by: 'process:checker', at: '2026-11-21' }\n")
            concept.write_text(
                concept.read_text(encoding="utf-8").replace("'2026-11-20T10:00:00+08:00'", "'2026-11-20'"),
                encoding="utf-8",
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("generated.at to be a timezone-aware date-time", profile.stderr)
            self.assertIn("verified[0].at to be a timezone-aware date-time", profile.stderr)

    def test_blank_values_mean_absent_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(
                root,
                extra="stale_after: ''\nstatus: null\nverified: []\nsources: []\nsuperseded_by: null\n",
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.stderr, "")
            self.assertEqual(profile.returncode, 0, profile.stderr)

    def test_profile_treats_null_generated_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(GENERATED, "generated: null"),
                encoding="utf-8",
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("requires generated.by and generated.at", profile.stderr)

    def test_single_source_mapping_is_a_list_of_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(
                root,
                extra="sources: { id: guide, resource: https://example.com }\n",
            )
            concept = root / "concepts" / "coverage.md"
            concept.write_text(
                concept.read_text(encoding="utf-8") + "\nA claim.[^guide]\n\n[^guide]: Guide\n",
                encoding="utf-8",
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.stderr, "")
            self.assertEqual(profile.returncode, 0, profile.stderr)

    def test_actor_schemes_and_source_author(self) -> None:
        for actor in ("team:docs", "service:indexer", "human:reviewer", "writer/v2"):
            with self.subTest(actor=actor), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                self.write_bundle(
                    root,
                    extra=(
                        f"verified: {{ by: '{actor}', at: '2026-11-21T00:00:00Z' }}\n"
                        f"sources: [{{ resource: 'https://example.com', author: '{actor}' }}]\n"
                    ),
                )
                self.assertEqual(self.run_validator(root, "--doc-sync-profile").returncode, 0)
        for actor in ("team:", "Docs Team", "writer/"):
            with self.subTest(invalid_actor=actor), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                self.write_bundle(
                    root, extra=f"sources: [{{ resource: 'https://example.com', author: '{actor}' }}]\n"
                )
                consumer, profile = self.both(root)
                self.assertEqual(consumer.returncode, 0, consumer.stderr)
                self.assertIn("sources[0].author must follow the OKF actor convention", consumer.stderr)
                self.assertEqual(profile.returncode, 1)

    def test_superseded_by_requires_deprecation_and_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root, extra="superseded_by: replacement.md\n")
            consumer, profile = self.both(root)
            self.assertIn("superseded_by requires status: deprecated", consumer.stderr)
            self.assertIn("broken local link 'replacement.md'", profile.stderr)
            (root / "concepts" / "replacement.md").write_text(
                "---\ntype: Note\n---\n", encoding="utf-8"
            )
            concept = root / "concepts" / "coverage.md"
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "superseded_by: replacement.md", "status: deprecated\nsuperseded_by: /concepts/replacement.md"
                ),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            self.assertEqual(consumer.stderr, "")

    def test_legacy_v01_bundle_is_read_and_profile_lists_migration_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_bundle(root, version="0.1")
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    GENERATED, "timestamp: 2026-07-16T09:00:00+08:00"
                )
                + "\n# Citations\n\n[1] [Guide](https://example.com)\n",
                encoding="utf-8",
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("declares OKF v0.1", consumer.stderr)
            self.assertIn("references/okf-migration.md", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn('requires root okf_version: "0.3"', profile.stderr)
            self.assertIn("references/okf-migration.md", profile.stderr)
            self.assertIn("requires generated.by and generated.at", profile.stderr)

    def test_legacy_v02_bundle_needs_only_the_version_bump(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root, version="0.2")
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(profile.returncode, 1)
            self.assertEqual(profile.stderr.count("ERROR"), 1, profile.stderr)
            self.assertIn("declares OKF v0.2", profile.stderr)

    def test_bare_path_fields_resolve_from_file_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "references").mkdir(parents=True)
            (root / "references" / "guide.txt").write_text("guide\n", encoding="utf-8")
            self.write_bundle(root, extra="sources: [{ resource: references/guide.txt }]\n")
            consumer, profile = self.both(root)
            self.assertIn("broken local link 'references/guide.txt'", consumer.stderr)
            self.assertEqual(profile.returncode, 1)

    def test_legacy_bare_path_fields_fall_back_to_bundle_root_for_consumers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "references").mkdir(parents=True)
            (root / "references" / "guide.txt").write_text("guide\n", encoding="utf-8")
            self.write_bundle(root, version="0.2", extra="sources: [{ resource: references/guide.txt }]\n")
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("resolves only from the bundle root", consumer.stderr)
            self.assertNotIn("broken local link", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("broken local link 'references/guide.txt'", profile.stderr)

    def test_attested_computation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_bundle(
                root,
                extra=(
                    "runtime: bigquery\n"
                    "parameters: { name: year }\n"
                    "executor: { resource: /references/run.txt, receipt: [job_id] }\n"
                    "attester: { resource: ../references/attest.py }\n"
                ),
            )
            concept.write_text(
                concept.read_text(encoding="utf-8").replace("type: Coverage Manifest", "type: Attested Computation"),
                encoding="utf-8",
            )
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("parameters[0].type", consumer.stderr)
            self.assertIn("not attestable", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("broken local link '/references/run.txt'", profile.stderr)
            self.assertIn("broken local link '../references/attest.py'", profile.stderr)

            (root / "references").mkdir()
            (root / "references" / "run.txt").write_text("run\n", encoding="utf-8")
            (root / "references" / "attest.py").write_text("pass\n", encoding="utf-8")
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "parameters: { name: year }", "parameters: { name: year, type: integer, required: true }"
                )
                + "\n## Computation\n\n```sql\nSELECT @year\n```\n",
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertEqual(consumer.stderr, "")

    def test_duplicate_frontmatter_keys_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_bundle(root, extra="title: Coverage again\n")
            consumer, profile = self.both(root)
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("repeats the key 'title'", consumer.stderr)
            self.assertEqual(profile.returncode, 1)


if __name__ == "__main__":
    unittest.main()
