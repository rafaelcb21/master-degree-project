import csv
import io
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from esp32_consensus import select_image
from consolidate_reports import consolidate
from test_consolidate_reports import ConsolidationTests
from representative_reports import ESP32Consensus


def row(execution, q=(10, 20), **changes):
    data = dict(execution=execution, quantized=list(q), scores=[v/256 for v in q],
                output_indices=[0, 1], result=0, ok=1, label=0, recovery_skipped=0,
                source_file=f'{execution}/report.csv')
    data.update(changes)
    return data


class SelectionTests(unittest.TestCase):
    def test_plurality_uses_whole_vector_and_earliest_matching_run(self):
        selected = select_image([row(4), row(3, (11, 19)), row(2, (12, 18)), row(1)])
        self.assertEqual(selected['status'], 'mode')
        self.assertEqual(selected['votes'], 2)
        self.assertEqual(selected['observations'], 4)
        self.assertEqual(selected['winner']['execution'], 1)
        self.assertEqual(selected['variant_count'], 3)

    def test_tie_does_not_choose_prediction_even_if_class_is_same(self):
        selected = select_image([row(1), row(2, (11, 19))])
        self.assertEqual(selected['status'], 'tie')
        self.assertIsNone(selected['winner'])

    def test_exclude_duplicates_failed_skipped_and_incomplete(self):
        selected = select_image([row(1), row(1), row(2, ok=0), row(3, recovery_skipped=1),
                                 row(4, quantized=[None, 20]), row(5)])
        self.assertEqual(selected['status'], 'single')
        self.assertEqual(selected['winner']['execution'], 5)
        self.assertEqual(selected['excluded_executions'], [1, 2, 3, 4])
        self.assertEqual(selected['duplicate_executions'], [1])

    def test_conflicting_identity_is_unresolved(self):
        for field in ['model_sha256', 'input_sha256', 'output_scale', 'width']:
            selected = select_image([row(1, _identity={field:'a'}), row(2, _identity={field:'b'})])
            self.assertEqual(selected['status'], 'conflict')
            self.assertIn(field, selected['conflicts'])
            self.assertIsNone(selected['winner'])
        self.assertEqual(select_image([row(1), row(2, label=1)])['status'], 'conflict')

    def test_equal_invalid_output_is_preserved_and_missing_hashes_are_disclosed(self):
        selected = select_image([row(1, result=-1), row(2, result=-1)])
        self.assertEqual(selected['status'], 'equal')
        self.assertEqual(selected['winner']['result'], -1)
        self.assertFalse(selected['input_identity_verified'])


class IntegrationTests(ConsolidationTests):
    def test_new_reports_drive_consolidation_and_raw_evidence_survives(self):
        paths = []
        for run, q, timing in [('one', '10,20', 30), ('two', '11,19', 20), ('three', '10,20', 40)]:
            paths.append(self.write(f'ESP32/host/reports/{run}/report.csv',
                'name_image,ok,class_0_raw,class_1_raw,result,label,right,inference_ms\n'
                f'A0001_suffix.raw,1,{q},0,0,1,{timing}\n'
                f'a0001_suffix.raw,1,{q},0,0,1,{timing}\n'))
        originals = [path.read_bytes() for path in paths]
        data = consolidate(self.root)
        self.assertEqual(len(data['rows']), 2)
        self.assertEqual(len(data['raw_rows']), 6)
        self.assertEqual(len(data['executions']), 1)
        self.assertEqual(len(data['raw_executions']), 3)
        self.assertEqual(data['rows'][0]['quantized'], [10, 20])
        self.assertEqual(data['rows'][0]['inference_ms'], 30)
        self.assertEqual(data['rows'][0]['consensus_votes'], 2)
        self.assertTrue(data['rows'][0]['source_file'].startswith('analysis/esp32_consensus/'))
        self.assertEqual([path.read_bytes() for path in paths], originals)
        service = ESP32Consensus(self.root)
        report = service.query({'search':['A0001'], 'status':['mode']})
        self.assertEqual(report['matched'], 2)
        content, filename = service.download({'group':['drowsiness/tflite']})
        exported = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        self.assertEqual([r['name_image'] for r in exported], ['A0001.raw', 'a0001.raw'])
        self.assertEqual(exported[0]['class_0_raw'], '10')
        self.assertEqual(float(exported[0]['inference_ms']), 30)
        with self.assertRaises(ValueError):
            service.download({'file':['../../config.json']})
        with self.assertRaises(ValueError):
            service.download({'group':['../../config']})
        # Reads saved reports; source files need not remain accessible for navigation.
        for path in paths:
            path.unlink()
        self.assertEqual(service.query({})['matched'], 2)

    def test_tie_is_exported_as_unusable_without_arbitrary_output(self):
        for run, q in [('one', '10,20'), ('two', '11,19')]:
            self.write(f'ESP32/host/reports/{run}/report.csv',
                'name_image,ok,class_0_raw,class_1_raw,result\n'
                f'x_suffix.raw,1,{q},0\n')
        data = consolidate(self.root)
        self.assertEqual(data['rows'][0]['consensus_status'], 'tie')
        self.assertEqual(data['rows'][0]['prediction_usable'], 0)
        self.assertIsNone(data['rows'][0]['quantized'])
        report = ESP32Consensus(self.root).query({})
        self.assertEqual(report['groups'][0]['unresolved'], 1)

    def test_partial_output_does_not_abort_generation_or_vote(self):
        self.write('ESP32/host/reports/one/report.csv',
            'name_image,ok,class_0_raw,class_1_raw,result\nx.raw,1,10,,0\n')
        self.write('ESP32/host/reports/two/report.csv',
            'name_image,ok,class_0_raw,class_1_raw,result\nx.raw,1,10,20,0\n')
        data = consolidate(self.root)
        self.assertEqual(data['rows'][0]['consensus_status'], 'single')
        self.assertEqual(data['rows'][0]['consensus_observations'], 1)


if __name__ == '__main__':
    unittest.main()
