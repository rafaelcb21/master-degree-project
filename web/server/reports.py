"""Read-only adapters for existing reports. Never execute model code."""
import csv
import io
import math
import re
import statistics


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def metrics_for_rows(rows):
    metrics = [{"label": "Registros", "value": len(rows)}]
    successful = [r for r in rows if str(r.get("ok", "1")) == "1"]
    if rows and "ok" in rows[0]:
        metrics.append({"label": "Falhas", "value": len(rows) - len(successful)})
    labeled = [r for r in successful if number(r.get("right")) in (0, 1)]
    if labeled:
        metrics.extend([
            {"label": "Acurácia", "value": round(100 * sum(float(r["right"]) for r in labeled) / len(labeled), 2), "unit": "%"},
            {"label": "Amostras avaliadas", "value": len(labeled)},
        ])
    for key, label in [("inference_ms", "Inferência média"), ("download_ms", "Download médio")]:
        values = [number(r.get(key)) for r in successful]
        values = [v for v in values if v is not None and v >= 0]
        if values:
            metrics.append({"label": label, "value": round(statistics.mean(values), 3), "unit": "ms"})
    return metrics


def parse_report(path, text):
    result = {"kind": "text", "metrics": [], "columns": [], "rows": [], "series": [], "regions": []}
    if path.suffix.lower() == ".csv":
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        try:
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            columns = reader.fieldnames or []
            rows = [{k: (v or "") for k, v in row.items() if k is not None} for row in reader]
        except csv.Error:
            return result
        result.update(kind="csv", columns=columns, rows=rows, metrics=metrics_for_rows(rows))
        for key, label in [("inference_ms", "Inferência"), ("download_ms", "Download")]:
            points = [{"x": i + 1, "y": number(r.get(key))} for i, r in enumerate(rows) if r.get("ok", "1") == "1" and number(r.get(key)) is not None and number(r.get(key)) >= 0]
            if points:
                result["series"].append({"label": label, "unit": "ms", "points": points})
        return result

    if "quantized=" in text and "right=" in text:
        rows = []
        for line in text.splitlines():
            match = re.match(r"(.+?)\s*\|\s*quantized=(\[[^\]]*\])\s*\|\s*scores=(\[[^\]]*\])\s*\|\s*result=(-?\d+|None)\s+label=(-?\d+)\s+right=(-?\d+)\s+invalid=(True|False)", line)
            if match:
                name, raw, scores, prediction, label, right, invalid = match.groups()
                rows.append({"Imagem": re.split(r"[/\\]", name)[-1], "Predição": prediction, "Rótulo": label, "right": right, "Inválido": invalid, "Quantizado": raw, "Scores": scores})
        result.update(kind="inference", rows=rows, columns=list(rows[0]) if rows else [], metrics=metrics_for_rows(rows))
        invalid = sum(r["Inválido"] == "True" for r in rows)
        result["metrics"].append({"label": "Inválidos / empates", "value": invalid})
        errors = re.search(r"Erros de processamento:\s*(\d+)", text)
        if errors:
            result["metrics"].append({"label": "Erros de processamento", "value": int(errors[1])})
        return result

    if "ImageNet Top-K" in text:
        rows, current = [], ""
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().lower().endswith(".raw"):
                current = re.split(r"[/\\]", line.strip())[-1]
            match = re.match(r"\s*(\d+)\.\s*\[(\d+)\]\s*(.+)", line)
            if match:
                fields = dict(re.findall(r"(wnid|q|score)=([^\s]+)", " ".join(lines[i + 1:i + 4])))
                rows.append({"Imagem": current, "Posição": int(match[1]), "Classe": match[3], "Índice": match[2], "Score": number(fields.get("score")), "Quantizado": fields.get("q", ""), "WordNet": fields.get("wnid", "")})
        result.update(kind="topk", rows=rows, columns=list(rows[0]) if rows else [], metrics=[{"label": "Imagens", "value": len({r['Imagem'] for r in rows})}, {"label": "Predições listadas", "value": len(rows)}])
        return result

    regions = []
    for line in text.splitlines():
        match = re.match(r"^(WEIGHTS|BIAS|MUL|SHIFT|Q6|PARAMS|SLOT\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", line)
        if match:
            regions.append({"Região": match[1], "Base": int(match[2]), "Bytes": int(match[3]), "Fim": int(match[4])})
    if regions:
        result.update(kind="memory", regions=regions, rows=regions, columns=list(regions[0]))
        for key, label, unit in [("MEM_PAGES", "Páginas WASM", ""), ("MEM_END", "Fim da memória", "bytes"), ("SLOT_BYTES", "Tamanho de cada slot", "bytes")]:
            match = re.search(rf"^{key}\s*=\s*(\d+)", text, re.M)
            if match:
                result["metrics"].append({"label": label, "value": int(match[1]), "unit": unit})
        return result

    # Weight and quantization records: expose fields while retaining the source.
    rows = []
    section = ""
    for line in text.splitlines():
        if line.strip() in ("PESOS", "BIAS", "WEIGHTS"):
            section = line.strip()
        if re.match(r"\s*op\s*=", line):
            fields = dict(re.findall(r"(\w+)\s*=\s*(.*?)(?=\s+\w+\s*=|$)", line))
            if len(fields) > 2:
                rows.append({"Seção": section, **fields} if section else fields)
    if rows:
        columns = list(dict.fromkeys(k for row in rows for k in row))
        result.update(kind="records", rows=rows, columns=columns, metrics=[{"label": "Registros", "value": len(rows)}])
    return result

