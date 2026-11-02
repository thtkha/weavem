"""The first PyPI upload must be the original immutable GitHub a2 wheel."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError
import zipfile

from _support import workspace

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("promote_pypi_a2", ROOT / "scripts/promote-pypi-a2.py")
assert spec and spec.loader
promotion = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = promotion
spec.loader.exec_module(promotion)


class PromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = workspace("pypi-a2-")
        self.root = Path(self.temp.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        self.wheel = self.dist / promotion.WHEEL
        prefix = f"weavem-{promotion.VERSION}.dist-info/"
        self.metadata = (
            "Metadata-Version: 2.4\nName: weavem\nVersion: 0.1.0a2\n"
            "Requires-Python: <3.16,>=3.12\nLicense-Expression: Apache-2.0\n"
            "License-File: LICENSE\nLicense-File: NOTICE\nLicense-File: TRADEMARKS.md\n\n"
            "Original historical README.\n"
        )
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr(prefix + "METADATA", self.metadata)
            for name in ("LICENSE", "NOTICE", "TRADEMARKS.md"):
                archive.writestr(prefix + "licenses/" + name, "fixture")
        self.hash = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        self.pin = mock.patch.object(promotion, "WHEEL_SHA256", self.hash)
        self.pin.start()

    def tearDown(self) -> None:
        self.pin.stop()
        self.temp.cleanup()

    def published(self, **file_changes):
        file = {"filename": promotion.WHEEL, "digests": {"sha256": self.hash}, "yanked": False}
        file.update(file_changes)
        return {"info": {"name": "weavem", "version": "0.1.0a2"}, "urls": [file]}

    def add_manifest(self) -> str:
        path = self.dist / "SHA256SUMS"
        path.write_text(f"{self.hash}  {promotion.WHEEL}\n", encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_verify_preserves_original_wheel(self):
        before = self.wheel.read_bytes()
        result = promotion.verify(self.dist)
        self.assertEqual(result["sha256"], self.hash)
        self.assertEqual(self.wheel.read_bytes(), before)

    def test_verify_original_manifest_is_also_pinned(self):
        manifest_hash = self.add_manifest()
        with mock.patch.object(promotion, "MANIFEST_SHA256", manifest_hash):
            self.assertEqual(promotion.verify(self.dist, original=True)["sha256"], self.hash)
            (self.dist / "SHA256SUMS").write_text("changed")
            with self.assertRaisesRegex(promotion.PromotionError, "manifest differs"):
                promotion.verify(self.dist, original=True)

    def test_changed_wheel_and_matching_rewritten_manifest_still_fail(self):
        self.wheel.write_bytes(b"different bytes")
        self.add_manifest()
        with self.assertRaisesRegex(promotion.PromotionError, "pinned original"):
            promotion.verify(self.dist, original=True)

    def test_extra_assets_in_publication_directory_are_rejected(self):
        for name in ("SHA256SUMS", "extra.whl", "source.tar.gz", ".hidden"):
            with self.subTest(name=name):
                path = self.dist / name
                path.write_text("unexpected")
                with self.assertRaisesRegex(promotion.PromotionError, "unexpected files"):
                    promotion.verify(self.dist)
                path.unlink()

    def test_missing_or_renamed_wheel_is_rejected(self):
        self.wheel.rename(self.dist / "weavem-0.1.0a3-py3-none-any.whl")
        with self.assertRaisesRegex(promotion.PromotionError, "unexpected files"):
            promotion.verify(self.dist)

    def test_symlink_candidate_is_rejected(self):
        saved = self.root / "saved.whl"
        self.wheel.rename(saved)
        self.wheel.symlink_to(saved)
        with self.assertRaisesRegex(promotion.PromotionError, "regular files"):
            promotion.verify(self.dist)

    def test_wrong_metadata_and_missing_license_rejected_even_with_matching_test_pin(self):
        for change in ("version", "name", "license"):
            with self.subTest(change=change):
                prefix = f"weavem-{promotion.VERSION}.dist-info/"
                metadata = self.metadata.replace("0.1.0a2", "0.1.0a3") if change == "version" else self.metadata
                if change == "name":
                    metadata = metadata.replace("Name: weavem", "Name: other")
                with zipfile.ZipFile(self.wheel, "w") as archive:
                    archive.writestr(prefix + "METADATA", metadata)
                    for name in ("LICENSE", "NOTICE", "TRADEMARKS.md"):
                        if change != "license" or name != "NOTICE":
                            archive.writestr(prefix + "licenses/" + name, "fixture")
                with mock.patch.object(promotion, "WHEEL_SHA256", promotion.digest(self.wheel)):
                    with self.assertRaises(promotion.PromotionError):
                        promotion.verify(self.dist)

    def test_no_existing_pypi_release_needs_upload(self):
        self.assertTrue(promotion.needs_upload(None))

    def test_same_existing_release_is_noop(self):
        self.assertFalse(promotion.needs_upload(self.published()))

    def test_existing_pypi_conflicts_are_never_silently_skipped(self):
        wrong = [self.published(digests={"sha256": "0" * 64}),
                 self.published(filename="different.whl"), self.published(yanked=True),
                 {"info": {"name": "other", "version": "0.1.0a2"}, "urls": []},
                 {"info": {"name": "weavem", "version": "0.1.0a2"}, "urls": []}]
        extra = self.published()
        extra["urls"].append({"filename": "extra.tar.gz"})
        for data in [*wrong, extra]:
            with self.subTest(data=data):
                with self.assertRaises(promotion.PromotionError):
                    promotion.needs_upload(data)

    def test_pypi_request_404_is_not_confused_with_other_failures(self):
        with mock.patch.object(promotion, "urlopen", side_effect=HTTPError(promotion.PYPI_JSON, 404, "missing", {}, None)):
            self.assertIsNone(promotion.fetch_pypi())
        for error in (HTTPError(promotion.PYPI_JSON, 500, "bad", {}, None), URLError("secret diagnostic")):
            with mock.patch.object(promotion, "urlopen", side_effect=error):
                with self.assertRaises(promotion.PromotionError) as seen:
                    promotion.fetch_pypi()
                self.assertNotIn("secret diagnostic", str(seen.exception))

    def test_malformed_and_oversized_pypi_metadata_rejected(self):
        for body in (b"not json", b"[]", b"x" * (1024 * 1024 + 1)):
            with mock.patch.object(promotion, "urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(promotion.PromotionError):
                    promotion.fetch_pypi()

    def test_context_accepts_only_canonical_manual_main_dispatch(self):
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
               "GITHUB_REPOSITORY": promotion.REPOSITORY, "GITHUB_SERVER_URL": "https://github.com",
               "GITHUB_SHA": "current-main"}
        commands = ["https://github.com/thtkha/weavem.git", promotion.SOURCE_COMMIT, "current-main"]
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(promotion, "command", side_effect=commands):
            self.assertEqual(promotion.context(self.root)["source_commit"], promotion.SOURCE_COMMIT)
        for key, value in (("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_EVENT_NAME", "push"),
                           ("GITHUB_REF", "refs/tags/v0.1.0a2"), ("GITHUB_REF", "refs/heads/feature"),
                           ("GITHUB_REPOSITORY", "other/weavem"), ("GITHUB_SERVER_URL", "https://other.invalid")):
            with self.subTest(key=key, value=value), mock.patch.dict(os.environ, env | {key: value}, clear=True), mock.patch.object(promotion, "command") as cmd:
                with self.assertRaises(promotion.PromotionError):
                    promotion.context(self.root)
                cmd.assert_not_called()

    def test_context_rejects_wrong_origin_moved_tag_or_checkout(self):
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
               "GITHUB_REPOSITORY": promotion.REPOSITORY, "GITHUB_SERVER_URL": "https://github.com",
               "GITHUB_SHA": "current-main"}
        wrong = [["https://github.com/other/weavem"],
                 ["https://github.com/thtkha/weavem", "moved-tag"],
                 ["https://github.com/thtkha/weavem", promotion.SOURCE_COMMIT, "wrong-head"]]
        for values in wrong:
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(promotion, "command", side_effect=values):
                with self.assertRaises(promotion.PromotionError):
                    promotion.context(self.root)

    def test_download_rejects_wrong_release_or_extra_remote_assets_before_downloading(self):
        valid = {"tagName": promotion.TAG, "isDraft": False, "isPrerelease": True,
                 "assets": [{"name": promotion.WHEEL}, {"name": "SHA256SUMS"}]}
        args = argparse.Namespace(project=self.root, dist=self.root / "download", publish_dir=self.root / "publish")
        for release in (valid | {"tagName": "v0.1.0a3"}, valid | {"isDraft": True},
                        valid | {"assets": [*valid["assets"], {"name": "extra"}]}):
            with mock.patch.object(promotion, "context"), mock.patch.object(promotion, "command", return_value=json.dumps(release)) as cmd:
                with self.assertRaises(promotion.PromotionError):
                    promotion.download(args)
                self.assertEqual(cmd.call_count, 1)
                self.assertFalse(args.dist.exists())

    def test_status_writes_only_boolean_workflow_output(self):
        output = self.root / "output"
        with mock.patch.object(promotion, "fetch_pypi", return_value=self.published()):
            self.assertEqual(promotion.main(["pypi-status", "--github-output", str(output)]), 0)
        self.assertEqual(output.read_text(), "upload=false\n")

    def test_confirmation_waits_only_for_initial_404_then_verifies(self):
        with mock.patch.object(promotion, "fetch_pypi", side_effect=[None, self.published()]), mock.patch.object(promotion.time, "sleep") as sleep:
            self.assertEqual(promotion.main(["confirm-pypi"]), 0)
        sleep.assert_called_once_with(10)
        with mock.patch.object(promotion, "fetch_pypi", return_value=None), mock.patch.object(promotion.time, "sleep") as sleep:
            self.assertEqual(promotion.main(["confirm-pypi"]), 2)
        self.assertEqual(sleep.call_count, 8)


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github/workflows/publish-pypi.yml").read_text()

    def test_manual_main_canonical_repository_gate(self):
        triggers = self.text.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", triggers)
        self.assertNotIn("pull_request", triggers)
        self.assertNotIn("push:", triggers)
        self.assertIn("github.ref == 'refs/heads/main'", self.text)
        self.assertIn("github.repository == 'thtkha/weavem'", self.text)

    def test_oidc_limited_to_protected_publication_job(self):
        self.assertEqual(self.text.count("id-token: write"), 1)
        publication = self.text.split("\n  publish:\n")[1].split("\n  public-install:\n")[0]
        self.assertIn("id-token: write", publication)
        self.assertIn("name: pypi", publication)
        self.assertIn("github.event.repository.private == false", publication)
        self.assertIn("needs: [candidate, verify, native-consumer]", publication)
        self.assertIn("test \"$(gh api repos/thtkha/weavem --jq .private)\" = false", publication)

    def test_workflow_never_builds_or_replaces_original(self):
        for forbidden in ("pip wheel", "-m build", "--clobber", "release upload", "git tag "):
            self.assertNotIn(forbidden, self.text)
        self.assertIn("path: dist/*.whl", self.text)
        self.assertIn("packages-dir: dist/", self.text)
        self.assertIn("steps.existing.outputs.upload == 'true'", self.text)
        self.assertIn("pypa/gh-action-pypi-publish@7245906fb61fa33a13554f9d5fb856fe61758086", self.text)

    def test_all_supported_minors_and_isolated_consumer_gates(self):
        self.assertEqual(self.text.count("python: ['3.12', '3.13', '3.14', '3.15']"), 2)
        self.assertIn('"$RUNNER_TEMP/a2-wheel/bin/python" -I verify-installed-wheel.py', self.text)
        self.assertIn('"$RUNNER_TEMP/a2-consumer/bin/python" -I', self.text)
        self.assertIn("--index-url https://pypi.org/simple weavem==0.1.0a2", self.text)


if __name__ == "__main__":
    unittest.main()
