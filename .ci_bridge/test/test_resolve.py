from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


RESOLVER_PATH = Path(__file__).parents[1] / "resolve.py"
SPEC = importlib.util.spec_from_file_location("ci_bridge_resolve", RESOLVER_PATH)
assert SPEC is not None and SPEC.loader is not None
RESOLVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RESOLVER
SPEC.loader.exec_module(RESOLVER)


CATALOG = """\
schema_version = 1

[action]
id = "test"
description = "Run tests"
required_bindings = ["script"]
"""

PROJECT = """\
schema_version = 1

pipeline = ["test"]

[bindings.test]
script = "test/run.sh"
"""


class ResolverTest(unittest.TestCase):
    def make_repo(self) -> Path:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        (root / ".ci_action" / "catalog").mkdir(parents=True)
        (root / "test").mkdir()
        (root / ".ci_action" / "catalog" / "test.toml").write_text(CATALOG)
        (root / "ci-project.toml").write_text(PROJECT)
        script = root / "test" / "run.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        return root

    def assert_config_error(self, expected: str, callback) -> None:
        with self.assertRaises(RESOLVER.ConfigError) as raised:
            callback()
        self.assertIn(expected, str(raised.exception))

    def test_resolves_managed_action_to_downstream_script(self) -> None:
        root = self.make_repo()

        plan = RESOLVER.build_plan(root, "pipeline", "ci")

        self.assertEqual(
            [(task.action_id, str(task.script)) for task in plan],
            [("test", "test/run.sh")],
        )

    def test_empty_pipeline_fails_closed(self) -> None:
        root = self.make_repo()
        (root / "ci-project.toml").write_text(PROJECT.replace('["test"]', "[]"))

        self.assert_config_error(
            "pipeline must select at least one action",
            lambda: RESOLVER.build_plan(root, "pipeline", "ci"),
        )

    def test_duplicate_action_id_fails_closed(self) -> None:
        root = self.make_repo()
        (root / ".ci_action" / "catalog" / "duplicate.toml").write_text(CATALOG)

        self.assert_config_error(
            "duplicate action id 'test'",
            lambda: RESOLVER.build_plan(root, "pipeline", "ci"),
        )

    def test_unknown_catalog_key_fails_closed(self) -> None:
        root = self.make_repo()
        source = root / ".ci_action" / "catalog" / "test.toml"
        source.write_text(CATALOG + "\nunsafe = true\n")

        self.assert_config_error(
            "unknown key(s): unsafe",
            lambda: RESOLVER.build_plan(root, "pipeline", "ci"),
        )

    def test_unused_unknown_binding_fails_closed(self) -> None:
        root = self.make_repo()
        project = root / "ci-project.toml"
        project.write_text(PROJECT + '\n[bindings.unknown]\nscript = "test/run.sh"\n')

        self.assert_config_error(
            "binding names unknown action: unknown",
            lambda: RESOLVER.build_plan(root, "pipeline", "ci"),
        )

    def test_plan_delimiter_in_script_path_fails_closed(self) -> None:
        root = self.make_repo()
        (root / "ci-project.toml").write_text(
            PROJECT.replace('"test/run.sh"', '"test/run.sh\\tsecond"')
        )

        self.assert_config_error(
            "forbidden control character",
            lambda: RESOLVER.build_plan(root, "pipeline", "ci"),
        )

    def test_script_cannot_escape_repository(self) -> None:
        root = self.make_repo()
        (root / "ci-project.toml").write_text(
            PROJECT.replace('"test/run.sh"', '"../outside.sh"')
        )

        self.assert_config_error(
            "repo-relative path without '..'",
            lambda: RESOLVER.build_plan(root, "pipeline", "ci"),
        )

if __name__ == "__main__":
    unittest.main()
