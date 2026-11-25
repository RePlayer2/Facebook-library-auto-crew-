import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
import meta_ad_card_batch_by_ids as batch


class ConcurrentBatchTests(unittest.TestCase):
    def test_limit_completion_barrier_and_ordered_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "result.json"
            args = SimpleNamespace(
                ids=["101", "102", "103", "104", "105"], ids_file=None,
                output_root=Path(directory), media_type="video", require_hd_video=False,
                report=report, dry_run=False, concurrency=2, continue_on_error=True,
            )
            lock = threading.Lock()
            active = 0
            peak = 0
            finished = []
            def job(command, library_id, *unused):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep(.12 if library_id == "101" else .025)
                with lock:
                    active -= 1
                    finished.append(library_id)
                return 1 if library_id == "103" else 0
            with patch.object(batch, "parse_args", return_value=(args, [])), \
                 patch.object(batch, "build_command", side_effect=lambda a, i, p: [i]), \
                 patch.object(batch, "run_job", side_effect=job), \
                 patch.object(batch, "validate_download"):
                self.assertEqual(batch.main(), 1)
            self.assertEqual(active, 0)
            self.assertEqual(peak, 2)
            self.assertEqual(len(finished), 5)
            self.assertNotEqual(finished, args.ids)
            data = json.loads(report.read_text())
            self.assertEqual(data["succeeded"], ["101", "102", "104", "105"])
            self.assertEqual(data["failed"], ["103"])
            self.assertEqual(data["pending"], [])

    def test_cli_default_and_upper_limit(self):
        with patch.object(sys, "argv", ["batch", "101"]):
            args, _ = batch.parse_args()
            self.assertEqual(args.concurrency, 2)
        with patch.object(sys, "argv", ["batch", "101", "--concurrency", "6"]):
            with self.assertRaises(SystemExit):
                batch.parse_args()

    def test_stop_terminates_workers_and_keeps_unstarted_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "runner.py"
            runner.write_text(
                "import sys,time\n"
                f"sys.path.insert(0, {str(Path(batch.__file__).parent)!r})\n"
                "import meta_ad_card_batch_by_ids as b\n"
                "b.build_command=lambda a,i,p: [sys.executable,'-c','import time;time.sleep(60)']\n"
                "raise SystemExit(b.main())\n"
            )
            report = root / "report.json"
            p = subprocess.Popen([
                sys.executable, str(runner), "101", "102", "103",
                "--report", str(report), "--concurrency", "2",
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                for _ in range(100):
                    if report.exists():
                        time.sleep(.2)
                        break
                    time.sleep(.02)
                p.send_signal(signal.SIGTERM)
                p.communicate(timeout=10)
                self.assertNotEqual(p.returncode, 0)
                data = json.loads(report.read_text())
                self.assertIn("103", data["pending"])
                self.assertFalse(data["succeeded"])
            finally:
                if p.poll() is None:
                    p.kill()
                    p.communicate()
