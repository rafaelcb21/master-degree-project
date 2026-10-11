import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_determinism import compare_group, analyze, statistics, buckets
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web/server"))
from determinism import Determinism


def sample(execution, q=None, scores=None, **extra):
    return dict(execution=execution, quantized=q if q is not None else [255., 0.],
                scores=scores if scores is not None else [255/256, 0.], ok=1, **extra)


class DeterminismTests(unittest.TestCase):
    key = ("drowsiness", "wasm", "desktop", "a0002.raw")

    def test_web_regeneration_includes_new_partial_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "analysis").mkdir()
            (root / "analysis/config.json").write_text(json.dumps({"esp32_projects": {
                "host": {"model":"drowsiness", "type":"wasm", "output_scale":1/256, "output_zero_point":0}}}))
            def save_run(folder, q):
                path = root / "ESP32/host/reports" / folder / "report.csv"
                path.parent.mkdir(parents=True)
                path.write_text(f"name_image,ok,class_0_raw,class_1_raw,result\na0969_suffix.raw,1,{q},68,1\n")
            save_run("01", 187)
            save_run("02", 68)
            service = Determinism(root)
            self.assertEqual(service.rebuild()["images"][0]["observations"], 2)
            save_run("03", 187)
            save_run("04", 187)
            # Browsing stays cached; explicit generation discovers both new runs.
            self.assertEqual(service.query({})["images"][0]["observations"], 2)
            updated = service.rebuild()["images"][0]
            saved = json.loads((root / "analysis/consolidated.json").read_text(encoding="utf-8"))
            source_ids = [run["execution"] for run in saved["raw_executions"]]
            self.assertEqual(updated["compared_executions"], source_ids)
            self.assertEqual(len(source_ids), 4)
            self.assertNotIn(saved["executions"][0]["execution"], source_ids)
            self.assertEqual(updated["pairs"], 6)
            self.assertEqual(updated["quantized_differences"]["maximum"], 119)

    def test_exact_repeatability_includes_invalid_outputs(self):
        result = compare_group(self.key, [sample(i, invalid=1) for i in range(1, 5)], {1, 2, 3, 4})
        self.assertEqual(result["status"], "equal")
        self.assertEqual(result["pairs"], 6)
        self.assertEqual(result["quantized_different_pairs"], 0)
        self.assertEqual(result["invalid_observations"], 4)

    def test_separate_score_differences_without_tolerance(self):
        result = compare_group(self.key, [sample(1), sample(2), sample(3, scores=[255/256, 1e-12])], {1, 2, 3})
        self.assertEqual(result["status"], "different")
        self.assertTrue(result["quantized_equal"])
        self.assertFalse(result["scores_equal"])
        self.assertEqual(result["scores_different_pairs"], 2)
        self.assertEqual(result["scores_variants"][0]["executions"], [1, 2])
        self.assertEqual(result["scores_variants"][1]["executions"], [3])

    def test_missing_failed_skipped_duplicate_are_not_repeats(self):
        failed = sample(2)
        failed["ok"] = 0
        result = compare_group(self.key, [sample(1), failed, sample(3, recovery_skipped=1), sample(4), sample(4)], {1, 2, 3, 4, 5})
        self.assertEqual(result["status"], "insufficient")
        self.assertIsNone(result["quantized_equal"])
        self.assertEqual(result["missing_executions"], [5])
        self.assertEqual(result["excluded_executions"], [2, 3])
        self.assertEqual(result["duplicate_executions"], [4])
        self.assertFalse(result["complete"])

    def test_ranking_change_without_numeric_change(self):
        a = sample(1, q=[[1, 5.], [2, 5.]], scores=[[1, .5], [2, .5]], ranking=[1, 2])
        b = sample(2, q=a["quantized"], scores=a["scores"], ranking=[2, 1])
        result = compare_group(self.key, [a, b], {1, 2})
        self.assertTrue(result["quantized_equal"])
        self.assertTrue(result["scores_equal"])
        self.assertFalse(result["ranking_equal"])
        self.assertEqual(result["status"], "different")

    def test_percentiles_and_all_quantized_buckets(self):
        stats = statistics(Counter([0, 1, 2, 5, 6, 10, 11]))
        self.assertEqual(stats["maximum"], 11)
        self.assertEqual(stats["mean"], 5)
        self.assertEqual(stats["median"], 5)
        self.assertAlmostEqual(stats["p95"], 10.7)
        self.assertAlmostEqual(stats["p99"], 10.94)
        self.assertEqual(buckets(stats), {"0":1, "1":1, "2–5":2, "6–10":2, ">10":1})
        self.assertIsNone(statistics(Counter())["maximum"])

    def test_all_pairs_and_class_changes(self):
        result = compare_group(self.key, [sample(1,q=[0,0],result=1),sample(2,q=[1,2],result=1),sample(3,q=[3,2],result=0)],{1,2,3})
        stats=result["quantized_differences"]
        self.assertEqual(stats["count"],6)
        self.assertEqual(stats["maximum"],3)
        self.assertAlmostEqual(stats["mean"],10/6)
        self.assertEqual(stats["median"],2)
        self.assertEqual(stats["p95"],2.75)
        self.assertTrue(result["class_changed"])
        self.assertTrue(result["decision_changed"])
        unchanged=compare_group(self.key,[sample(1,result=1),sample(2,q=[254,1],result=1)],{1,2})
        self.assertFalse(unchanged["class_changed"])
        invalid=compare_group(self.key,[sample(1,result=1),sample(2,result=None,invalid=1)],{1,2})
        self.assertIsNone(invalid["class_changed"])
        self.assertTrue(invalid["decision_changed"])

    def test_top15_missing_classes_are_not_zero_filled(self):
        result=compare_group(self.key,[sample(1,q=[[1,10],[2,5]],scores=[[1,.5],[2,.1]],ranking=[1,2]),
                                       sample(2,q=[[1,12],[3,9]],scores=[[1,.6],[3,.2]],ranking=[1,3])],{1,2})
        self.assertEqual(result["quantized_differences"]["count"],1)
        self.assertEqual(result["quantized_differences"]["maximum"],2)
        self.assertEqual(result["quantized_differences"]["unmatched_components"],2)
        self.assertFalse(result["class_changed"])

    def test_environments_and_image_case_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "analysis").mkdir()
            runs, rows = [], []
            for execution, env in [(1, "desktop"), (2, "desktop"), (3, "esp32"), (4, "esp32")]:
                runs.append(dict(execution=execution, model="drowsiness", type="wasm", env=env, folder=f"runs/{execution}"))
                for name in ("A0002.raw", "a0002.raw"):
                    rows.append(dict(sample(execution, q=[int(env == "esp32"), 0], scores=[float(env == "esp32"), 0]), model="drowsiness", type="wasm", env=env, name_image=name))
            (root / "analysis/consolidated.json").write_text(json.dumps(dict(generated_at="saved", rows=rows, executions=runs)))
            (root / "analysis/mobilenet_top15.json").write_text(json.dumps(dict(generated_at="saved", rows=[], executions=[])))
            result = analyze(root)
            self.assertEqual(len(result["images"]), 4)
            self.assertTrue(all(r["status"] == "equal" for r in result["images"]))
            self.assertTrue((root / "analysis/determinism/report.md").is_file())


if __name__ == "__main__":
    unittest.main()
