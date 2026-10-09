from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "doc-sync" / "scripts" / "validate_okf.py"


class ValidateOkfV02Tests(unittest.TestCase):
    def run_validator(self, bundle: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(bundle), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def write_v02_bundle(self, root: Path) -> Path:
        (root / "concepts").mkdir(parents=True)
        (root / "index.md").write_text(
            '---\nokf_version: "0.2"\n---\n\n# Index\n\n* [Coverage](concepts/coverage.md)\n',
            encoding="utf-8",
        )
        (root / "log.md").write_text("# Log\n\n## 2026-09-05\n\n* Created.\n", encoding="utf-8")
        concept = root / "concepts" / "coverage.md"
        concept.write_text(
            "---\n"
            "type: Coverage Manifest\n"
            "title: Coverage\n"
            "description: Maps maintained knowledge.\n"
            "generated: { by: 'process:doc-sync', at: '2026-09-05T10:00:00+08:00' }\n"
            "---\n\n# Coverage\n",
            encoding="utf-8",
        )
        return concept

    def test_v02_profile_accepts_typed_concept_without_legacy_timestamp_or_citations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_v02_bundle(root)
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_consumer_accepts_type_only_concept_without_generated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "index.md").write_text(
                '---\nokf_version: "0.2"\n---\n\n# Index\n\n* [Thing](thing.md)\n', encoding="utf-8"
            )
            (root / "thing.md").write_text("---\ntype: Vendor Concept\n---\n\n# Thing\n", encoding="utf-8")
            completed = self.run_validator(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_consumer_accepts_verified_list_but_warns_missing_source_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "verified:\n  - by: 'process:checker'\n    at: '2026-09-05T10:00:00Z'\n"
                    "sources:\n  - id: policy\n---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("sources[0].resource", completed.stderr)

    def test_v02_profile_requires_generated_by_and_timezone_aware_at(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "generated: { by: 'process:doc-sync', at: '2026-09-05T10:00:00+08:00' }",
                    "generated: { at: '2026-09-05T10:00:00' }",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("generated.by", completed.stderr)
            self.assertIn("generated.at", completed.stderr)

    def test_v02_known_metadata_is_warned_for_consumers_and_rejected_by_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "generated: { by: 'process:doc-sync', at: '2026-09-05T10:00:00+08:00' }",
                    "generated: invalid\nverified: [{ by: 'human:reviewer', at: '2026-09-05T10:00:00' }]\n"
                    "status: obsolete\nstale_after: '2026-09-05T10:00:00'\n"
                    "sources: [{ resource: 42, last_modified: '2026-09-05T10:00:00' }]",
                ),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("WARNING", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("generated", profile.stderr)
            self.assertIn("verified", profile.stderr)
            self.assertIn("status", profile.stderr)
            self.assertIn("stale_after", profile.stderr)
            self.assertIn("sources", profile.stderr)

    def test_v02_accepts_verified_bare_mapping_and_unknown_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "verified: { by: 'human:reviewer', at: '2026-09-05T10:00:00Z' }\n"
                    "x-vendor: { retain: true }\n---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_source_local_links_follow_consumer_and_producer_link_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources:\n  - resource: references/missing.md\n---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("broken local link", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("broken local link", profile.stderr)

    def test_v02_source_scope_descriptor_is_not_treated_as_a_broken_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources:\n  - resource: all queries in BigQuery project X\n---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_source_path_heuristic_distinguishes_descriptors_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources:\n  - resource: project.dataset.table\n"
                    "  - resource: references/missing file.md\n---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("references/missing file.md", consumer.stderr)
            self.assertNotIn("project.dataset.table", consumer.stderr)
            self.assertEqual(profile.returncode, 1)

    def test_v02_usage_windows_must_be_complete_ordered_and_cover_usage_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "usage_window: {}\n"
                    "sources:\n  - resource: https://example.com/one\n    usage_count: 1\n"
                    "  - resource: https://example.com/two\n    usage_window: { from: '2026-10-01T00:00:00Z', to: '2026-09-01T00:00:00Z' }\n"
                    "---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("usage_window.from", consumer.stderr)
            self.assertIn("usage_count requires", consumer.stderr)
            self.assertIn("must not be after", consumer.stderr)
            self.assertEqual(profile.returncode, 1)

    def test_v02_actor_convention_is_checked_for_generated_and_verified_only(self) -> None:
        valid_actors = ("human:reviewer", "process:nightly", "writer/v2")
        for actor in valid_actors:
            with self.subTest(actor=actor), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                concept = self.write_v02_bundle(root)
                concept.write_text(
                    concept.read_text(encoding="utf-8").replace(
                        "'process:doc-sync'", repr(actor),
                    ).replace(
                        "---\n\n# Coverage\n",
                        "verified: { by: '" + actor + "', at: '2026-09-05T10:00:00Z' }\n"
                        "sources: [{ resource: 'https://example.com', author: 'team:docs' }]\n---\n\n# Coverage\n",
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(self.run_validator(root, "--doc-sync-profile").returncode, 0)
        for actor in ("human:", "process:", "writer/", "bare"):
            with self.subTest(invalid_actor=actor), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                concept = self.write_v02_bundle(root)
                concept.write_text(
                    concept.read_text(encoding="utf-8").replace("'process:doc-sync'", repr(actor)),
                    encoding="utf-8",
                )
                consumer = self.run_validator(root)
                profile = self.run_validator(root, "--doc-sync-profile")
                self.assertEqual(consumer.returncode, 0)
                self.assertIn("actor", consumer.stderr)
                self.assertEqual(profile.returncode, 1)

    def test_v02_footnote_requires_definition_and_ignores_literal_or_image_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources: [{ id: policy, resource: 'https://example.com/policy' }]\n---\n\n"
                    "# Coverage\n\nClaim.[^policy]\nLiteral \\[^literal].\n![^image](image.png)\n[inline [^inline]](https://example.com)\n",
                ),
                encoding="utf-8",
            )
            missing = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(missing.returncode, 1)
            self.assertIn("policy", missing.stderr)
            concept.write_text(concept.read_text(encoding="utf-8") + "\n[^policy]: Policy source\n", encoding="utf-8")
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_individual_timestamp_values_are_not_masked_by_another_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "verified:\n  - by: 'human:valid'\n    at: '2026-09-05T10:00:00Z'\n"
                    "  - by: 'process:invalid'\n    at: '2026-09-05T10:00:00'\n"
                    "usage_window: { from: '2026-09-01T00:00:00Z', to: '2026-09-30T00:00:00Z' }\n"
                    "sources:\n  - resource: https://example.com/one\n    last_modified: '2026-09-01T00:00:00Z'\n"
                    "  - resource: https://example.com/two\n    last_modified: '2026-09-01T00:00:00'\n"
                    "    usage_window: { from: '2026-09-01T00:00:00Z', to: '2026-09-30T00:00:00' }\n"
                    "---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("verified[1].at", completed.stderr)
            self.assertIn("sources[1].last_modified", completed.stderr)
            self.assertIn("sources[1].usage_window.to", completed.stderr)

    def test_v02_known_null_and_container_shapes_warn_without_tracebacks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "generated: { by: 'process:doc-sync', at: '2026-09-05T10:00:00+08:00' }",
                    "generated: null\nverified: null\nsources: null\nstatus: []",
                ),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("WARNING", consumer.stderr)
            self.assertNotIn("Traceback", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertNotIn("Traceback", profile.stderr)

    def test_v02_attested_computation_runtime_is_checked_without_executing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace("type: Coverage Manifest", "type: Attested Computation"),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("runtime", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertIn("runtime", profile.stderr)

    def test_v02_source_ids_must_be_unique_and_used_footnotes_are_covered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources:\n  - id: policy\n    resource: https://example.com/one\n"
                    "  - id: policy\n    resource: https://example.com/two\n"
                    "---\n\n# Coverage\n\nClaim.[^missing]\n\n[^missing]: An ordinary note.\n",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("duplicate sources[].id", completed.stderr)

    def test_v02_profile_allows_source_id_without_a_claim_footnote(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources:\n  - id: policy\n    resource: https://example.com/policy\n"
                    "---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_footnotes_do_not_become_local_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources:\n  - id: policy\n    resource: https://example.com/policy\n"
                    "---\n\n# Coverage\n\nA sourced claim.[^policy]\n\n[^policy]: Policy source title\n",
                ),
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_direct_link_label_is_not_an_attribution_footnote(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8")
                + "\n[^ordinary-label](https://example.com/navigation)\n",
                encoding="utf-8",
            )
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_v02_malformed_source_url_reports_a_diagnostic_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            concept.write_text(
                concept.read_text(encoding="utf-8").replace(
                    "---\n\n# Coverage\n",
                    "sources: [{resource: 'https://[invalid'}]\n---\n\n# Coverage\n",
                ),
                encoding="utf-8",
            )
            consumer = self.run_validator(root)
            profile = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertIn("WARNING", consumer.stderr)
            self.assertEqual(profile.returncode, 1)
            self.assertNotIn("Traceback", profile.stderr)
            self.assertIn("invalid source resource", profile.stderr)

    def test_legacy_v01_profile_still_requires_legacy_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            concept = self.write_v02_bundle(root)
            index = root / "index.md"
            index.write_text(index.read_text(encoding="utf-8").replace('"0.2"', '"0.1"'), encoding="utf-8")
            completed = self.run_validator(root, "--doc-sync-profile")
            self.assertEqual(completed.returncode, 1)
            self.assertIn("timestamp", completed.stderr)


if __name__ == "__main__":
    unittest.main()
