"""Readable quantized difference and ground-truth accuracy summaries."""
from compare_environments import SOURCES, SOURCE_NAMES, BUCKETS
from consolidate_reports import csv_bytes
from decimal import Decimal, ROUND_HALF_UP

FILES = ('quantized_stats.csv', 'quantized_stats.md', 'quantized_buckets.csv', 'quantized_buckets.md',
         'accuracy.csv', 'accuracy.md')


def accuracy(report):
    results = []
    for source in SOURCES:
        records, missing = {}, set()
        for pair in report['pairs']:
            for side in ('left', 'right'):
                if pair[side] != source:
                    continue
                for image in pair['images']:
                    value = image[side]
                    if value is not None:
                        previous = records.get(image['name_image'])
                        if previous is not None and previous != value:
                            raise ValueError('Conflicting saved image records for accuracy')
                        records[image['name_image']] = value
                    else:
                        missing.add(image['name_image'])
        unknown = sum(r.get('label') not in (0, 1) for r in records.values())
        for label in (None, 0, 1):
            items = [r for r in records.values() if r.get('label') in (0, 1) and
                     (label is None or r['label'] == label)]
            valid = [r for r in items if r.get('ok') == 1 and r.get('invalid') != 1 and
                     r.get('prediction_usable') != 0 and r.get('result') in (0, 1)]
            correct = sum(r['result'] == r['label'] for r in valid)
            results.append(dict(source=source, execution=report['selected'][source]['execution'],
                class_label=label, total=len(items), valid_predictions=len(valid), correct=correct,
                incorrect_valid=len(valid)-correct, no_valid_prediction=len(items)-len(valid),
                accuracy_pct=100*correct/len(items) if items else None,
                valid_accuracy_pct=100*correct/len(valid) if valid else None,
                unknown_labels=unknown, missing_records=len(missing-set(records))))
    return results


def percent(value):
    return decimal(value)+'%' if value is not None else '—'


def decimal(value, digits=2):
    if value is None:
        return '—'
    rounded = Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return f'{rounded:.{digits}f}'.replace('.', ',')


def compact(value):
    return decimal(value).rstrip('0').rstrip(',') if value is not None else '—'


def table_files(name, title, rows, notes):
    columns = list(rows[0]) if rows else []
    lines = [f'# {title}', '', '| ' + ' | '.join(columns) + ' |',
             '| ' + ' | '.join(['---']*len(columns)) + ' |']
    lines.extend('| ' + ' | '.join(str(row[key]) for key in columns) + ' |' for row in rows)
    lines += ['', notes, '']
    return {name+'.csv':csv_bytes(columns, rows), name+'.md':'\n'.join(lines).encode('utf-8')}


def summary_files(report):
    stats_rows, bucket_rows = [], []
    for pair in report['pairs']:
        name = f"{SOURCE_NAMES[pair['left']]} × {SOURCE_NAMES[pair['right']]}"
        q = pair['quantized']
        zero = q['buckets']['0']
        stats_rows.append({'Comparação':name, 'Máx. Δq':compact(q['maximum']), 'Média Δq':decimal(q['mean'], 3),
            'Mediana':compact(q['median']), 'P95':compact(q['p95']), 'P99':compact(q['p99']),
            'Δq = 0':zero, 'Δq = 0 (%)':percent(100*zero/q['count'] if q['count'] else None),
            'Componentes comparáveis':q['count']})
        bucket_rows.append({'Comparação':name, **{f'Δq={key}' if key != '>10' else 'Δq>10':q['buckets'][key] for key in BUCKETS},
                            'Componentes comparáveis':q['count']})
    note = 'Diferenças absolutas por componente quantizado, incluindo zeros. São dois componentes por imagem comparável no Drowsiness. Percentis usam interpolação linear. Contagens e percentual de Δq=0 usam o total de componentes comparáveis. Os números são derivados dos relatórios salvos; os vetores originais e valores sem arredondamento permanecem no JSON detalhado.'
    files = table_files('quantized_stats', 'Estatísticas das diferenças quantizadas', stats_rows, note)
    files.update(table_files('quantized_buckets', 'Distribuição das diferenças quantizadas', bucket_rows, note))
    accuracy_rows = []
    for row in accuracy(report):
        label = row['class_label']
        accuracy_rows.append({'Ambiente e formato':SOURCE_NAMES[row['source']],
            'Classe de referência':'Geral' if label is None else f"{label} ({'drowsy' if label == 1 else 'non_drowsy'})",
            'Imagens rotuladas':row['total'], 'Acertos':row['correct'],
            'Erros com classe válida':row['incorrect_valid'], 'Sem predição válida':row['no_valid_prediction'],
            'Acertos (%)':percent(row['accuracy_pct']), 'Predições válidas':row['valid_predictions'],
            'Acertos entre predições válidas (%)':percent(row['valid_accuracy_pct']),
            'Sem rótulo conhecido':row['unknown_labels'], 'Registros ausentes/duplicados':row['missing_records'],
            'Execução':row['execution']})
    files.update(table_files('accuracy', 'Acertos por classe de referência', accuracy_rows,
        'Acerto = classe predita igual ao rótulo de referência registrado. Cada fonte/imagem é contada uma única vez, mesmo aparecendo em três comparações. O percentual principal é acertos / todas as imagens com rótulo conhecido da classe (ou de ambas as classes em Geral); falhas, empates e saídas inválidas não contam como acerto. O percentual complementar usa apenas predições válidas. Sem rótulo conhecido e registros ausentes/duplicados ficam identificados e fora do denominador. As classes são 0 = non_drowsy e 1 = drowsy. Usa as execuções já escolhidas nas comparações; não calcula concordância entre implementações.'))
    return files
