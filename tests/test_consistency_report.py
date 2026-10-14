import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consistency_report import audit, consistency_files, prediction, vector, NONE
from compare_environments import build
from test_comparisons import dataset


class ConsistencyTests(unittest.TestCase):
    def test_invalid_class_is_not_recovered_from_vector(self):
        record = dict(ok=1, invalid=0, prediction_usable=0, result=0,
                      quantized=[0, 255], output_indices=[0, 1])
        self.assertEqual(prediction(record), NONE)
        self.assertEqual(vector(record), [0, 255])
        record.update(prediction_usable=1, invalid=1)
        self.assertEqual(prediction(record), NONE)
        record.update(invalid=0, result=-1)
        self.assertEqual(prediction(record), NONE)

    def test_both_absent_is_category_agreement_not_valid_class(self):
        data = dataset()
        for record in data['rows']:
            record.update(result=-1, invalid=1)
        report = build(data)
        report['generated_at'] = 'saved'
        result = audit(report)
        for pair in result['pairs']:
            self.assertEqual(pair['both_no_prediction'], 1)
            self.assertEqual(pair['both_incorrect'], 1)
            self.assertEqual(pair['both_wrong_valid'], 0)
            self.assertEqual(pair['same_valid_class'], 0)
            self.assertEqual(pair['same_category'], 1)
            self.assertEqual(pair['identical_quantized_vectors'], 1)
            self.assertEqual(pair['matrix'][2][2], 1)
        files = consistency_files(report)
        self.assertEqual(json.loads(files['consistency.json'])['total'], 1)

    def test_case_and_vector_alignment_are_preserved(self):
        data = dataset()
        for record in list(data['rows']):
            data['rows'].append(dict(record, name_image='a0001.raw', result=1, label=1))
        report = build(data)
        report['generated_at'] = 'saved'
        result = audit(report)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['sources'][0]['correct'], 2)
        self.assertEqual(vector(dict(ok=1, output_indices=[1, 0], quantized=[255, 0])), [0, 255])
        self.assertIsNone(vector(dict(ok=1, output_indices=[0], quantized=[255])))

    def test_saved_desktop_reconciles_accuracy_difference(self):
        path = Path(__file__).resolve().parents[1] / 'analysis/comparisons/report.json'
        if not path.exists():
            self.skipTest('Saved comparison report unavailable')
        report = json.loads(path.read_text(encoding='utf-8'))
        if [report['selected'][s]['execution'] for s in ('wasm_esp32', 'tflite_esp32', 'wasm_desktop', 'tflite_desktop')] != [51, 50, 9, 12]:
            self.skipTest('Different selected executions')
        result = audit(report)
        pair = next(p for p in result['pairs'] if p['id'] == 'wasm_desktop--tflite_desktop')
        self.assertEqual(pair['total'], 2000)
        self.assertEqual(pair['different_valid_class'], 23)
        self.assertEqual(pair['different_category'], 30)
        self.assertEqual(pair['any_no_prediction'], 7)
        self.assertEqual(pair['right_only_correct']-pair['left_only_correct'], 25)
        self.assertEqual(sum(map(sum, pair['matrix'])), 2000)
        sys.path.insert(0, str(path.parents[2] / 'web/server'))
        from comparisons import Comparisons
        api = Comparisons(path.parents[2])
        response = api.query({})
        self.assertEqual(len(response['consistency']), 6)
        self.assertEqual(len(response['images']), 25)
        download = api.download('consistency_images.csv').decode('utf-8-sig')
        self.assertIn('SEM_PREDICAO', download)
        self.assertEqual(len(download.splitlines()), 2001)


if __name__ == '__main__':
    unittest.main()
