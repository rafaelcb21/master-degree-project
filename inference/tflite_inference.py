"""Execute original TFLite models with the same test cases as the WASM adapters."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from adapters.registry import create_adapter


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def rgb565_to_rgb888(raw):
    """Match WASM load16_u (little endian) and its bit-replication expansion."""
    if len(raw) % 2:
        raise ValueError("RGB565 requer um número par de bytes.")
    pixels = np.frombuffer(raw, dtype="<u2")
    red, green, blue = (pixels >> 11) & 31, (pixels >> 5) & 63, pixels & 31
    return np.stack(((red << 3) | (red >> 2),
                     (green << 2) | (green >> 4),
                     (blue << 3) | (blue >> 2)), axis=-1).astype(np.uint8)


def tensor_info(detail):
    dtype = np.dtype(detail["dtype"])
    if dtype not in (np.dtype("uint8"), np.dtype("int8")):
        raise ValueError(f"Este runner requer entrada/saída quantizada de 8 bits: {dtype}")
    quant = detail["quantization_parameters"]
    scales, zeros = quant["scales"], quant["zero_points"]
    if len(scales) != 1 or len(zeros) != 1 or scales[0] <= 0:
        raise ValueError("Entrada/saída requer quantização por tensor com escala positiva.")
    shape = [int(n) for n in detail["shape"]]
    if not shape or any(n <= 0 for n in shape):
        raise ValueError(f"Shape inválido: {shape}")
    return {"name": detail["name"], "shape": shape, "elements": int(np.prod(shape)),
            "dtype": dtype.name, "scale": float(scales[0]), "zero_point": int(zeros[0])}


def prepare_input(adapter, case, info):
    if adapter.config.input_format == "rgb565":
        if info["dtype"] != "uint8":
            raise ValueError("RGB565 requer entrada TFLite uint8 antes da camada QUANTIZE.")
        raw = case.path.read_bytes()
        if len(raw) != info["elements"] // 3 * 2:
            raise ValueError(f"Tamanho RGB565 inválido: {len(raw)} bytes")
        pixels = rgb565_to_rgb888(raw)
    else:
        # Reuse BGR->RGB and any int8 normalization from the WASM adapter.
        pixels = np.frombuffer(adapter.prepare_input(case, info), dtype=info["dtype"])
    return np.ascontiguousarray(pixels.reshape(info["shape"]))


def run_tflite(package, *, threads=1):
    import tensorflow as tf

    if threads < 1:
        raise ValueError("threads deve ser positivo")
    model_path = package.resolve(package.config.tflite)
    model_bytes = model_path.read_bytes()
    interpreter = tf.lite.Interpreter(
        model_content=model_bytes, num_threads=threads,
        experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES,
    )
    interpreter.allocate_tensors()
    inputs, outputs = interpreter.get_input_details(), interpreter.get_output_details()
    if len(inputs) != 1 or len(outputs) != 1:
        raise ValueError("Este runner requer um tensor de entrada e um de saída.")
    input_info, output_info = tensor_info(inputs[0]), tensor_info(outputs[0])
    if len(input_info["shape"]) != 4 or input_info["shape"][0] != 1 or input_info["shape"][-1] != 3:
        raise ValueError("Entrada esperada: NHWC, batch 1, três canais RGB.")
    adapter = create_adapter(package)
    cases = list(adapter.discover_cases())
    started = datetime.now(timezone.utc)
    destination = package.root / "reports_tflite" / started.strftime("%Y%m%dT%H%M%S%fZ")
    destination.mkdir(parents=True, exist_ok=False)
    records, errors = [], []
    for index, case in enumerate(cases, 1):
        relative = case.path.relative_to(package.root).as_posix()
        try:
            image = prepare_input(adapter, case, input_info)
            interpreter.set_tensor(inputs[0]["index"], image)
            before = time.perf_counter_ns()
            interpreter.invoke()
            elapsed = (time.perf_counter_ns() - before) / 1_000_000
            output = interpreter.get_tensor(outputs[0]["index"]).reshape(-1)
            record = adapter.evaluate_output(case, output.tobytes(), output_info)
            # Full output vector is retained even when the text shows only Top-K.
            record.update(file=relative, raw_sha256=sha256(case.path.read_bytes()),
                          input_sha256=sha256(image.tobytes()), inference_ms=elapsed,
                          quantized=output.tolist(),
                          scores=((output.astype(np.float64) - output_info["zero_point"]) * output_info["scale"]).tolist())
            records.append(record)
        except (OSError, ValueError, RuntimeError) as error:
            errors.append({"file": relative, "error": str(error)})
        if index % 100 == 0 or index == len(cases):
            print(f"{package.root.name}: {index}/{len(cases)}; erros={len(errors)}", flush=True)

    results = {"records": records, "errors": errors, "processed": len(records)}
    text = adapter.build_report(results).replace("INFERÊNCIA WASM", "INFERÊNCIA TFLITE", 1)
    text += f"\nErros de processamento: {len(errors)}\n"
    text += "\n".join(f"{error['file']} | {error['error']}" for error in errors)
    (destination / "inference-report.txt").write_text(text + "\n", encoding="utf-8")
    summary = {"attempted": len(cases), "processed": len(records), "errors": len(errors)}
    if records:
        summary["mean_inference_ms"] = sum(r["inference_ms"] for r in records) / len(records)
        if "right" in records[0]:
            summary.update(correct=sum(r["right"] for r in records), invalid=sum(r["invalid"] for r in records))
            summary["accuracy_percent"] = 100 * summary["correct"] / len(records)
    metadata = {"schema_version": 1, "runtime": "tensorflow.lite.Interpreter", "tensorflow_version": tf.__version__,
                "numpy_version": np.__version__, "python_version": platform.python_version(),
                "platform": platform.platform(), "threads": threads,
                "op_resolver": "BUILTIN_WITHOUT_DEFAULT_DELEGATES", "warmup_runs": 0,
                "timing": "invoke only; excludes input preparation, tensor copies and file IO; first invocation included",
                "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
                "model": package.root.name, "model_file": package.config.tflite,
                "model_sha256": sha256(model_bytes), "manifest_sha256": sha256((package.root / "model.toml").read_bytes()),
                "input_format": package.config.input_format, "input_tensor": input_info,
                "output_tensor": output_info, "summary": summary,
                "preprocessing": "RGB565 LE -> RGB888 by bit replication" if package.config.input_format == "rgb565" else "Same prepare_input adapter as WASM"}
    (destination / "results-report.json").write_text(json.dumps({"metadata": metadata, **results}, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (destination / "samples-report.csv").open("w", encoding="utf-8", newline="") as stream:
        columns = ["name_image", "ok", "result", "label", "right", "invalid", "inference_ms", "quantized", "scores", "error"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({"name_image": record["file"], "ok": 1,
                             "result": record.get("result", record.get("top", [{}])[0].get("index", "")),
                             "label": record.get("label", ""), "right": int(record["right"]) if "right" in record else "",
                             "invalid": record.get("invalid", ""), "inference_ms": record["inference_ms"],
                             "quantized": json.dumps(record["quantized"]), "scores": json.dumps(record["scores"])})
        for error in errors:
            writer.writerow({"name_image": error["file"], "ok": 0, "error": error["error"]})
    print(f"Relatórios: {destination}\nResumo: {summary}", flush=True)
    return destination, metadata
