"""Audit saved image decisions without running inference (standard library only)."""
import json
import math
from collections import Counter

from consolidate_reports import ROOT, read_json, csv_bytes, atomic_write

FILES = ('consistency.md', 'consistency.json', 'consistency.csv',
         'consistency_images.csv', 'consistency_matrices.csv')
NONE = 'SEM_PREDICAO'
CATEGORIES = (0, 1, NONE)
METRICS = {
    'both_correct': 'Ambas acertaram',
    'both_incorrect': 'Ambas não acertaram (inclui SEM_PREDICAO)',
    'both_wrong_valid': 'Ambas erraram com classes válidas',
    'left_only_correct': 'Esquerda acertou e direita não acertou',
    'right_only_correct': 'Direita acertou e esquerda não acertou',
    'same_valid_class': 'Mesma classe predita (ambas válidas)',
    'different_valid_class': 'Classes diferentes (ambas válidas)',
    'any_no_prediction': 'Pelo menos uma SEM_PREDICAO',
    'both_no_prediction': 'Ambas SEM_PREDICAO',
    'left_no_prediction': 'Esquerda SEM_PREDICAO',
    'right_no_prediction': 'Direita SEM_PREDICAO',
    'same_category': 'Mesma categoria (inclui SEM_PREDICAO)',
    'different_category': 'Categorias diferentes (inclui SEM_PREDICAO)',
    'identical_quantized_vectors': 'Vetores quantizados completos idênticos',
    'vector_comparable': 'Pares com vetores completos comparáveis',
    'unknown_or_conflicting_label': 'Rótulos ausentes ou conflitantes',
}


def prediction(record):
    if (record and record.get('ok') == 1 and record.get('invalid') != 1
            and record.get('prediction_usable') != 0
            and record.get('result') in (0, 1)):
        return record['result']
    return NONE


def vector(record):
    if not record or record.get('ok') != 1:
        return None
    q, indices = record.get('quantized'), record.get('output_indices')
    if not isinstance(q, list) or indices not in ([0, 1], [1, 0]) or len(q) != 2:
        return None
    if any(not isinstance(v, (int, float)) or not math.isfinite(v)
           or not float(v).is_integer() for v in q):
        return None
    return [dict(zip(indices, q))[i] for i in (0, 1)]


def audit(report):
    from compare_environments import SOURCES
    records = {s: {} for s in SOURCES}
    for pair in report['pairs']:
        seen = set()
        for item in pair['images']:
            name = item['name_image']
            if name in seen:
                raise ValueError(f'Duplicate image in comparison: {name}')
            seen.add(name)
            for side in ('left', 'right'):
                source = pair[side]
                if name in records[source] and records[source][name] != item[side]:
                    raise ValueError(f'Conflicting records: {source}/{name}')
                records[source][name] = item[side]
    names = sorted(set().union(*(set(r) for r in records.values())))
    rows = []
    for name in names:
        labels = {r[name]['label'] for r in records.values()
                  if r.get(name) and r[name].get('label') in (0, 1)}
        label = next(iter(labels)) if len(labels) == 1 else None
        item = dict(name_image=name, label=label, label_conflict=len(labels) > 1)
        for source in SOURCES:
            r = records[source].get(name)
            item[source] = dict(prediction=prediction(r), quantized=vector(r),
                recorded_quantized=r.get('quantized') if r else None,
                recorded_result=r.get('result') if r else None,
                recorded_label=r.get('label') if r else None,
                execution=report['selected'][source]['execution'],
                source_file=r.get('source_file') if r else None,
                missing_record=r is None)
        rows.append(item)
    sources = []
    for source in SOURCES:
        labelled = [r for r in rows if r['label'] in (0, 1)]
        correct = sum(r[source]['prediction'] == r['label'] for r in labelled)
        absent = sum(r[source]['prediction'] == NONE for r in labelled)
        sources.append(dict(source=source, execution=report['selected'][source]['execution'],
            total=len(rows), labelled=len(labelled), correct=correct,
            incorrect_valid=len(labelled)-correct-absent, no_prediction=absent,
            missing_records=sum(r[source]['missing_record'] for r in rows)))
    summaries = []
    for pair in report['pairs']:
        counts, matrix, details = Counter(), Counter(), []
        for item in rows:
            a, b = item[pair['left']], item[pair['right']]
            pa, pb, label = a['prediction'], b['prediction'], item['label']
            matrix[pa, pb] += 1
            valid = pa != NONE and pb != NONE
            known = label in (0, 1)
            ca, cb = known and pa == label, known and pb == label
            va, vb = a['quantized'], b['quantized']
            flags = dict(both_correct=known and ca and cb,
                both_incorrect=known and not ca and not cb,
                both_wrong_valid=known and valid and not ca and not cb,
                left_only_correct=known and ca and not cb,
                right_only_correct=known and cb and not ca,
                same_valid_class=valid and pa == pb,
                different_valid_class=valid and pa != pb,
                any_no_prediction=not valid, both_no_prediction=pa == pb == NONE,
                left_no_prediction=pa == NONE, right_no_prediction=pb == NONE,
                same_category=pa == pb, different_category=pa != pb,
                identical_quantized_vectors=va is not None and vb is not None and va == vb,
                vector_comparable=va is not None and vb is not None,
                unknown_or_conflicting_label=not known)
            counts.update({k: int(v) for k, v in flags.items()})
            if pa != pb or not valid:
                details.append(dict(name_image=item['name_image'], label=label,
                    left_prediction=pa, right_prediction=pb,
                    left_quantized=va, right_quantized=vb,
                    left_correct=ca if known else None, right_correct=cb if known else None))
        total = len(rows)
        labelled = total - counts['unknown_or_conflicting_label']
        assert sum(counts[k] for k in ('both_correct', 'both_incorrect', 'left_only_correct', 'right_only_correct')) == labelled
        assert counts['same_valid_class'] + counts['different_valid_class'] + counts['any_no_prediction'] == total
        valid_n = total - counts['any_no_prediction']
        summaries.append(dict(id=pair['id'], left=pair['left'], right=pair['right'], total=total,
            **counts, accuracy_difference_right_minus_left=counts['right_only_correct']-counts['left_only_correct'],
            category_agreement_pct=100*counts['same_category']/total if total else None,
            valid_class_agreement_pct=100*counts['same_valid_class']/valid_n if valid_n else None,
            quantized_agreement_pct=100*counts['identical_quantized_vectors']/counts['vector_comparable'] if counts['vector_comparable'] else None,
            previous_class_changes=pair['class_changes'],
            previous_decision_changes=pair['decision_changes'],
            matrix=[[matrix[a, b] for b in CATEGORIES] for a in CATEGORIES], details=details))
    return dict(generated_from=report['generated_at'], selected=report['selected'], sources=sources,
                total=len(rows), categories=list(CATEGORIES), pairs=summaries, images=rows)


def consistency_files(report):
    from compare_environments import SOURCE_NAMES, SOURCES
    result = audit(report)
    lines = ['# Teste de consistência dos resultados — parecer 4.2', '',
        f"Base: relatório de comparações gerado em {result['generated_from']}. {result['total']} imagens por par.", '',
        'Processamento exclusivo de resultados armazenados, sem repetir inferências.', '',
        '## Fontes', '', '| Implementação | Execução | Arquivo |', '| --- | --- | --- |']
    for source, run in report['selected'].items():
        lines.append(f"| {SOURCE_NAMES[source]} | {run['execution']} | {run['source_file']} |")
    lines += ['', 'As execuções ESP32 51 e 50 são relatórios representativos derivados por consenso; o teste preserva essas fontes.', '',
        '## Acertos recalculados por implementação', '',
        '| Implementação | Total | Acertos | Erros com classe válida | SEM_PREDICAO | Registros ausentes |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    lines.extend('| ' + ' | '.join(map(str, [SOURCE_NAMES[s['source']], s['total'], s['correct'], s['incorrect_valid'], s['no_prediction'], s['missing_records']])) + ' |' for s in result['sources'])
    lines += ['',
        '## Critérios', '',
        'Identificadores são relacionados exatamente, preservando maiúsculas e minúsculas: A0001.raw e a0001.raw são imagens distintas. Classes: 0 = non_drowsy; 1 = drowsy. Saída sem classe utilizável, falha ou registro ausente recebe SEM_PREDICAO; a classe registrada não é substituída pelo argmax.', '',
        '“Ambas não acertaram” inclui ausências; “ambas erraram com classes válidas” é apresentada separadamente. Os quatro resultados de acerto somam as imagens com rótulo conhecido e consistente. Mesma classe válida + classes válidas diferentes + pelo menos uma SEM_PREDICAO = total.', '',
        'Os relatórios armazenam vetores quantizados de saída em UINT8 (0–255), apesar do modelo ter quantização interna INT8. Os valores são preservados, sem reinterpretá-los como INT8. Ordem completa: índice 0 = drowsy; índice 1 = non_drowsy. Igualdade quantizada compara os dois componentes alinhados, independentemente dos scores e da existência de classe válida. Vetores incompletos/ausentes não contam como idênticos.', '',
        'A concordância válida exclui SEM_PREDICAO; a concordância por categoria inclui SEM_PREDICAO e usa todas as imagens. Duas ausências iguais são concordância de categoria, nunca uma classe válida.']
    summary, matrices = [], []
    for p in result['pairs']:
        title = f"{SOURCE_NAMES[p['left']]} × {SOURCE_NAMES[p['right']]}"
        summary.append({k: v for k, v in p.items() if k not in ('matrix', 'details')})
        lines += ['', f'## {title}', '', '| Resultado | Quantidade |', '| --- | ---: |', f"| Imagens | {p['total']} |"]
        lines.extend(f"| {text} | {p[key]} |" for key, text in METRICS.items())
        lines += ['', f"Diferença de acertos (direita − esquerda): {p['right_only_correct']} − {p['left_only_correct']} = {p['accuracy_difference_right_minus_left']}.",
            f"Trocas de classe na tabela anterior: {p['previous_class_changes']}; recalculadas entre classes válidas: {p['different_valid_class']}; mudanças incluindo SEM_PREDICAO: {p['different_category']}.", '',
            'Concordância de classes válidas: {}; concordância de categorias: {}; igualdade dos vetores quantizados: {}.'.format(
                *(f'{p[k]:.4f}%'.replace('.', ',') if p[k] is not None else 'não calculável'
                  for k in ('valid_class_agreement_pct', 'category_agreement_pct', 'quantized_agreement_pct'))), '',
            '### Matriz de concordância', '', 'Linhas = esquerda; colunas = direita.', '',
            '| Predição | 0 | 1 | SEM_PREDICAO |', '| --- | ---: | ---: | ---: |']
        for a, values in zip(CATEGORIES, p['matrix']):
            lines.append('| ' + ' | '.join(map(str, [a, *values])) + ' |')
            matrices.extend(dict(comparison=p['id'], left_prediction=a, right_prediction=b, count=n)
                            for b, n in zip(CATEGORIES, values))
        lines += ['', '### Imagens com categorias diferentes ou ausência de predição', '',
            '| Imagem | Rótulo | Esquerda | Direita | Vetor esquerda | Vetor direita | Acertou esquerda | Acertou direita |',
            '| --- | --- | --- | --- | --- | --- | --- | --- |']
        lines.extend('| ' + ' | '.join(str(d[k]) for k in ('name_image', 'label', 'left_prediction', 'right_prediction', 'left_quantized', 'right_quantized', 'left_correct', 'right_correct')) + ' |' for d in p['details'])
    desktop = next(p for p in result['pairs'] if p['id'] == 'wasm_desktop--tflite_desktop')
    p = desktop
    valid_changes = [d for d in p['details'] if d['left_prediction'] != NONE and d['right_prediction'] != NONE]
    absent_changes = [d for d in p['details'] if d['left_prediction'] == NONE or d['right_prediction'] == NONE]
    valid_right = sum(d['right_correct'] is True for d in valid_changes)
    valid_left = sum(d['left_correct'] is True for d in valid_changes)
    absent_right = sum(d['right_correct'] is True for d in absent_changes)
    absent_left = sum(d['left_correct'] is True for d in absent_changes)
    lines += ['', '## Conclusão sobre a diferença no desktop', '',
        f"A diferença de {p['accuracy_difference_right_minus_left']} acertos corresponde a {p['right_only_correct']} imagens acertadas somente pelo TFLite menos {p['left_only_correct']} acertadas somente pelo WASM. Há {p['different_valid_class']} trocas entre classes válidas, {p['any_no_prediction']} imagens com pelo menos uma ausência e {p['both_no_prediction']} com ausência em ambas. Contando SEM_PREDICAO, há {p['different_category']} mudanças de categoria.", '',
        f'Entre as trocas válidas, o TFLite acertou {valid_right} e o WASM {valid_left}: saldo {valid_right-valid_left}. Entre as imagens com ausência, o TFLite acertou {absent_right} e o WASM {absent_left}: saldo {absent_right-absent_left}. Logo, ({valid_right} − {valid_left}) + ({absent_right} − {absent_left}) = {p["accuracy_difference_right_minus_left"]}.', '',
        'A tabela anterior pode manter as trocas entre classes válidas, desde que explicite o denominador e as ausências. Diferença líquida de acertos não é a mesma métrica que número de mudanças de classe. As imagens e matrizes acima permitem verificar ambas.', '']
    flat = []
    for image in result['images']:
        row = {k: image[k] for k in ('name_image', 'label', 'label_conflict')}
        for source in SOURCES:
            row.update({source+'_'+k: v for k, v in image[source].items()})
        flat.append(row)
    def csv(rows):
        return csv_bytes(list(rows[0]) if rows else [], rows)
    return {'consistency.md': ('\n'.join(lines)).encode('utf-8'),
        'consistency.json': json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8'),
        'consistency.csv': csv(summary), 'consistency_images.csv': csv(flat),
        'consistency_matrices.csv': csv(matrices)}


if __name__ == '__main__':
    report = read_json(ROOT / 'analysis/comparisons/report.json')
    for filename, content in consistency_files(report).items():
        atomic_write(ROOT / 'analysis/comparisons' / filename, content)
    print('Relatório gerado: analysis/comparisons/consistency.md')
