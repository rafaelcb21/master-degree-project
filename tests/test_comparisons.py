import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web/server'))
from compare_environments import build, compare_image, analyze, agreement, SOURCES, PAIR_IDS
from comparisons import Comparisons
from comparison_summaries import accuracy, summary_files, percent, decimal, FILES


def row(execution=1, name='A0001.raw', q=(10, 20), result=0, **changes):
    data = dict(execution=execution, name_image=name, quantized=list(q), scores=[v/256 for v in q],
        output_indices=[0, 1], result=result, invalid=0, label=0, ok=1, recovery_skipped=0,
        output_scope='full', source_file=f'{execution}/report.csv', prediction_usable=1)
    data.update(changes)
    return data


def dataset():
    runs, rows = [], []
    for execution, source in enumerate(SOURCES, 1):
        runtime, env = source.split('_')
        runs.append(dict(execution=execution, model='drowsiness', type=runtime, env=env,
                         folder=f'{source}/01', source_file=f'{source}/01/report.csv', derived=env=='esp32'))
        rows.append(row(execution, model='drowsiness', type=runtime, env=env))
    return dict(executions=runs, rows=rows, generated_at='original')


class ComparisonTests(unittest.TestCase):
    def test_summary_rounding_matches_display_at_half_values(self):
        self.assertEqual(percent(87.175), '87,18%')
        self.assertEqual(percent(87.325), '87,33%')
        self.assertEqual(decimal(4.13975, 3), '4,140')

    def test_accuracy_counts_each_source_once_and_uses_reference_labels(self):
        data = dataset()
        originals = list(data['rows'])
        for record in originals:
            for name, changes in [('correct1',dict(label=1,result=1)),
                ('wrong1',dict(label=1,result=0,right=1)),
                ('invalid1',dict(label=1,result=-1,invalid=1)),
                ('failed1',dict(label=1,result=1,ok=0)),
                ('unknown',dict(label=None,result=1))]:
                data['rows'].append(dict(record, name_image=name+'.raw', **changes))
        report = build(data)
        rows = accuracy(report)
        self.assertEqual(len(rows), 12)
        overall = next(r for r in rows if r['source']=='wasm_esp32' and r['class_label'] is None)
        self.assertEqual(overall['total'], 5)
        self.assertEqual(overall['correct'], 2)
        self.assertEqual(overall['accuracy_pct'], 40)
        self.assertEqual(overall['unknown_labels'], 1)
        target = next(r for r in rows if r['source']=='wasm_esp32' and r['class_label']==1)
        self.assertEqual(target['total'], 4)
        self.assertEqual(target['correct'], 1)
        self.assertEqual(target['incorrect_valid'], 1)
        self.assertEqual(target['no_valid_prediction'], 2)
        self.assertEqual(target['accuracy_pct'], 25)
        self.assertEqual(target['valid_accuracy_pct'], 50)
        files = summary_files(report)
        self.assertEqual(set(files), set(FILES))
        self.assertIn(b'25,00%', files['accuracy.csv'])
        stats_csv = list(csv.DictReader(io.StringIO(files['quantized_stats.csv'].decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(stats_csv), 6)
        self.assertEqual(stats_csv[0]['Δq = 0 (%)'], '100,00%')

    def test_agreement_uses_numeric_vectors_and_valid_class_denominators(self):
        images = [compare_image('same', [row()], [row()]),
                  compare_image('class_only', [row()], [row(result=1)]),
                  compare_image('invalid', [row(result=-1, invalid=1)], [row()]),
                  compare_image('missing', [], [row()])]
        result = agreement(dict(images=images, total=4))
        self.assertEqual(result['vector_equal'], 3)
        self.assertEqual(result['vector_agreement_pct'], 100)
        self.assertEqual(result['class_comparable'], 2)
        self.assertEqual(result['class_equal'], 1)
        self.assertEqual(result['class_not_comparable'], 2)
        self.assertEqual(result['class_agreement_pct'], 50)
        empty = agreement(dict(images=images[-1:], total=1))
        self.assertIsNone(empty['vector_agreement_pct'])
        self.assertIsNone(empty['class_agreement_pct'])

    def test_per_component_differences_and_interpolated_percentiles(self):
        item = compare_image('x', [row()], [row(q=(11, 31), result=1)])
        q = item['quantized']
        self.assertEqual(q['count'], 2)
        self.assertEqual(q['maximum'], 11)
        self.assertEqual(q['mean'], 6)
        self.assertEqual(q['median'], 6)
        self.assertAlmostEqual(q['p95'], 10.5)
        self.assertAlmostEqual(q['p99'], 10.9)
        self.assertEqual(q['buckets'], {'0':0,'1':1,'2–5':0,'6–10':0,'>10':1})
        self.assertAlmostEqual(item['scores']['mean'], 6/256)
        self.assertTrue(item['class_changed'])

    def test_alignment_by_index_not_vector_position(self):
        item = compare_image('x', [row()], [row(q=(20, 10), output_indices=[1, 0])])
        self.assertEqual(item['status'], 'equal')
        self.assertEqual(item['quantized']['buckets']['0'], 2)
        different = compare_image('x', [row()], [row(output_indices=[0, 2])])
        self.assertEqual(different['issues']['alignment'], 'different_indices')
        self.assertIsNone(different['quantized']['maximum'])

    def test_invalid_completed_outputs_are_numeric_not_class_changes(self):
        item = compare_image('x', [row(result=-1, invalid=1)], [row(result=0)])
        self.assertEqual(item['status'], 'different')
        self.assertIsNone(item['class_changed'])
        self.assertTrue(item['decision_changed'])
        self.assertEqual(item['quantized']['maximum'], 0)

    def test_missing_failed_duplicate_and_partial_do_not_become_zero(self):
        for left in ([], [row(ok=0)], [row(), row()], [row(quantized=[None, 20])], [row(scores=[0.1])]):
            item = compare_image('x', left, [row()])
            self.assertEqual(item['status'], 'not_comparable')
            self.assertEqual(item['quantized']['count'], 0)
            self.assertIsNone(item['scores']['mean'])

    def test_six_pairs_latest_default_and_explicit_desktop_execution(self):
        data = dataset()
        data['executions'].append(dict(execution=10, model='drowsiness',type='wasm',env='desktop',folder='wasm_desktop/02',source_file='new'))
        data['rows'].append(row(10, model='drowsiness',type='wasm',env='desktop',q=(11,31)))
        report = build(data)
        self.assertEqual([p['id'] for p in report['pairs']], PAIR_IDS)
        self.assertEqual(report['selected']['wasm_desktop']['execution'], 10)
        self.assertEqual(report['pairs'][0]['equal'], 1)
        self.assertEqual(report['pairs'][1]['different'], 1)
        selected = build(data, selections={'wasm_desktop':3})
        self.assertEqual(selected['pairs'][1]['equal'], 1)
        with self.assertRaises(ValueError):
            build(data, selections={'wasm_desktop':4})
        data['executions'][0]['derived'] = False
        with self.assertRaises(ValueError):
            build(data)

    def test_exact_case_join_and_aggregate_component_counts(self):
        data = dataset()
        data['rows'][1]['name_image'] = 'a0001.raw'
        report = build(data)
        first = report['pairs'][0]
        self.assertEqual(first['total'], 2)
        self.assertEqual(first['not_comparable'], 2)
        self.assertEqual(first['quantized']['count'], 0)
        self.assertEqual(report['pairs'][1]['quantized']['count'], 2)

    def test_saved_reports_downloads_pagination_staleness_and_failed_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'analysis').mkdir()
            data = dataset()
            data['rows'] = [dict(record, name_image=f'A{i:04}.raw') for record in data['rows'] for i in range(51)]
            path = root/'analysis/consolidated.json'
            path.write_text(json.dumps(data))
            analyze(root)
            service = Comparisons(root)
            self.assertEqual(service.query({})['matched'], 51)
            self.assertEqual(len(service.query({})['images']), 25)
            self.assertEqual(len(service.query({'page':['3']})['images']), 1)
            self.assertEqual(service.query({'search':['A0001']})['matched'], 1)
            self.assertEqual(service.query({'status':['different']})['matched'], 0)
            self.assertFalse(service.query({})['stale'])
            self.assertEqual(len(service.query({})['accuracy']), 12)
            for filename in FILES:
                self.assertTrue(service.download(filename))
            agreement_csv = list(csv.DictReader(io.StringIO(service.download('agreement.csv').decode('utf-8-sig')), delimiter=';'))
            self.assertEqual(len(agreement_csv), 6)
            self.assertEqual(agreement_csv[0]['Concordância vetorial'], '100,00%')
            self.assertEqual(agreement_csv[0]['Classes comparáveis'], '51')
            self.assertIn(b'WASM ESP32', service.download('agreement.md'))
            # Older saved reports gain agreement on read without regeneration.
            saved_path = root/'analysis/comparisons/report.json'
            saved = json.loads(saved_path.read_text())
            for pair in saved['pairs']:
                for key in agreement(pair):
                    pair.pop(key, None)
            saved_path.write_text(json.dumps(saved))
            self.assertEqual(service.query({})['pairs'][0]['class_agreement_pct'], 100)
            exported = list(csv.DictReader(io.StringIO(service.download(PAIR_IDS[0]+'.csv').decode('utf-8-sig')), delimiter=';'))
            self.assertEqual(len(exported), 51)
            self.assertEqual(exported[0]['left_scores'], '[0.0390625,0.078125]')
            self.assertEqual(exported[0]['quantized_count_0'], '2')
            for filename in ('../consolidated.json', 'unknown.csv'):
                with self.assertRaises(ValueError):
                    service.download(filename)
            before = service.download('report.json')
            with self.assertRaises(ValueError):
                analyze(root, selections={'wasm_desktop':999})
            self.assertEqual(service.download('report.json'), before)
            path.write_text(json.dumps(dict(data, generated_at='new')))
            self.assertTrue(service.query({})['stale'])


if __name__ == '__main__':
    unittest.main()
