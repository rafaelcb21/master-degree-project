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


def memory_metrics(text):
    """Only explicit versioned fields may be labeled as internal SRAM."""
    footer = "\n".join(line[1:] for line in text.splitlines() if line.startswith("#"))
    fields = dict(re.findall(r"(?:^|\s)([a-z][a-z0-9_]*)=([^\s]+)", footer))
    if fields.get("memory_report_schema") != "1":
        return [], []
    metrics = []
    for key, label, unit in [
        ("cpu_frequency_mhz", "Frequência da CPU", "MHz"),
        ("internal_heap_total_bytes", "Heap interno total (8 bits)", "bytes"),
        ("internal_heap_min_free_bytes", "Heap interno livre mínimo desde o boot", "bytes"),
        ("internal_heap_used_bytes", "Heap interno ocupado ao final", "bytes"),
        ("psram_total_bytes", "PSRAM total", "bytes"),
        ("psram_min_free_bytes", "PSRAM livre mínima desde o boot", "bytes"),
        ("psram_occupied_bytes", "PSRAM ocupada ao final", "bytes"),
        ("sram_static_dram_bytes", "SRAM estática em DRAM", "bytes"),
        ("sram_static_iram_bytes", "SRAM estática em IRAM (com alinhamento)", "bytes"),
        ("flash_app_image_bytes", "Firmware na flash", "bytes"),
        ("flash_app_partition_bytes", "Partição da aplicação", "bytes"),
        ("flash_app_partition_used_pct", "Ocupação da partição da aplicação", "%"),
        ("flash_spiffs_used_bytes", "SPIFFS ocupado", "bytes"),
    ]:
        value = number(fields.get(key))
        if value is not None and value >= 0:
            metrics.append({"label": label, "value": value, "unit": unit})
    notes = [
        "Heap interno: MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT. PSRAM: MALLOC_CAP_SPIRAM. Os campos legados heap_* usam MALLOC_CAP_DEFAULT e não representam somente SRAM interna.",
        "Memória livre: heap_caps_get_free_size. Mínimos históricos por região desde o boot: heap_caps_get_minimum_free_size. Total: heap_caps_get_total_size. Maior bloco livre: heap_caps_get_largest_free_block.",
        "A ocupação dinâmica é total menos livre, medida ao final da rodada antes do rodapé de memória e da liberação dos buffers. Inclui runtime, cache de imagens e relatório. Os mínimos históricos não são reiniciados a cada rodada.",
        "SRAM estática: intervalos do linker para DRAM (.data, .bss, .noinit) e IRAM, incluindo alinhamento. Flash: esp_image_get_metadata na partição obtida por esp_ota_get_running_partition. A ocupação da aplicação não inclui bootloader, tabela de partições ou SPIFFS; SPIFFS só é medido quando montado.",
        "No TFLite, linhas restauradas de checkpoints conservam as medições da execução original. O resumo de memória pertence ao boot e à rodada que publicaram este CSV.",
    ]
    return metrics, notes


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
            rows = []
            for row in reader:
                # ESP32 footers are single-field comment records, not images.
                first = columns[0] if columns else ""
                if str(row.get(first) or "").startswith("#") and all(
                        v in (None, "") for k, v in row.items() if k != first):
                    continue
                rows.append({k: (v or "") for k, v in row.items() if k is not None})
        except csv.Error:
            return result
        result.update(kind="csv", columns=columns, rows=rows, metrics=metrics_for_rows(rows))
        memory, notes = memory_metrics(text)
        result["metrics"].extend(memory)
        result["memory_notes"] = notes
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

