from __future__ import annotations

import subprocess
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TEST_DIR.parent
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import progress_checkpoint  # noqa: E402


class ProgressCheckpointTests(unittest.TestCase):
    def make_repository(self, root):
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "task/save"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "SI Test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "si@example.invalid"], cwd=root, check=True)
        (root / "owned.txt").write_text("before\n", encoding="utf-8")
        (root / "unrelated.txt").write_text("baseline\n", encoding="utf-8")
        (root / ".gitignore").write_text(".selective-intelligence/\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "owned.txt", "unrelated.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)
        return root

    def test_preserves_unrelated_staged_and_unstaged_work_with_ignored_state(self):
        with tempfile.TemporaryDirectory(prefix="si-progress-selective-") as temporary:
            root = self.make_repository(Path(temporary))
            (root / "owned.txt").write_text("after\n", encoding="utf-8")
            (root / "unrelated.txt").write_text("staged change\n", encoding="utf-8")
            subprocess.run(["git", "add", "unrelated.txt"], cwd=root, check=True)
            (root / "unrelated.txt").write_text("staged plus later work\n", encoding="utf-8")
            staged_before = subprocess.check_output(["git", "show", ":unrelated.txt"], cwd=root)
            result = progress_checkpoint.save_checkpoint(
                root=root, outcome="Save the owned change", next_safe_action="Continue",
                paths=["owned.txt"], commit=True,
            )
            self.assertTrue(result["committed"])
            self.assertEqual(subprocess.check_output(["git", "show", "HEAD:unrelated.txt"], cwd=root), b"baseline\n")
            self.assertEqual(subprocess.check_output(["git", "show", ":unrelated.txt"], cwd=root), staged_before)
            self.assertEqual((root / "unrelated.txt").read_text(), "staged plus later work\n")
            self.assertEqual(subprocess.check_output(["git", "show", "HEAD:owned.txt"], cwd=root), b"after\n")
            self.assertEqual(subprocess.check_output(["git", "status", "--porcelain"], cwd=root).decode().splitlines(), ["MM unrelated.txt"])

    def test_selected_filename_is_literal_and_directory_selection_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="si-progress-literal-") as temporary:
            root = self.make_repository(Path(temporary))
            (root / "owned[1].txt").write_text("selected\n")
            (root / "owned1.txt").write_text("unrelated\n")
            progress_checkpoint.save_checkpoint(
                root=root, outcome="Save one literal filename", next_safe_action="Continue",
                paths=["owned[1].txt"], commit=True,
            )
            self.assertEqual(subprocess.check_output(["git", "show", "HEAD:owned[1].txt"], cwd=root), b"selected\n")
            self.assertIn("?? owned1.txt", subprocess.check_output(["git", "status", "--porcelain"], cwd=root).decode())
            (root / "folder").mkdir()
            with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                progress_checkpoint.save_checkpoint(
                    root=root, outcome="Save selected work", next_safe_action="Select files",
                    paths=["folder"], commit=True,
                )

    def test_unverified_accepted_push_keeps_an_honest_receipt(self):
        with tempfile.TemporaryDirectory(prefix="si-progress-remote-") as temporary:
            root = self.make_repository(Path(temporary) / "work")
            remote = Path(temporary) / "remote.git"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
            original_run = progress_checkpoint._run
            for verification in (
                subprocess.CompletedProcess([], 1, "", "verification unavailable"),
                subprocess.CompletedProcess([], 0, "0" * 40 + "\trefs/heads/task/save\n", ""),
            ):
                def unavailable(project_root, *args, **kwargs):
                    if args[:2] == ("git", "ls-remote"):
                        return verification
                    return original_run(project_root, *args, **kwargs)
                with patch.object(progress_checkpoint, "_run", side_effect=unavailable):
                    with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                        progress_checkpoint.save_checkpoint(
                            root=root, outcome="Save remotely", next_safe_action="Inspect remote state",
                            paths=["owned.txt"], commit=True, push=True,
                        )
                operation = json.loads((root / ".git/selective-intelligence/progress/last-operation.json").read_text())
                self.assertTrue(operation["committed"])
                self.assertTrue(operation["pushAccepted"])
                self.assertFalse(operation["pushed"])
                self.assertFalse(operation["remoteVerified"])
                remote_head = subprocess.check_output(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/task/save"]).decode().strip()
                self.assertEqual(remote_head, operation["commitSha"])

    def test_self_test_preserves_pushes_and_bounds_usage(self):
        result = progress_checkpoint.self_test()
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["checkpoint"]["committed"])
        self.assertTrue(result["checkpoint"]["pushed"])
        self.assertEqual(result["remoteHead"], result["checkpoint"]["commitSha"])
        self.assertTrue(result["checkpoint"]["remoteVerified"])
        self.assertEqual(result["checkpoint"]["remoteHead"], result["checkpoint"]["commitSha"])
        self.assertEqual(result["tracked"], [".selective-intelligence/progress/latest.json"])
        self.assertTrue(any(line.endswith(" unrelated.txt") for line in result["workingTree"]))
        self.assertEqual(result["usage"]["limits"]["filesPerBatch"], 12)
        self.assertEqual(result["usage"]["limits"]["bytesPerBatch"], 65_536)
        self.assertEqual(result["usage"]["limits"]["batchesBeforeDecision"], 3)

    def test_protected_branch_requires_exact_authority(self):
        with tempfile.TemporaryDirectory(prefix="si-progress-protected-") as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "SI Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "si@example.invalid"], cwd=root, check=True)
            (root / "owned.txt").write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "owned.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)
            (root / "owned.txt").write_text("after\n", encoding="utf-8")
            with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                progress_checkpoint.save_checkpoint(
                    root=root,
                    outcome="Do not checkpoint directly to main",
                    completed=["Owned file changed"],
                    next_safe_action="Move work to a task branch",
                    paths=["owned.txt"],
                    commit=True,
                )

    def test_release_branch_prefix_is_also_protected(self):
        with tempfile.TemporaryDirectory(prefix="si-progress-release-") as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-b", "release/1.0.7"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "SI Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "si@example.invalid"], cwd=root, check=True)
            (root / "owned.txt").write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "owned.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)
            (root / "owned.txt").write_text("after\n", encoding="utf-8")
            with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                progress_checkpoint.save_checkpoint(
                    root=root,
                    outcome="Do not checkpoint directly to a release branch",
                    completed=["Owned file changed"],
                    next_safe_action="Move work to a task branch",
                    paths=["owned.txt"],
                    commit=True,
                )

    def test_push_requires_commit(self):
        with tempfile.TemporaryDirectory(prefix="si-progress-no-git-") as temporary:
            with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                progress_checkpoint.save_checkpoint(
                    root=Path(temporary),
                    outcome="Invalid push request",
                    next_safe_action="Create a task branch",
                    push=True,
                )

    def test_usage_governor_blocks_fourth_batch_and_overlapping_owner(self):
        with tempfile.TemporaryDirectory(prefix="si-usage-") as temporary:
            root = self.make_repository(Path(temporary))
            progress_checkpoint.usage_start(root, "Inspect one bounded question")
            for index in range(3):
                status = progress_checkpoint.usage_record(
                    root,
                    kind="inspection",
                    question="Which module owns the public profile?",
                    owner="worker-1",
                    file_count=3,
                    byte_count=4096,
                    impact="proof",
                    result=f"batch {index + 1}",
                )
            self.assertTrue(status["decisionRequired"])
            with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                progress_checkpoint.usage_record(
                    root,
                    kind="search",
                    question="Which module owns the public profile?",
                    owner="worker-1",
                    file_count=1,
                    byte_count=100,
                    impact="proof",
                    result="fourth batch",
                )
            progress_checkpoint.usage_decide(root, action="narrow", summary="Use the selected route owner")
            with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                progress_checkpoint.usage_record(
                    root,
                    kind="inspection",
                    question="Which module owns the public profile?",
                    owner="worker-2",
                    file_count=1,
                    byte_count=100,
                    impact="proof",
                    result="duplicate owner",
                )

class CheckpointSelectionTests(unittest.TestCase):
    """Real local Git/filesystem and fresh CLI processes; no external services."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="si-resume-selection-")
        self.addCleanup(self.temporary.cleanup)
        self.root = ProgressCheckpointTests().make_repository(Path(self.temporary.name) / "work")
        self.tracked = self.root / ".selective-intelligence/progress/latest.json"
        self.private = progress_checkpoint._private_root(self.root, "progress") / "latest.json"

    def save(self, name, commit=False):
        return progress_checkpoint.save_checkpoint(
            root=self.root, outcome=name, next_safe_action="Continue " + name,
            completed=[name], paths=["owned.txt"], commit=commit,
        )

    def pair(self):
        tracked = self.save("committed milestone", commit=True)
        private = self.save("new local work")
        return tracked, private

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, path, record):
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def status(self):
        return progress_checkpoint.checkpoint_status(self.root)

    def snapshot(self):
        paths = [self.tracked, self.private, self.private.parent / "last-operation.json",
                 self.root / "owned.txt", self.root / "unrelated.txt", self.root / ".git/index"]
        return {str(path): path.read_bytes() for path in paths if path.is_file()}

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "progress_checkpoint.py"), *args,
             "--root", str(self.root)], capture_output=True, text=True, timeout=15,
        )

    def test_new_local_checkpoint_survives_a_fresh_cli_process(self):
        # All save/status calls cross real OS process boundaries.
        first = self.cli("save", "--outcome", "committed milestone", "--next", "Old next step",
                         "--path", "owned.txt", "--commit")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        second = self.cli("save", "--outcome", "new local work", "--next", "New next step",
                          "--path", "owned.txt")
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        local = json.loads(second.stdout)
        before = self.snapshot()
        result = self.cli("status")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        state = json.loads(result.stdout)
        self.assertEqual(state["latestCheckpoint"]["checkpointId"], local["checkpointId"])
        self.assertEqual(state["latestCheckpoint"]["progress"]["nextSafeAction"], "New next step")
        self.assertEqual(state["checkpointSource"], "private")
        self.assertFalse(state["checkpointExternalStateVerified"])
        self.assertEqual(self.snapshot(), before, "Reading status must preserve saved work and Git index")

    def test_newer_committed_checkpoint_supersedes_old_local_checkpoint(self):
        self.save("old local work")
        latest = self.save("later committed milestone", commit=True)
        self.assertEqual(self.status()["latestCheckpoint"]["checkpointId"], latest["checkpointId"])

    def test_private_only_checkpoint_is_still_readable(self):
        latest = self.save("local only")
        self.assertEqual(self.status()["latestCheckpoint"]["checkpointId"], latest["checkpointId"])

    def test_tracked_only_checkpoint_is_still_readable(self):
        latest = self.save("tracked only", commit=True)
        self.assertEqual(self.status()["latestCheckpoint"]["checkpointId"], latest["checkpointId"])

    def test_missing_checkpoint_does_not_invent_one(self):
        self.assertIsNone(self.status()["latestCheckpoint"])

    def test_non_git_project_keeps_one_local_checkpoint_location(self):
        root = Path(self.temporary.name) / "non-git"
        root.mkdir()
        saved = progress_checkpoint.save_checkpoint(
            root=root, outcome="local project", next_safe_action="Continue local project",
        )
        state = progress_checkpoint.checkpoint_status(root)
        self.assertEqual(state["latestCheckpoint"]["checkpointId"], saved["checkpointId"])
        self.assertIsNone(state["currentHead"])

    def test_filesystem_modification_time_does_not_override_record_time(self):
        import os
        _, latest = self.pair()
        os.utime(self.tracked, (2_000_000_000, 2_000_000_000))
        os.utime(self.private, (1, 1))
        self.assertEqual(self.status()["latestCheckpoint"]["checkpointId"], latest["checkpointId"])

    def test_timestamp_order_uses_actual_instant_not_lexical_offset(self):
        _, latest = self.pair()
        tracked, private = self.read(self.tracked), self.read(self.private)
        tracked["createdAt"] = "2026-10-14T17:59:59Z"
        private["createdAt"] = "2026-10-14T13:00:00-05:00"
        self.write(self.tracked, tracked)
        self.write(self.private, private)
        self.assertEqual(self.status()["latestCheckpoint"]["checkpointId"], latest["checkpointId"])

    def test_identical_records_prefer_the_tracked_copy(self):
        self.pair()
        self.private.write_bytes(self.tracked.read_bytes())
        state = self.status()
        self.assertEqual(state["latestCheckpoint"], self.read(self.tracked))
        self.assertEqual(state["checkpointSource"], "tracked")

    def test_equal_instant_with_different_records_requires_reconciliation(self):
        self.pair()
        tracked, private = self.read(self.tracked), self.read(self.private)
        tracked["createdAt"] = "2026-10-14T18:00:00+00:00"
        private["createdAt"] = "2026-10-14T13:00:00-05:00"
        self.write(self.tracked, tracked)
        self.write(self.private, private)
        before = self.snapshot()
        result = self.cli("status")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "error")
        self.assertEqual(self.snapshot(), before)

    def test_same_checkpoint_identity_with_changed_content_is_not_ranked_by_time(self):
        self.pair()
        private = self.read(self.private)
        private["checkpointId"] = self.read(self.tracked)["checkpointId"]
        self.write(self.private, private)
        with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
            self.status()

    def test_unreadable_private_record_is_not_hidden_by_a_tracked_record(self):
        self.pair()
        self.private.write_text("not-json\n", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
            self.status()
        self.assertEqual(self.snapshot(), before)

    def test_unreadable_tracked_record_is_not_hidden_by_a_newer_private_record(self):
        self.pair()
        self.tracked.write_text("not-json\n", encoding="utf-8")
        with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
            self.status()

    def test_unorderable_timestamps_are_not_guessed(self):
        self.pair()
        original = self.read(self.private)
        for timestamp in [None, 7, "bad-time", "2026-10-14T18:00:00", "2026-10-14"]:
            with self.subTest(timestamp=timestamp):
                private = dict(original)
                private["createdAt"] = timestamp
                self.write(self.private, private)
                with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                    self.status()

    def test_private_record_from_another_branch_cannot_be_silently_resumed(self):
        self.pair()
        subprocess.run(["git", "switch", "-c", "task/other"], cwd=self.root,
                       capture_output=True, check=True)
        before = self.snapshot()
        with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
            self.status()
        self.assertEqual(self.snapshot(), before)

    def test_symlink_checkpoint_is_not_followed_or_treated_as_absent(self):
        self.pair()
        target = Path(self.temporary.name) / "outside.json"
        target.write_bytes(self.private.read_bytes())
        self.private.unlink()
        try:
            self.private.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Host cannot create symlinks: {exc}")
        for exists in [True, False]:
            with self.subTest(target_exists=exists):
                if not exists:
                    target.unlink()
                with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
                    self.status()

    def test_non_file_checkpoint_is_not_silently_ignored(self):
        self.pair()
        self.private.unlink()
        self.private.mkdir()
        with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
            self.status()

    def test_detached_head_cannot_adopt_a_branch_bound_private_record(self):
        self.pair()
        subprocess.run(["git", "switch", "--detach"], cwd=self.root,
                       capture_output=True, check=True)
        with self.assertRaises(progress_checkpoint.ProgressCheckpointError):
            self.status()


if __name__ == "__main__":
    unittest.main()
