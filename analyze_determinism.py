"""Measure observed repeatability within model/runtime/environment from saved consolidations."""
from collections import defaultdict, Counter
from itertools import combinations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from consolidate_reports import ROOT, LOCK, atomic_write, csv_bytes, image_name, read_json


def signature(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def variants(records, field):
    grouped = {}
    for record in records:
        value = record[field]
        key = signature(value)
        grouped.setdefault(key, {"value": value, "executions": []})["executions"].append(record["execution"])
    return list(grouped.values())


def statistics(histogram):
    histogram = sorted((float(value), count) for value, count in histogram.items())
    n = sum(count for _, count in histogram)
    def percentile(p):
        if not n:
            return None
        position = (n - 1) * p
        low = int(position)
        def at(index):
            cumulative = 0
            for value, count in histogram:
                cumulative += count
                if index < cumulative:
                    return value
        return at(low) + (at(min(low + 1, n - 1)) - at(low)) * (position - low)
    return dict(count=n, maximum=histogram[-1][0] if n else None,
                mean=sum(value * count for value, count in histogram) / n if n else None,
                median=percentile(.5), p95=percentile(.95), p99=percentile(.99),
                histogram=histogram)


def buckets(stats):
    result = dict.fromkeys(["0", "1", "2–5", "6–10", ">10"], 0)
    for value, count in stats["histogram"]:
        if not value.is_integer():
            raise ValueError("Quantized differences must be integers")
        key = "0" if value == 0 else "1" if value == 1 else "2–5" if value <= 5 else "6–10" if value <= 10 else ">10"
        result[key] += count
    return result


def magnitudes(records, field):
    histogram = Counter()
    missing = 0
    for first, second in combinations(records, 2):
        def values(record):
            array = record[field]
            return dict(array) if "ranking" in record else dict(zip(record.get("output_indices") or range(len(array)), array))
        a, b = values(first), values(second)
        missing += len(set(a) ^ set(b))
        for index in a.keys() & b.keys():
            histogram[abs(a[index] - b[index])] += 1
    result = statistics(histogram)
    result["unmatched_components"] = missing
    if field == "quantized":
        result["buckets"] = buckets(result)
    return result


def prediction(record):
    if "ranking" in record:
        return {"state": "class", "label": record["ranking"][0]}
    if record.get("result") is not None and record["result"] != -1:
        return {"state": "class", "label": record["result"]}
    return {"state": "invalid" if record.get("invalid") == 1 else "unknown", "label": None}


def aggregate_magnitudes(images):
    result = {}
    for field in ("quantized", "scores"):
        histogram = Counter()
        for item in images:
            histogram.update(dict(item[field + "_differences"]["histogram"]))
        result[field] = statistics(histogram)
        if field == "quantized":
            result[field]["buckets"] = buckets(result[field])
    maxima = Counter(item["quantized_differences"]["maximum"] for item in images
                     if item["quantized_differences"]["maximum"] is not None)
    result["image_maxima"] = statistics(maxima)
    result["image_maxima"]["buckets"] = buckets(result["image_maxima"])
    return result


def compare_group(key, samples, expected):
    model, runtime, env, name = key
    by_execution = defaultdict(list)
    for sample in samples:
        by_execution[sample["execution"]].append(sample)
    duplicate = sorted(execution for execution, records in by_execution.items() if len(records) != 1)
    records = [records[0] for execution, records in sorted(by_execution.items()) if execution not in duplicate]
    good = [r for r in records if r["ok"] == 1 and not r.get("recovery_skipped")
            and isinstance(r.get("quantized"), list) and isinstance(r.get("scores"), list)
            and len(r["quantized"]) == len(r["scores"]) > 0]
    # Explicitly retain successful invalid/tied outputs: those are meaningful
    # observations of numerical repeatability, unlike failed/skipped samples.
    q_variants = variants(good, "quantized")
    s_variants = variants(good, "scores")
    rank_variants = variants(good, "ranking") if good and "ranking" in good[0] else []
    n = len(good)
    pairs = n * (n - 1) // 2
    def differing_pairs(items):
        return pairs - sum(len(v["executions"]) * (len(v["executions"]) - 1) // 2 for v in items)
    q_equal = len(q_variants) == 1 if n >= 2 else None
    s_equal = len(s_variants) == 1 if n >= 2 else None
    rank_equal = len(rank_variants) == 1 if n >= 2 and rank_variants else None
    status = "insufficient" if n < 2 else ("different" if not q_equal or not s_equal or rank_equal is False else "equal")
    outcomes = [dict(r, prediction=prediction(r)) for r in good]
    known = [r for r in outcomes if r["prediction"]["state"] != "unknown"]
    labels = [r["prediction"]["label"] for r in known if r["prediction"]["state"] == "class"]
    prediction_variants = variants(outcomes, "prediction")
    decision_changed = len(variants(known, "prediction")) > 1 if len(known) >= 2 else None
    class_changed = len(set(labels)) > 1 if len(labels) >= 2 else None
    return dict(model=model, type=runtime, env=env, name_image=name,
                scope="top15" if rank_variants else "full", status=status,
                executions=sorted(by_execution), compared_executions=[r["execution"] for r in good],
                missing_executions=sorted(expected - set(by_execution)), duplicate_executions=duplicate,
                excluded_executions=[r["execution"] for r in records if r not in good],
                invalid_observations=sum(r.get("invalid") == 1 for r in good),
                complete=len(good) == len(expected), observations=n, pairs=pairs,
                quantized_equal=q_equal, scores_equal=s_equal, ranking_equal=rank_equal,
                quantized_differences=magnitudes(good, "quantized"), scores_differences=magnitudes(good, "scores"),
                class_changed=class_changed, decision_changed=decision_changed,
                prediction_variants=prediction_variants,
                quantized_different_pairs=differing_pairs(q_variants),
                scores_different_pairs=differing_pairs(s_variants),
                quantized_variants=q_variants, scores_variants=s_variants, ranking_variants=rank_variants)


def markdown(report):
    lines = ["# Determinismo intra-ambiente", "", f"Gerado em: {report['generated_at']}", "",
             "## Método", "",
             "Cada comparação agrupa modelo, formato, ambiente e nome exato da imagem (preservando maiúsculas/minúsculas). "
             "Cada pasta é considerada uma execução independente, conforme informado pelo pesquisador. "
             "São necessárias pelo menos duas execuções com saída registrada. Comparação numérica exata, sem tolerância, dos valores salvos; "
             "a precisão é limitada pelo relatório de origem. Valores 0 e 0.0 são equivalentes.", "",
             "Saídas concluídas marcadas como inválidas/empates são incluídas: uma predição inválida também pode se repetir. "
             "Falhas, imagens ignoradas, vetores ausentes e execuções duplicadas para a mesma imagem são excluídos e identificados. "
             "Cobertura completa significa que todas as execuções do grupo contribuíram com saída comparável.", "",
             "MobileNetV2: compara somente as 15 classes registradas. q e score são associados ao índice da classe; "
             "mudanças na composição do Top-15 contam como diferenças. A ordem do ranking também é comparada separadamente. "
             "Não se infere igualdade das outras 985 classes.", "",
             "O resultado descreve repetibilidade observada, não uma garantia de determinismo em execuções futuras. "
             "A identidade dos bytes de entrada, modelo e configuração entre execuções não é verificada por esta análise; "
             "mudanças nesses fatores podem explicar diferenças. Não são comparados tempos de execução.", "",
             "## Resultados", "", "| Modelo | Formato | Ambiente | Execuções | Imagens comparáveis | Iguais | Diferentes | Insuficientes | Cobertura incompleta |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for group in report["groups"]:
        lines.append(f"| {group['model']} | {group['type']} | {group['env']} | {len(group['executions'])} | {group['comparable']} | {group['equal']} | {group['different']} | {group['insufficient']} | {group['incomplete']} |")
    lines.extend(["", "## Magnitude e distribuição", "",
                  "Para cada imagem, usamos todos os pares não ordenados de execuções válidas e a diferença absoluta por componente de saída. "
                  "Com n execuções e c classes, são n(n−1)/2 × c diferenças. Média, mediana, P95 e P99 incluem zeros. "
                  "Percentis usam interpolação linear na posição (N−1)p. As estatísticas agregadas agrupam componentes, "
                  "não médias de imagens; imagens com mais pares contribuem mais observações. Resultados sem pares são ausentes, não zero.", "",
                  "As faixas 0, 1, 2–5, 6–10 e >10 usam unidades inteiras de quantized. "
                  "Há duas distribuições: diferenças por componente/par e imagens agrupadas pela sua diferença máxima. "
                  "Scores têm estatísticas próprias, sem arredondamento antes do cálculo. No Top-15, magnitudes usam somente classes presentes em ambos os pares; "
                  "classes ausentes não são preenchidas com zero. A mudança de composição continua sinalizada na análise de igualdade.", "",
                  "Mudança de classe compara labels/resultados registrados (Top-1 no MobileNet). Transições entre uma classe e saída inválida "
                  "são mudanças de decisão, não trocas entre duas classes; resultados desconhecidos não comprovam estabilidade.", ""])
    def stats_text(stats):
        return f"N={stats['count']}; máximo={stats['maximum']}; média={stats['mean']}; mediana={stats['median']}; P95={stats['p95']}; P99={stats['p99']}"
    for group in report["groups"]:
        lines.extend([f"### {group['model']} / {group['type']} / {group['env']}", "",
                      f"Imagens com troca de classe: {group['class_changes']}; com mudança de decisão: {group['decision_changes']}.", ""])
        for population, title in [("all", "Todas as imagens comparáveis"), ("divergent", "Somente imagens divergentes")]:
            metrics = group["magnitudes"][population]
            lines.extend([f"**{title}**", f"- quantized: {stats_text(metrics['quantized'])}",
                          f"- scores: {stats_text(metrics['scores'])}",
                          f"- Faixas por componente/par: {metrics['quantized']['buckets']}",
                          f"- Faixas por imagem (máximo): {metrics['image_maxima']['buckets']}", ""])
    lines.extend(["", "## Interpretação", ""])
    for group in report["groups"]:
        label = f"{group['model']} / {group['type']} / {group['env']}"
        if group["comparable"]:
            percentage = 100 * group["equal"] / group["comparable"]
            lines.append(f"- **{label}**: {group['equal']}/{group['comparable']} imagens comparáveis "
                         f"({percentage:.2f}%) repetiram exatamente os valores registrados em todas as execuções comparadas; "
                         f"{group['different']} apresentaram diferenças. Execuções do grupo: {group['executions']}.")
        else:
            lines.append(f"- **{label}**: não há repetições suficientes para avaliar igualdade.")
    lines.extend(["", "Esta porcentagem mede repetibilidade por imagem, não acurácia. "
                  "Para MobileNetV2, inclui igualdade do Top-15 e da ordem do ranking. "
                  "Diferenças observadas não identificam sua causa; é necessário controlar entradas, modelo e configuração antes de atribuí-las ao runtime.",
                  "", "## Imagens com diferenças", ""])
    for item in report["images"]:
        if item["status"] != "different":
            continue
        lines.extend([f"### {item['model']} / {item['type']} / {item['env']} / {item['name_image']}", "",
                      f"Execuções comparadas: {item['compared_executions']}. Quantized iguais: {item['quantized_equal']}; scores iguais: {item['scores_equal']}; ranking igual: {item['ranking_equal']}.", ""])
        lines.extend([f"quantized: {stats_text(item['quantized_differences'])}",
                      f"scores: {stats_text(item['scores_differences'])}",
                      f"Faixas quantized: {item['quantized_differences']['buckets']}",
                      f"Troca de classe: {item['class_changed']}; mudança de decisão: {item['decision_changed']}; predições: {signature(item['prediction_variants'])}", ""])
        conclusion = ("A classe predita mudou entre as execuções." if item["class_changed"] else
                      "Houve uma transição entre predição e saída inválida." if item["decision_changed"] else
                      "A classe predita permaneceu a mesma, apesar da variação numérica." if item["class_changed"] is False else
                      "Não há classes registradas suficientes para concluir se houve troca.")
        lines.extend([f"**Interpretação desta imagem:** a maior diferença registrada foi de {item['quantized_differences']['maximum']} "
                      f"unidades quantizadas e {item['scores_differences']['maximum']} em score. {conclusion} "
                      f"As estatísticas resumem {item['quantized_differences']['count']} diferenças entre valores de saída desta imagem. "
                      "Quando há duas execuções e duas saídas com diferenças iguais, máximo, média, mediana, P95 e P99 coincidem.", ""])
        for field in ("quantized", "scores", "ranking"):
            if item[field + "_variants"]:
                lines.append(f"**{field}**")
                for variant in item[field + "_variants"]:
                    lines.append(f"- Execuções {variant['executions']}: `{signature(variant['value'])}`")
                lines.append("")
    if not any(item["status"] == "different" for item in report["images"]):
        lines.append("Nenhuma diferença observada nas imagens comparáveis.")
    lines.extend(["", "## Cobertura e exclusões", ""])
    for item in report["images"]:
        if not item["complete"] or item["status"] == "insufficient":
            lines.append(f"- {item['model']} / {item['type']} / {item['env']} / {item['name_image']}: "
                         f"ausentes={item['missing_executions']}; excluídas={item['excluded_executions']}; "
                         f"duplicadas={item['duplicate_executions']}; comparadas={item['compared_executions']}.")
    lines.extend(["", "## Fontes consolidadas", ""])
    for source in report["sources"]:
        lines.append(f"- `{source['path']}` — SHA256 `{source['sha256']}`; consolidação: {source['generated_at']}.")
    lines.extend(["", "Os IDs de execução do MobileNetV2 pertencem ao seu próprio mapa; não correspondem aos IDs da tabela Drowsiness.", ""])
    for source, runs in report["execution_maps"].items():
        lines.extend([f"### Mapa: {source}", ""])
        for run in runs:
            lines.append(f"- {run['execution']} / {run['type']} / {run['env']}: `{run['folder']}`")
        lines.append("")
    return "\n".join(lines)


def analyze(root=ROOT):
    root = Path(root)
    with LOCK:
        samples, expected = defaultdict(list), defaultdict(set)
        sources, execution_maps = [], {}
        for filename in ("consolidated.json", "mobilenet_top15.json"):
            path = root / "analysis" / filename
            if not path.exists():
                raise ValueError(f"Gere primeiro a consolidação: analysis/{filename}")
            data = read_json(path)
            sources.append(dict(path=f"analysis/{filename}", generated_at=data["generated_at"], sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            execution_maps[filename] = data.get("raw_executions", data["executions"])
            runs = {r["execution"]: r for r in execution_maps[filename]}
            for run in runs.values():
                expected[(run["model"], run["type"], run["env"])].add(run["execution"])
            if filename == "consolidated.json":
                for item in data.get("raw_rows", data["rows"]):
                    record = dict(item)
                    # Normalize JSON numeric representations before exact comparison.
                    for field in ("quantized", "scores"):
                        if isinstance(record[field], list):
                            record[field] = [float(v) or 0.0 for v in record[field]]
                    key = (item["model"], item["type"], item["env"], item["name_image"])
                    samples[key].append(record)
            else:
                per_run = defaultdict(list)
                for item in data["rows"]:
                    per_run[item["execution"]].append(item)
                for execution, entries in per_run.items():
                    run = runs[execution]
                    name = image_name(run.get("image", ""))
                    if not name:
                        raise ValueError(f"MobileNet execution {execution}: missing image identity")
                    indices = [int(item["name"].split("]", 1)[0][1:]) for item in entries]
                    if len(indices) != 15 or len(set(indices)) != 15:
                        raise ValueError(f"MobileNet execution {execution}: invalid Top-15")
                    ordered = sorted(zip(indices, entries), key=lambda pair: pair[0])
                    record = dict(execution=execution, ok=1, quantized=[[i, float(r["q"])] for i, r in ordered],
                                  scores=[[i, float(r["score"])] for i, r in ordered], ranking=indices)
                    samples[(run["model"], run["type"], run["env"], name)].append(record)
        images = [compare_group(key, records, expected[key[:3]]) for key, records in sorted(samples.items())]
        groups = []
        for key, executions in sorted(expected.items()):
            subset = [item for item in images if (item["model"], item["type"], item["env"]) == key]
            groups.append(dict(model=key[0], type=key[1], env=key[2], executions=sorted(executions),
                               images=len(subset), comparable=sum(r["observations"] >= 2 for r in subset),
                               equal=sum(r["status"] == "equal" for r in subset),
                               different=sum(r["status"] == "different" for r in subset),
                               class_changes=sum(r["class_changed"] is True for r in subset),
                               decision_changes=sum(r["decision_changed"] is True for r in subset),
                               magnitudes={"all": aggregate_magnitudes(subset),
                                           "divergent": aggregate_magnitudes([r for r in subset if r["status"] == "different"])},
                               insufficient=sum(r["status"] == "insufficient" for r in subset),
                               incomplete=sum(not r["complete"] for r in subset)))
        report = dict(generated_at=datetime.now(timezone.utc).isoformat(), sources=sources,
                      groups=groups, images=images, execution_maps=execution_maps)
        destination = root / "analysis/determinism"
        payload = json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")
        columns = ["model", "type", "env", "name_image", "scope", "status", "observations", "complete",
                   "quantized_equal", "scores_equal", "ranking_equal", "pairs", "quantized_different_pairs", "scores_different_pairs",
                   "compared_executions", "missing_executions", "excluded_executions", "duplicate_executions",
                   "quantized_variants", "scores_variants", "ranking_variants"]
        columns += ["class_changed", "decision_changed", "prediction_variants"]
        exported = []
        for item in images:
            item = dict(item)
            for field in ("quantized", "scores"):
                for metric in ("count", "maximum", "mean", "median", "p95", "p99", "unmatched_components"):
                    item[field + "_" + metric] = item[field + "_differences"][metric]
            for bucket, count in item["quantized_differences"]["buckets"].items():
                item["quantized_count_" + bucket] = count
            exported.append(item)
        columns += [field + "_" + metric for field in ("quantized", "scores") for metric in ("count", "maximum", "mean", "median", "p95", "p99", "unmatched_components")]
        columns += ["quantized_count_" + bucket for bucket in ("0", "1", "2–5", "6–10", ">10")]
        atomic_write(destination / "images.csv", csv_bytes(columns, exported))
        atomic_write(destination / "report.md", markdown(report).encode("utf-8"))
        atomic_write(destination / "report.json", payload)
        return report


if __name__ == "__main__":
    result = analyze()
    for group in result["groups"]:
        print(group)
