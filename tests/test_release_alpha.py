"""Focused invariants for the immutable alpha-release helper."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import zipfile

from _support import workspace


SCRIPT = Path(__file__).parents[1] / "scripts" / "release-alpha.py"
spec = importlib.util.spec_from_file_location("release_alpha", SCRIPT)
assert spec and spec.loader
release_alpha = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = release_alpha
spec.loader.exec_module(release_alpha)


class ReleaseAlphaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = workspace("release-alpha-")
        self.root = Path(self.temp.name)
        (self.root / "pyproject.toml").write_text("[project]\nname = 'weavem'\nversion = '0.1.0a1'\n", encoding="utf-8")
        self.dist = self.root / "dist"
        self.dist.mkdir()
        self.wheel = self.dist / "weavem-0.1.0a1-py3-none-any.whl"
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr("weavem-0.1.0a1.dist-info/METADATA", "Metadata-Version: 2.1\nName: weavem\nVersion: 0.1.0a1\n")
        self.digest = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        (self.dist / "SHA256SUMS").write_text(f"{self.digest}  {self.wheel.name}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_prepare_writes_canonical_checksum(self) -> None:
        (self.dist / "SHA256SUMS").unlink()
        self.assertEqual(release_alpha.main(["prepare", "--project", str(self.root), "--dist", str(self.dist), "--tag", "v0.1.0a1"]), 0)
        self.assertEqual((self.dist / "SHA256SUMS").read_text(), f"{self.digest}  {self.wheel.name}\n")

    def test_check_rejects_nonalpha_tag_and_version_mismatch(self) -> None:
        for tag in ("v0.1.0", "0.1.0a1", "v0.1.0a2"):
            self.assertEqual(release_alpha.main(["--project", str(self.root), "--dist", str(self.dist), "--tag", tag, "check"]), 2)

    def test_check_rejects_changed_checksum_and_multiple_wheels(self) -> None:
        (self.dist / "SHA256SUMS").write_text("0" * 64 + f"  {self.wheel.name}\n")
        self.assertEqual(release_alpha.main(["--project", str(self.root), "--dist", str(self.dist), "check"]), 2)
        (self.dist / "SHA256SUMS").write_text(f"{self.digest}  {self.wheel.name}\n")
        (self.dist / "second.whl").write_bytes(b"not relevant")
        self.assertEqual(release_alpha.main(["--project", str(self.root), "--dist", str(self.dist), "check"]), 2)

    def test_metadata_body_cannot_spoof_name_or_version(self) -> None:
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr(
                "weavem-0.1.0a1.dist-info/METADATA",
                "Name: weavem\nVersion: 0.1.0a1\n\nName: another-project\nVersion: 9.9.9\n",
            )
        digest = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        (self.dist / "SHA256SUMS").write_text(f"{digest}  {self.wheel.name}\n")
        self.assertEqual(release_alpha.main(["check", "--project", str(self.root), "--dist", str(self.dist)]), 0)

    def test_check_rejects_non_universal_candidate_filename(self) -> None:
        renamed = self.dist / "weavem-0.1.0a1-cp312-cp312-linux_x86_64.whl"
        self.wheel.rename(renamed)
        digest = hashlib.sha256(renamed.read_bytes()).hexdigest()
        (self.dist / "SHA256SUMS").write_text(f"{digest}  {renamed.name}\n")
        self.assertEqual(release_alpha.main(["check", "--project", str(self.root), "--dist", str(self.dist)]), 2)

    def test_check_rejects_metadata_version_mismatch(self) -> None:
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr("weavem-0.1.0a1.dist-info/METADATA", "Name: weavem\nVersion: 0.1.0\n")
        digest = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        (self.dist / "SHA256SUMS").write_text(f"{digest}  {self.wheel.name}\n")
        self.assertEqual(release_alpha.main(["--project", str(self.root), "--dist", str(self.dist), "check"]), 2)

    @mock.patch.dict("os.environ", {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/tags/v0.1.0a1"}, clear=True)
    def test_publish_rejects_non_tag_push_before_gh(self) -> None:
        with mock.patch.object(release_alpha, "run") as runner:
            self.assertEqual(release_alpha.main(["--project", str(self.root), "--dist", str(self.dist), "--tag", "v0.1.0a1", "publish"]), 2)
        runner.assert_not_called()

    def test_existing_assets_rejects_conflicts(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        release = {"tagName": "v0.1.0a1", "assets": [{"name": "other.whl"}]}
        with workspace("release-alpha-assets-") as temp:
            with self.assertRaisesRegex(release_alpha.ReleaseError, "unexpected assets"):
                release_alpha.verify_existing_assets(release, candidate, Path(temp))

    def test_existing_assets_are_downloaded_and_verified_for_retry(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        release = {"tagName": "v0.1.0a1", "assets": [{"name": self.wheel.name}, {"name": "SHA256SUMS"}]}
        with workspace("release-alpha-assets-") as temp:
            target = Path(temp)
            def fake_download(tag: str, name: str, digest: str, directory: Path) -> None:
                source = self.dist / name
                (directory / name).write_bytes(source.read_bytes())
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), digest)
            with mock.patch.object(release_alpha, "download_and_verify", side_effect=fake_download) as download:
                present = release_alpha.verify_existing_assets(release, candidate, target)
        self.assertEqual(present, {self.wheel.name, "SHA256SUMS"})
        self.assertEqual(download.call_count, 2)

    def _publish_args(self) -> argparse.Namespace:
        return argparse.Namespace(dist=self.dist, project=self.root, tag="v0.1.0a1")

    def test_publish_fresh_draft_uploads_then_verifies_before_publish(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        draft = {"tagName": "v0.1.0a1", "isDraft": True, "isPrerelease": True, "targetCommitish": "main", "body": "- Source commit: `abc`\n- CI run: https://github.com/acme/weavem/actions/runs/1", "assets": []}
        complete = {**draft, "assets": [{"name": candidate.wheel.name}, {"name": "SHA256SUMS"}]}
        with mock.patch.object(release_alpha, "validate_publication_context", return_value="abc"), \
             mock.patch.object(release_alpha, "gh_release", side_effect=[None, draft, complete]), \
             mock.patch.object(release_alpha, "verify_existing_assets", side_effect=[set(), {candidate.wheel.name, "SHA256SUMS"}]), \
             mock.patch.object(release_alpha, "run") as runner, \
             mock.patch.dict("os.environ", {"WEAVEM_ARTIFACTS_DIR": str(self.root / ".artifacts"), "GITHUB_REPOSITORY": "acme/weavem"}, clear=False):
            self.assertEqual(release_alpha.publish(self._publish_args()), 0)
        commands = [call.args for call in runner.call_args_list]
        self.assertTrue(any(command[0:3] == ("gh", "release", "create") and "--verify-tag" in command for command in commands))
        self.assertEqual(sum(command[0:3] == ("gh", "release", "upload") for command in commands), 2)
        self.assertTrue(any(command[0:3] == ("gh", "release", "edit") for command in commands))

    def test_publish_resumes_partial_draft_without_replacing_existing_asset(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        draft = {"tagName": "v0.1.0a1", "isDraft": True, "isPrerelease": True, "targetCommitish": "main", "body": "- Source commit: `abc`\n- CI run: https://github.com/acme/weavem/actions/runs/1", "assets": [{"name": candidate.wheel.name}]}
        complete = {**draft, "assets": [{"name": candidate.wheel.name}, {"name": "SHA256SUMS"}]}
        with mock.patch.object(release_alpha, "validate_publication_context", return_value="abc"), \
             mock.patch.object(release_alpha, "gh_release", side_effect=[draft, complete]), \
             mock.patch.object(release_alpha, "verify_existing_assets", side_effect=[{candidate.wheel.name}, {candidate.wheel.name, "SHA256SUMS"}]), \
             mock.patch.object(release_alpha, "run") as runner, \
             mock.patch.dict("os.environ", {"WEAVEM_ARTIFACTS_DIR": str(self.root / ".artifacts"), "GITHUB_REPOSITORY": "acme/weavem"}, clear=False):
            self.assertEqual(release_alpha.publish(self._publish_args()), 0)
        uploads = [call.args for call in runner.call_args_list if call.args[0:3] == ("gh", "release", "upload")]
        self.assertEqual(len(uploads), 1)
        self.assertTrue(uploads[0][-1].endswith("SHA256SUMS"))

    def test_publish_matching_published_release_is_a_noop(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        published = {"tagName": "v0.1.0a1", "isDraft": False, "isPrerelease": True, "targetCommitish": "main", "body": "- Source commit: `abc`\n- CI run: https://github.com/acme/weavem/actions/runs/1", "assets": [{"name": candidate.wheel.name}, {"name": "SHA256SUMS"}]}
        with mock.patch.object(release_alpha, "validate_publication_context", return_value="abc"), \
             mock.patch.object(release_alpha, "gh_release", side_effect=[published, published]), \
             mock.patch.object(release_alpha, "verify_existing_assets", side_effect=[{candidate.wheel.name, "SHA256SUMS"}] * 2), \
             mock.patch.object(release_alpha, "run") as runner, \
             mock.patch.dict("os.environ", {"WEAVEM_ARTIFACTS_DIR": str(self.root / ".artifacts")}, clear=False):
            self.assertEqual(release_alpha.publish(self._publish_args()), 0)
        runner.assert_not_called()

    def test_publish_conflict_or_incomplete_release_never_uploads(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        published = {"tagName": "v0.1.0a1", "isDraft": False, "isPrerelease": True, "targetCommitish": "main", "body": "- Source commit: `abc`\n- CI run: https://github.com/acme/weavem/actions/runs/1", "assets": []}
        for failure in (release_alpha.ReleaseError("unexpected assets"), None):
            with self.subTest(failure=failure), \
                 mock.patch.object(release_alpha, "validate_publication_context", return_value="abc"), \
                 mock.patch.object(release_alpha, "gh_release", return_value=published), \
                 mock.patch.object(release_alpha, "verify_existing_assets", side_effect=failure or [{candidate.wheel.name}]), \
                 mock.patch.object(release_alpha, "run") as runner, \
                 mock.patch.dict("os.environ", {"WEAVEM_ARTIFACTS_DIR": str(self.root / ".artifacts")}, clear=False):
                with self.assertRaises(release_alpha.ReleaseError):
                    release_alpha.publish(self._publish_args())
            self.assertFalse(any(call.args[0:3] == ("gh", "release", "upload") for call in runner.call_args_list))

    def test_publish_draft_with_missing_final_asset_never_publishes(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        draft = {"tagName": "v0.1.0a1", "isDraft": True, "isPrerelease": True, "targetCommitish": "main", "body": "- Source commit: `abc`\n- CI run: https://github.com/acme/weavem/actions/runs/1", "assets": []}
        with mock.patch.object(release_alpha, "validate_publication_context", return_value="abc"), \
             mock.patch.object(release_alpha, "gh_release", side_effect=[draft, draft]), \
             mock.patch.object(release_alpha, "verify_existing_assets", side_effect=[set(), {candidate.wheel.name}]), \
             mock.patch.object(release_alpha, "run") as runner, \
             mock.patch.dict("os.environ", {"WEAVEM_ARTIFACTS_DIR": str(self.root / ".artifacts"), "GITHUB_REPOSITORY": "acme/weavem"}, clear=False):
            with self.assertRaisesRegex(release_alpha.ReleaseError, "incomplete"):
                release_alpha.publish(self._publish_args())
        self.assertFalse(any(call.args[0:3] == ("gh", "release", "edit") for call in runner.call_args_list))

    def test_release_lookup_finds_draft_and_rejects_duplicate_tags(self) -> None:
        draft = {"tag_name": "v0.1.0a1", "draft": True, "prerelease": True, "target_commitish": "abc", "assets": [], "html_url": "https://example/release"}
        response = subprocess.CompletedProcess([], 0, json.dumps(draft) + "\n", "")
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "acme/weavem"}, clear=True), \
             mock.patch.object(release_alpha, "run", return_value=response):
            release = release_alpha.gh_release("v0.1.0a1")
        self.assertTrue(release["isDraft"])
        duplicate = subprocess.CompletedProcess([], 0, json.dumps(draft) + "\n" + json.dumps(draft) + "\n", "")
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "acme/weavem"}, clear=True), \
             mock.patch.object(release_alpha, "run", return_value=duplicate):
            with self.assertRaisesRegex(release_alpha.ReleaseError, "multiple releases"):
                release_alpha.gh_release("v0.1.0a1")

    def test_github_api_500_and_git_sha_mismatch_stop_before_mutation(self) -> None:
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "acme/weavem"}, clear=True), \
             mock.patch.object(release_alpha, "run", return_value=subprocess.CompletedProcess([], 1, "", "HTTP 500")) as runner:
            with self.assertRaisesRegex(release_alpha.ReleaseError, "could not inspect"):
                release_alpha.gh_release("v0.1.0a1")
        self.assertEqual(runner.call_count, 1)
        with mock.patch.dict("os.environ", {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/tags/v0.1.0a1", "GITHUB_SHA": "wrong"}, clear=True), \
             mock.patch.object(release_alpha, "git", side_effect=["head", "head", "tag-object"]), \
             mock.patch.object(release_alpha, "run") as runner:
            with self.assertRaisesRegex(release_alpha.ReleaseError, "GITHUB_SHA"):
                release_alpha.validate_publication_context("v0.1.0a1", self.root)
        runner.assert_not_called()

    def test_publication_rejects_commit_outside_main(self) -> None:
        with mock.patch.dict("os.environ", {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/tags/v0.1.0a1"}, clear=True), \
             mock.patch.object(release_alpha, "git", side_effect=["head", "head"]), \
             mock.patch.object(release_alpha, "run", side_effect=release_alpha.ReleaseError("not on main")) as runner:
            with self.assertRaisesRegex(release_alpha.ReleaseError, "not on main"):
                release_alpha.validate_publication_context("v0.1.0a1", self.root)
        runner.assert_called_once_with("git", "merge-base", "--is-ancestor", "head", "origin/main", cwd=self.root)

    def test_publication_requires_private_repository(self) -> None:
        env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/tags/v0.1.0a1", "GITHUB_REPOSITORY": "acme/weavem"}
        for private in ("true", "false"):
            with self.subTest(private=private), \
                 mock.patch.dict("os.environ", env, clear=True), \
                 mock.patch.object(release_alpha, "git", side_effect=["head", "head"]), \
                 mock.patch.object(release_alpha, "run", side_effect=[subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 0, private, "")]):
                if private == "true":
                    self.assertEqual(release_alpha.validate_publication_context("v0.1.0a1", self.root), "head")
                else:
                    with self.assertRaisesRegex(release_alpha.ReleaseError, "private"):
                        release_alpha.validate_publication_context("v0.1.0a1", self.root)

    def test_notes_include_sha_and_ci_url(self) -> None:
        candidate = release_alpha.validate_candidate(self.dist, self.root, "v0.1.0a1", require_checksums=True)
        with mock.patch.dict("os.environ", {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "acme/weavem", "GITHUB_RUN_ID": "42"}, clear=True):
            notes = release_alpha.release_notes(candidate, "v0.1.0a1", "abcdef")
        self.assertIn("abcdef", notes)
        self.assertIn("https://github.com/acme/weavem/actions/runs/42", notes)
        self.assertIn("pip install", notes)


if __name__ == "__main__":
    unittest.main()
