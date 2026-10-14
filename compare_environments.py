"""Compare matching images across four runtime/environment sources."""
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import json
import math

from consolidate_reports import ROOT, LOCK, atomic_write, csv_bytes, read_json
from analyze_determinism import statistics, buckets

SOURCES = ('wasm_esp32', 'tflite_esp32', 'wasm_desktop', 'tflite_desktop')
PAIRS = [('wasm_esp32', 'tflite_esp32'), ('wasm_desktop', 'tflite_desktop'),
         ('wasm_esp32', 'tflite_desktop'), ('wasm_desktop', 'tflite_esp32'),
         ('wasm_esp32', 'wasm_desktop'), ('tflite_desktop', 'tflite_esp32')]
PAIR_IDS = ['--'.join(pair) for pair in PAIRS]
METRICS = ('count', 'maximum', 'mean', 'median', 'p95', 'p99')
BUCKETS = ('0', '1', '2–5', '6–10', '>10')
SOURCE_NAMES = {'wasm_esp32':'WASM ESP32', 'tflite_esp32':'TFLite ESP32',
                'wasm_desktop':'WASM desktop', 'tflite_desktop':'TFLite desktop'}


def agreement(pair):
    """Numeric vector agreement and class agreement have separate denominators."""
    items = [i for i in pair['images'] if i['status'] != 'not_comparable']
    vector_equal = sum(i['quantized']['maximum'] == 0 and i['scores']['maximum'] == 0 for i in items)
    class_comparable = sum(i['class_changed'] is not None for i in items)
    class_equal = sum(i['class_changed'] is False for i in items)
    return dict(vector_comparable=len(items), vector_equal=vector_equal,
        vector_different=len(items)-vector_equal,
        vector_agreement_pct=100*vector_equal/len(items) if items else None,
        class_comparable=class_comparable, class_equal=class_equal,
        class_not_comparable=pair['total']-class_comparable,
        class_agreement_pct=100*class_equal/class_comparable if class_comparable else None)


def agreement_files(report):
    rows = []
    def percent(value):
        return f'{value:.2f}%'.replace('.', ',') if value is not None else '—'
    for pair in report['pairs']:
        a = agreement(pair)
        rows.append({'Comparação':f"{SOURCE_NAMES[pair['left']]} × {SOURCE_NAMES[pair['right']]}",
            'Vetores diferentes':a['vector_different'], 'Vetores idênticos':a['vector_equal'],
            'Concordância vetorial':percent(a['vector_agreement_pct']),
            'Trocas de classe':pair['class_changes'], 'Concordância de classe':percent(a['class_agreement_pct']),
            'Imagens totais':pair['total'], 'Vetores comparáveis':a['vector_comparable'],
            'Vetores não comparáveis':pair['total']-a['vector_comparable'],
            'Classes comparáveis':a['class_comparable'], 'Classes idênticas':a['class_equal'],
            'Classes não comparáveis':a['class_not_comparable'],
            'Execução esquerda':report['selected'][pair['left']]['execution'],
            'Execução direita':report['selected'][pair['right']]['execution']})
    columns = list(rows[0]) if rows else []
    visible = columns[:6]
    generated = datetime.fromisoformat(report['generated_at']).astimezone(timezone(timedelta(hours=-3)))
    lines = ['# Resumo de concordância', '', f"Gerado em: {generated.strftime('%d/%m/%Y %H:%M:%S')} (UTC−03:00)", '',
        '| ' + ' | '.join(visible) + ' |', '| ' + ' | '.join(['---']*len(visible)) + ' |']
    lines += ['| ' + ' | '.join(str(row[key]) for key in visible) + ' |' for row in rows]
    lines += ['', 'Concordância vetorial = vetores numericamente idênticos / vetores comparáveis. Compara quantized e scores, independentemente da decisão registrada.',
        'Concordância de classe = classes idênticas / pares com vetores comparáveis e classes válidas nos dois lados. Saídas inválidas, empates e pares não comparáveis são excluídos desse denominador.', '',
        '## Cobertura e fontes', '', '| Comparação | Vetores comparáveis | Classes comparáveis | Classes não comparáveis | Execução esquerda | Execução direita |',
        '| --- | --- | --- | --- | --- | --- |']
    lines += ['| ' + ' | '.join(str(row[key]) for key in ('Comparação','Vetores comparáveis','Classes comparáveis','Classes não comparáveis','Execução esquerda','Execução direita')) + ' |' for row in rows]
    return {'agreement.csv':csv_bytes(columns, rows), 'agreement.md':('\n'.join(lines)+'\n').encode('utf-8')}


def stats(values, quantized=False):
    result = statistics(Counter(values))
    if quantized:
        result['buckets'] = buckets(result)
    return result


def reason(record):
    if record is None:
        return 'missing'
    if record.get('ok') != 1 or record.get('recovery_skipped') == 1:
        return 'failed_or_unresolved'
    if record.get('output_scope') != 'full':
        return 'not_full_vector'
    q, scores = record.get('quantized'), record.get('scores')
    if not isinstance(q, list) or not isinstance(scores, list) or not q or len(q) != len(scores):
        return 'incomplete_vector'
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in q + scores):
        return 'incomplete_vector'
    if any(not float(v).is_integer() for v in q):
        return 'non_integer_quantized'
    indices = record.get('output_indices')
    if indices is None or len(indices) != len(q) or len(set(indices)) != len(indices):
        return 'invalid_indices'
    return None


def side(record):
    if record is None:
        return None
    return {key: record.get(key) for key in ('execution', 'source_file', 'quantized', 'scores',
            'output_indices', 'result', 'label', 'prediction_usable', 'ok', 'invalid',
            'consensus_status', 'consensus_votes', 'consensus_observations', 'selected_execution')}


def decision(record):
    if record.get('result') == -1 or record.get('invalid') == 1:
        return ('invalid', None)
    if record.get('result') is not None:
        return ('class', record['result'])
    return ('unknown', None)


def compare_image(name, left_records, right_records):
    left = left_records[0] if len(left_records) == 1 else None
    right = right_records[0] if len(right_records) == 1 else None
    issues = {}
    for key, record, records in [('left', left, left_records), ('right', right, right_records)]:
        issue = 'duplicate' if len(records) > 1 else reason(record)
        if issue:
            issues[key] = issue
    if not issues and set(left['output_indices']) != set(right['output_indices']):
        issues['alignment'] = 'different_indices'
    result = dict(name_image=name, left=side(left), right=side(right), issues=issues,
                  status='not_comparable', class_changed=None, decision_changed=None,
                  label_conflict=bool(left and right and left.get('label') is not None and
                      right.get('label') is not None and left['label'] != right['label']),
                  components=[], quantized=stats([], True), scores=stats([]))
    if issues:
        return result
    a = {index: (q, s) for index, q, s in zip(left['output_indices'], left['quantized'], left['scores'])}
    b = {index: (q, s) for index, q, s in zip(right['output_indices'], right['quantized'], right['scores'])}
    result['components'] = [dict(index=index, left_q=a[index][0], right_q=b[index][0],
        left_score=a[index][1], right_score=b[index][1],
        difference_q=abs(a[index][0]-b[index][0]), difference_score=abs(a[index][1]-b[index][1]))
        for index in sorted(a)]
    result['quantized'] = stats([c['difference_q'] for c in result['components']], True)
    result['scores'] = stats([c['difference_score'] for c in result['components']])
    first, second = decision(left), decision(right)
    if first[0] == second[0] == 'class':
        result['class_changed'] = first[1] != second[1]
    if 'unknown' not in (first[0], second[0]):
        result['decision_changed'] = first != second
    result['status'] = 'equal' if result['quantized']['maximum'] == result['scores']['maximum'] == 0 and first == second else 'different'
    return result


def options(data, model):
    return {source: sorted([run for run in data['executions'] if run['model'] == model and
        f"{run['type']}_{run['env']}" == source], key=lambda r: (r['folder'], r['execution']))
        for source in SOURCES}


def build(data, model='drowsiness', selections=None):
    available = options(data, model)
    selections = selections or {}
    if set(selections) - set(SOURCES):
        raise ValueError('Unknown comparison source')
    selected = {}
    for source, runs in available.items():
        if not runs:
            raise ValueError(f'No execution available for {model}: {source}')
        requested = selections.get(source)
        chosen = next((run for run in runs if str(run['execution']) == str(requested)), None) if requested is not None else runs[-1]
        if chosen is None:
            raise ValueError(f'Unknown execution for {source}')
        if source.endswith('esp32') and not chosen.get('derived'):
            raise ValueError('ESP32 requires representative reports; regenerate consolidation')
        selected[source] = chosen
    records = {source: defaultdict(list) for source in SOURCES}
    for record in data['rows']:
        source = f"{record['type']}_{record['env']}"
        if source in selected and record['model'] == model and record['execution'] == selected[source]['execution']:
            records[source][record['name_image']].append(record)
    pairs = []
    for left, right in PAIRS:
        names = sorted(set(records[left]) | set(records[right]))
        images = [compare_image(name, records[left][name], records[right][name]) for name in names]
        pairs.append(dict(id=f'{left}--{right}', left=left, right=right, images=images,
            total=len(images), comparable=sum(i['status'] != 'not_comparable' for i in images),
            equal=sum(i['status'] == 'equal' for i in images), different=sum(i['status'] == 'different' for i in images),
            not_comparable=sum(i['status'] == 'not_comparable' for i in images),
            class_changes=sum(i['class_changed'] is True for i in images),
            decision_changes=sum(i['decision_changed'] is True for i in images),
            label_conflicts=sum(i['label_conflict'] for i in images),
            quantized=stats([c['difference_q'] for i in images for c in i['components']], True),
            scores=stats([c['difference_score'] for i in images for c in i['components']])))
    for pair in pairs:
        pair.update(agreement(pair))
    return dict(model=model, selected=selected, options=available, pairs=pairs,
                consolidation_generated_at=data['generated_at'])


def export_rows(pair):
    for item in pair['images']:
        record = dict(comparison=pair['id'], name_image=item['name_image'], status=item['status'],
            class_changed=item['class_changed'], decision_changed=item['decision_changed'],
            label_conflict=item['label_conflict'], issues=json.dumps(item['issues']),
            absolute_difference_quantized=[c['difference_q'] for c in item['components']],
            absolute_difference_scores=[c['difference_score'] for c in item['components']])
        for name in ('left', 'right'):
            for key in ('execution', 'source_file', 'result', 'label', 'quantized', 'scores', 'output_indices'):
                record[f'{name}_{key}'] = (item[name] or {}).get(key)
        for name in ('quantized', 'scores'):
            record.update({f'{name}_{key}': item[name][key] for key in METRICS})
        record.update({f'quantized_count_{key}': item['quantized']['buckets'][key] for key in BUCKETS})
        yield record


def analyze(root=ROOT, model='drowsiness', selections=None):
    with LOCK:
        data = read_json(root / 'analysis/consolidated.json')
        report = build(data, model, selections)
        report['generated_at'] = datetime.now(timezone.utc).isoformat()
        report['source'] = 'analysis/consolidated.json'
        report['source_mtime_ns'] = (root / report['source']).stat().st_mtime_ns
        from comparison_summaries import summary_files, accuracy
        report['accuracy'] = accuracy(report)
        payload = json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        files, all_rows = agreement_files(report), []
        files.update(summary_files(report))
        from consistency_report import consistency_files
        files.update(consistency_files(report))
        for pair in report['pairs']:
            rows = list(export_rows(pair))
            files[pair['id']+'.csv'] = csv_bytes(list(rows[0]) if rows else [], rows)
            all_rows.extend(rows)
        files['images.csv'] = csv_bytes(list(all_rows[0]) if all_rows else [], all_rows)
        summary_rows = []
        for pair in report['pairs']:
            row = {key: pair[key] for key in ('id', 'total', 'comparable', 'equal', 'different', 'not_comparable', 'class_changes', 'decision_changes', 'label_conflicts')}
            for field in ('quantized', 'scores'):
                row.update({f'{field}_{metric}': pair[field][metric] for metric in METRICS})
            row.update({f'quantized_count_{key}': pair['quantized']['buckets'][key] for key in BUCKETS})
            summary_rows.append(row)
        files['summary.csv'] = csv_bytes(list(summary_rows[0]), summary_rows)
        files['report.json'] = payload
        for filename, content in files.items():
            atomic_write(root / 'analysis/comparisons' / filename, content)
        return report


if __name__ == '__main__':
    from consolidate_reports import consolidate
    consolidate()
    report = analyze()
    for pair in report['pairs']:
        print(pair['id'], 'images=', pair['total'], 'equal=', pair['equal'], 'different=', pair['different'], 'not_comparable=', pair['not_comparable'])
