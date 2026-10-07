import json
import os
import sys
import unittest

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE, 'src'))
sys.path.insert(0, os.path.join(BASE, 'scripts'))

from sklearn import metrics as skm

from evaluation.dataset import DatasetValidator
from evaluation.metrics import calculate_metrics, confusion_matrix, cohen_kappa
from extraction.prefilter import PrivacyPrefilter
import run_classification_evaluation as rce


class TestKappaAndConfusionMatrix(unittest.TestCase):
    def test_kappa_matches_sklearn(self):
        cases = [
            ([1, 0, 1, 0], [1, 0, 1, 0]),
            ([1, 1, 1, 0, 0, 0], [1, 1, 0, 1, 0, 0]),
            ([1, 1, 0, 0, 1, 0, 1, 0], [0, 1, 0, 1, 1, 0, 0, 0]),
            ([1, 0, 1, 0], [0, 1, 0, 1]),            # perfect disagreement -> negative kappa
        ]
        for a, b in cases:
            self.assertAlmostEqual(cohen_kappa(a, b), skm.cohen_kappa_score(a, b), places=12)

    def test_kappa_hand_computed(self):
        a = [1, 1, 1, 0, 0, 0, 1, 0]
        b = [1, 1, 0, 0, 0, 1, 1, 0]
        po = 6 / 8
        pe = 0.5 * 0.5 + 0.5 * 0.5
        self.assertAlmostEqual(cohen_kappa(a, b), (po - pe) / (1 - pe))

    def test_kappa_undefined_cases(self):
        self.assertIsNone(cohen_kappa([], []))
        self.assertIsNone(cohen_kappa([1, 1, 1], [1, 1, 1]))   # pe == 1
        with self.assertRaises(ValueError):
            cohen_kappa([1, 0], [1])

    def test_confusion_matrix_layout_and_consistency(self):
        y_true = [1, 1, 1, 0, 0, 0, 0]
        y_pred = [1, 1, 0, 1, 0, 0, 0]
        cm = confusion_matrix(y_true, y_pred)
        m = calculate_metrics(y_true, y_pred)
        self.assertEqual(cm, [[m["TP"], m["FN"]], [m["FP"], m["TN"]]])
        self.assertEqual(cm, [[2, 1], [1, 3]])
        # sklearn orders labels [0, 1] -> [[TN, FP], [FN, TP]]
        sk = skm.confusion_matrix(y_true, y_pred, labels=[0, 1])
        self.assertEqual((sk[1][1], sk[1][0], sk[0][1], sk[0][0]), (cm[0][0], cm[0][1], cm[1][0], cm[1][1]))


class TestFortyClauseDataset(unittest.TestCase):
    def setUp(self):
        self.validator = DatasetValidator(rce.GT_40)
        self.data = self.validator.load_dataset()
        self.ex = self.data["examples"]

    def test_exactly_40_with_both_classes(self):
        stats = self.validator.validate_all()
        self.assertEqual(stats["total"], 40)
        self.assertGreater(stats["positive"], 0)
        self.assertGreater(stats["negative"], 0)
        self.assertEqual(stats["positive"] + stats["negative"], 40)

    def test_unique_ids_and_texts_and_labels(self):
        self.assertEqual(len({e["id"] for e in self.ex}), 40)
        self.assertEqual(len({rce.norm(e["text"]) for e in self.ex}), 40)
        self.assertTrue(all(e["label"] in (0, 1) for e in self.ex))

    def test_no_overlap_with_real_training_fixture(self):
        class Cap(PrivacyPrefilter):
            def train(self, texts, labels):
                self.captured = list(texts)
                super().train(texts, labels)
        pf = Cap()
        pf.train_with_minimal_fixture()
        train = {rce.norm(t) for t in pf.captured}
        self.assertEqual(len(train), 8)
        for e in self.ex:
            self.assertNotIn(rce.norm(e["text"]), train)

    def test_no_overlap_with_dev_set(self):
        with open(rce.GT_DEV, encoding="utf-8") as f:
            dev = {rce.norm(e["text"]) for e in json.load(f)["examples"]}
        for e in self.ex:
            self.assertNotIn(rce.norm(e["text"]), dev)

    def test_full_validation_routine(self):
        _, checks = rce.validate_dataset()
        self.assertEqual(checks["exact_overlap_with_training_fixture"], 0)

    def test_annotator_b_template_is_blind_and_complete(self):
        with open(os.path.join(rce.EVAL_DIR, "annotator_b_template.json"), encoding="utf-8") as f:
            t = json.load(f)
        self.assertEqual([e["id"] for e in t["examples"]], [e["id"] for e in self.ex])
        self.assertTrue(all(e["label"] is None for e in t["examples"]))


class TestEvaluationWorkflow(unittest.TestCase):
    def _run(self):
        import io, contextlib
        sys_argv = sys.argv
        sys.argv = ["run_classification_evaluation.py", "--no-write"]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                return rce.main()
        finally:
            sys.argv = sys_argv

    def test_metric_consistency(self):
        r = self._run()
        m = r["primary_metrics"]
        self.assertEqual(m["TP"] + m["TN"] + m["FP"] + m["FN"], 40)
        self.assertEqual(r["confusion_matrix"]["matrix"], [[m["TP"], m["FN"]], [m["FP"], m["TN"]]])
        self.assertAlmostEqual(m["Precision"], m["TP"] / (m["TP"] + m["FP"]))
        self.assertAlmostEqual(m["Recall"], m["TP"] / (m["TP"] + m["FN"]))
        self.assertAlmostEqual(m["F1"], 2 * m["Precision"] * m["Recall"] / (m["Precision"] + m["Recall"]))

    def test_matches_sklearn_on_real_predictions(self):
        r = self._run()
        y_true = [e["label"] for e in DatasetValidator(rce.GT_40).load_dataset()["examples"]]
        y_pred = [p["prefilter_pred"] for p in r["per_clause_predictions"]]
        m = r["primary_metrics"]
        self.assertAlmostEqual(m["Precision"], skm.precision_score(y_true, y_pred))
        self.assertAlmostEqual(m["Recall"], skm.recall_score(y_true, y_pred))
        self.assertAlmostEqual(m["F1"], skm.f1_score(y_true, y_pred))
        self.assertAlmostEqual(r["cohen_kappa_reference_vs_prediction"]["kappa"], skm.cohen_kappa_score(y_true, y_pred))
        tn, fp, fn, tp = skm.confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        self.assertEqual((m["TP"], m["TN"], m["FP"], m["FN"]), (tp, tn, fp, fn))

    def test_predictions_come_from_prefilter_and_are_deterministic(self):
        texts = [e["text"] for e in DatasetValidator(rce.GT_40).load_dataset()["examples"]]
        pf = PrivacyPrefilter()
        pf.train_with_minimal_fixture()
        direct = [1 if pf.filter_candidates([t]) else 0 for t in texts]
        self.assertEqual(direct, rce.predict_prefilter(texts))
        self.assertEqual(rce.predict_prefilter(texts), rce.predict_prefilter(texts))

    def test_inter_annotator_kappa_not_fabricated(self):
        r = self._run()
        iaa = r["cohen_kappa_inter_annotator"]
        if not os.path.exists(rce.ANNOTATOR_B):
            self.assertEqual(iaa["status"], "NOT COMPUTED")
        self.assertIn("NOT inter-annotator", r["cohen_kappa_reference_vs_prediction"]["meaning"])

    def test_inter_annotator_path_works_with_a_complete_second_file(self):
        import tempfile
        ex = DatasetValidator(rce.GT_40).load_dataset()["examples"]
        ids = [e["id"] for e in ex]
        y_a = [e["label"] for e in ex]
        y_b = list(y_a)
        y_b[0] = 1 - y_b[0]          # synthetic file used ONLY to exercise the code path in this test
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"annotator": "TEST", "examples": [{"id": i, "label": l} for i, l in zip(ids, y_b)]}, f)
        try:
            res = rce.inter_annotator(ids, y_a, f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual(res["status"], "COMPUTED")
        self.assertAlmostEqual(res["kappa"], skm.cohen_kappa_score(y_a, y_b))
        self.assertEqual(res["disagreements"], 1)


if __name__ == '__main__':
    unittest.main()
