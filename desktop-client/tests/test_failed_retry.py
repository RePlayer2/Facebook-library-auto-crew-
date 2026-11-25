import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
import create_and_copy_dated_folders as organize
import meta_ad_card_batch_by_ids as batch
import meta_material_client as client
from types import SimpleNamespace


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, library_id):
        folder = self.root / "source" / library_id / "广告素材文件/视频" / library_id
        folder.mkdir(parents=True)
        (folder / "素材信息.json").write_text(
            json.dumps({"资料库编号": library_id}), encoding="utf-8"
        )
        (folder / "广告视频.mp4").write_bytes(library_id.encode())
        return folder

    def test_retry_fills_original_gap_without_touching_success(self):
        self.source("101")
        self.source("103")
        target = self.root / "整理"
        kwargs = dict(prefix="115", reuse_existing=True, order_ids=["101", "102", "103"])
        organize.create_and_copy_cards_to_dated_folders(
            None, target, self.root / "source", ids=["101", "103"], **kwargs
        )
        before = (target / "115.1/广告视频.mp4").stat().st_mtime_ns
        self.assertTrue((target / "115.3/广告视频.mp4").exists())
        self.assertFalse((target / "115.2").exists())
        self.source("102")
        organize.create_and_copy_cards_to_dated_folders(
            None, target, self.root / "source", ids=["102"], **kwargs
        )
        self.assertEqual((target / "115.2/广告视频.mp4").read_bytes(), b"102")
        self.assertEqual((target / "115.1/广告视频.mp4").stat().st_mtime_ns, before)
        organize.create_and_copy_cards_to_dated_folders(
            None, target, self.root / "source", ids=["102"], **kwargs
        )
        self.assertEqual(len(list(target.glob("115.*"))), 3)

    def test_legacy_folder_matched_by_library_id(self):
        self.source("102")
        target = self.root / "整理"
        old = target / "114.9"
        old.mkdir(parents=True)
        (old / "素材信息.json").write_text('{"资料库编号": "102"}', encoding="utf-8")
        organize.create_and_copy_cards_to_dated_folders(
            None, target, self.root / "source", ids=["102"], prefix="115",
            reuse_existing=True, order_ids=["102"],
        )
        self.assertEqual((old / "广告视频.mp4").read_bytes(), b"102")
        self.assertFalse((target / "115.1").exists())

    def test_batch_persists_only_failed_ids(self):
        report = self.root / "report.json"
        args = argparse.Namespace(
            ids=["101", "102", "103"], ids_file=None, output_root=self.root,
            media_type="video", require_hd_video=False, dry_run=False,
            continue_on_error=True, report=report, download_images=True,
            concurrency=1,
        )
        with patch.object(batch, "parse_args", return_value=(args, [])), \
             patch.object(batch, "build_command", side_effect=lambda a, i, p: [i]), \
             patch.object(batch, "run_job", side_effect=[0, 1, 0]), \
             patch.object(batch, "validate_download"):
            self.assertEqual(batch.main(), 1)
        data = json.loads(report.read_text())
        self.assertEqual(data["succeeded"], ["101", "103"])
        self.assertEqual(data["failed"], ["102"])
        self.assertEqual(data["pending"], [])

    def test_download_validation_rejects_metadata_without_video(self):
        folder = self.root / "102"
        folder.mkdir()
        (folder / "广告素材.json").write_text(
            '[{"资料库编号":"102", "广告视频":"https://example.test/video.mp4"}]',
            encoding="utf-8",
        )
        args = SimpleNamespace(output_root=self.root, download_images=True, media_type="video")
        with self.assertRaises(ValueError):
            batch.validate_download(args, "102")

    def test_old_whole_batch_record_excludes_local_successes(self):
        folder = self.root / "素材爬取/101"
        folder.mkdir(parents=True)
        media = folder / "广告视频.mp4"
        media.write_bytes(b"saved-video")
        (folder / "广告素材.json").write_text(json.dumps([{
            "资料库编号": "101", "广告视频": "https://example.test/video",
            "广告视频本地文件": str(media),
        }]), encoding="utf-8")
        self.assertEqual(
            client.failed_ids_from_local_results(["101", "102"], self.root, "video"), ["102"]
        )

    def test_gui_partial_failure_advances_only_successful_ids(self):
        report = self.root / "report.json"
        report.write_text(json.dumps({
            "ids": ["101", "102", "103"], "succeeded": ["101", "103"],
            "failed": ["102"], "pending": [],
        }))
        saved = []
        advanced = []
        fake = SimpleNamespace(
            after=lambda delay, callback: callback(), workflow_report=report,
            workflow_ids=["101", "102", "103"],
            workflow_steps=["crawl", "organize", "summary"],
            config_data=SimpleNamespace(last_failed_ids=[]),
            store=SimpleNamespace(save=lambda config: saved.append(list(config.last_failed_ids))),
            log=lambda text: None, run_next_workflow_step=lambda: advanced.append(True),
        )
        client.MetaMaterialClient.on_task_done(fake, "资料库编号抓取", 1, "")
        self.assertEqual(fake.workflow_ids, ["101", "103"])
        self.assertEqual(saved[-1], ["102"])
        self.assertEqual(advanced, [True])
        report.write_text(json.dumps({
            "ids": ["102"], "succeeded": ["102"], "failed": [], "pending": [],
        }))
        fake.workflow_ids = ["102"]
        client.MetaMaterialClient.on_task_done(fake, "资料库编号抓取", 0, "")
        self.assertEqual(saved[-1], [])


if __name__ == "__main__":
    unittest.main()
