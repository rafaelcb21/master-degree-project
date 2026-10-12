"""Inspect stored TFLite parameters without executing the model.

Usage: python analyze_tflite_parameters.py model.tflite --output report.json
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path


# Input positions defined by the TFLite operator schema. Unlisted constants
# remain auxiliary/unknown; their presence alone does not imply learned weights.
ROLES = {
    "CONV_2D": {1: "weights", 2: "bias"},
    "DEPTHWISE_CONV_2D": {1: "weights", 2: "bias"},
    "FULLY_CONNECTED": {1: "weights", 2: "bias"},
    "TRANSPOSE_CONV": {1: "weights", 3: "bias"},
    "PRELU": {1: "other"},
    "EMBEDDING_LOOKUP": {1: "weights"},
    "RNN": {1: "weights", 2: "weights", 3: "bias"},
    "UNIDIRECTIONAL_SEQUENCE_RNN": {1: "weights", 2: "weights", 3: "bias"},
    "SVDF": {1: "weights", 2: "weights", 3: "bias"},
    "LSTM": {**{i: "weights" for i in range(1, 12)},
             **{i: "bias" for i in range(12, 16)}, 16: "weights", 17: "bias",
             **{i: "other" for i in range(20, 24)}},
    "UNIDIRECTIONAL_SEQUENCE_LSTM": {**{i: "weights" for i in range(1, 12)},
             **{i: "bias" for i in range(12, 16)}, 16: "weights", 17: "bias",
             **{i: "other" for i in range(20, 24)}},
}
PASSTHROUGH = {"DEQUANTIZE", "QUANTIZE", "CAST", "RESHAPE", "TRANSPOSE", "EXPAND_DIMS", "SQUEEZE"}
AUXILIARY_OPS = PASSTHROUGH | {"MEAN", "SUM", "REDUCE_MAX", "REDUCE_MIN", "REDUCE_PROD",
    "REDUCE_ANY", "REDUCE_ALL", "PAD", "PADV2", "MIRROR_PAD", "RESIZE_BILINEAR",
    "RESIZE_NEAREST_NEIGHBOR", "STRIDED_SLICE", "SLICE", "SPLIT", "SPLIT_V",
    "TILE", "BATCH_TO_SPACE_ND", "SPACE_TO_BATCH_ND", "ARG_MAX", "ARG_MIN",
    "FILL", "BROADCAST_TO", "SHAPE", "RANK", "SIZE"}


def parameter_calculation(opname, role, shape, count):
    product = " × ".join(map(str, shape)) or "1 (escalar)"
    labels = None
    if role == "weights":
        if opname in ("CONV_2D", "TRANSPOSE_CONV") and len(shape) == 4:
            labels = "canais de saída × altura do kernel × largura do kernel × canais de entrada por grupo"
        elif opname == "DEPTHWISE_CONV_2D" and len(shape) == 4:
            labels = "1 × altura do kernel × largura do kernel × canais de saída (entrada × multiplicador)"
        elif opname == "FULLY_CONNECTED" and len(shape) == 2:
            labels = "unidades de saída × unidades de entrada"
    elif role == "bias":
        labels = "bias = produto das dimensões do tensor de bias"
    return (labels + "\n" if labels else "") + f"{product} = {count}"


def analyze(content, name="model.tflite"):
    import tflite

    if len(content) < 8 or content[4:8] != b"TFL3":
        raise ValueError("Arquivo inválido: esperado um modelo TFLite (TFL3).")
    try:
        model = tflite.Model.GetRootAsModel(content, 0)
        if model.Version() != 3 or not 0 < model.SubgraphsLength() <= 1024:
            raise ValueError("Versão ou subgrafos TFLite inválidos.")
        operators = {v: k for k, v in vars(tflite.BuiltinOperator).items() if isinstance(v, int)}
        types = {v: k for k, v in vars(tflite.TensorType).items() if isinstance(v, int)}
        layers, unique, auxiliary, warnings = [], {}, {}, []
        for si in range(model.SubgraphsLength()):
            graph = model.Subgraphs(si)
            if graph.OperatorsLength() > 100000 or graph.TensorsLength() > 100000:
                raise ValueError("Modelo excede o limite de operações/tensores.")
            graph_name = (graph.Name() or b"").decode("utf-8", "replace")
            producers = {}
            ops = []
            for oi in range(graph.OperatorsLength()):
                op = graph.Operators(oi)
                code = model.OperatorCodes(op.OpcodeIndex())
                builtin = max(code.BuiltinCode(), code.DeprecatedBuiltinCode())
                opname = operators.get(builtin, "UNKNOWN")
                if opname == "CUSTOM":
                    opname += ":" + (code.CustomCode() or b"unknown").decode("utf-8", "replace")
                ops.append((op, opname))
                for j in range(op.OutputsLength()):
                    producers[op.Outputs(j)] = oi

            def tensor_info(tid):
                if not 0 <= tid < graph.TensorsLength():
                    raise ValueError("Referência de tensor inválida.")
                tensor = graph.Tensors(tid)
                shape = [int(tensor.Shape(j)) for j in range(tensor.ShapeLength())]
                if any(d < 0 for d in shape):
                    raise ValueError("Tensor constante com dimensão negativa.")
                buffer = model.Buffers(tensor.Buffer())
                if buffer is None:
                    raise ValueError("Buffer de tensor inválido.")
                storage = int(buffer.DataLength())
                if hasattr(buffer, "Size") and buffer.Size():
                    storage = int(buffer.Size())
                    if buffer.Offset() + storage > len(content):
                        raise ValueError("Buffer externo fora do arquivo.")
                return {"id": tid, "name": (tensor.Name() or b"").decode("utf-8", "replace"),
                        "shape": shape, "dtype": types.get(tensor.Type(), str(tensor.Type())),
                        "count": math.prod(shape), "buffer": int(tensor.Buffer()),
                        "storedBytes": storage, "sparse": tensor.Sparsity() is not None,
                        "variable": bool(tensor.IsVariable())}

            def constant(tid):
                visited = set()
                while tid >= 0 and tid not in visited:
                    visited.add(tid)
                    info = tensor_info(tid)
                    if info["storedBytes"] and not info["variable"]:
                        return info
                    producer = producers.get(tid)
                    if producer is None:
                        return None
                    op, opname = ops[producer]
                    if opname not in PASSTHROUGH or not op.InputsLength():
                        return None
                    tid = op.Inputs(0)
                return None

            for oi, (op, opname) in enumerate(ops):
                parts, constants, notes = [], [], []
                roles = ROLES.get(opname, {})
                if opname == "LSTM" and op.InputsLength() == 5:
                    roles = {2: "weights", 3: "bias"}
                counts = {"weights": 0, "bias": 0, "other": 0}
                seen = set()
                for position in range(op.InputsLength()):
                    tid = op.Inputs(position)
                    if tid < 0:
                        continue
                    info = constant(tid)
                    role = roles.get(position)
                    if info is None:
                        if role:
                            notes.append(f"Entrada {position}: parâmetro dinâmico/variável; não contado como parâmetro armazenado.")
                            warnings.append(f"Subgrafo {si}, operação {oi}: entrada de parâmetro {position} sem valor constante armazenado.")
                        continue
                    # Same buffer is one stored parameter even when used by multiple tensors.
                    key = info["buffer"]
                    info = dict(info, input=position, role=role or "auxiliary", sourceTensor=info["id"])
                    info["calculation"] = parameter_calculation(opname, role, info["shape"], info["count"])
                    if role:
                        info["shared"] = key in unique
                        if key in unique and (unique[key]["count"] != info["count"] or unique[key]["dtype"] != info["dtype"]):
                            raise ValueError("Buffer compartilhado com formas/tipos incompatíveis para contagem.")
                        unique.setdefault(key, info)
                        parts.append(info)
                        if key not in seen:
                            counts[role] += info["count"]
                            seen.add(key)
                    else:
                        constants.append(info)
                        auxiliary.setdefault(key, info)
                if opname.startswith(("CUSTOM:", "UNKNOWN")) or (constants and opname not in ROLES and opname not in AUXILIARY_OPS):
                    notes.append("Constantes sem papel de treino inferível: listadas separadamente, fora do total de parâmetros identificados.")
                    warnings.append(f"Subgrafo {si}, operação {oi} ({opname}): classificação de parâmetros pode ser incompleta.")
                total = sum(counts.values())
                layers.append({"subgraph": si, "subgraphName": graph_name, "index": oi, "operator": opname,
                    **counts, "total": total, "parameters": parts, "constants": constants, "notes": notes,
                    "calculation": f"{counts['weights']} pesos + {counts['bias']} bias + {counts['other']} outros = {total}",
                    "outputs": [tensor_info(op.Outputs(j)) for j in range(op.OutputsLength()) if op.Outputs(j) >= 0]})
        totals = {role: sum(t["count"] for t in unique.values() if t["role"] == role) for role in ("weights", "bias", "other")}
        aux = [t for key, t in auxiliary.items() if key not in unique]
        return {"name": name, "generatedAt": datetime.now(timezone.utc).isoformat(), "fileBytes": len(content),
                "subgraphs": model.SubgraphsLength(), "layers": layers, "totals": {**totals, "total": sum(totals.values()),
                "layerSum": sum(layer["total"] for layer in layers),
                "parameterBytes": sum(t["storedBytes"] for t in unique.values()),
                "auxiliaryElements": sum(t["count"] for t in aux)}, "warnings": warnings,
                "method": "Contagem dos parâmetros armazenados identificados no TFLite, por produto das dimensões. Buffers compartilhados contam uma vez no total global. Constantes auxiliares, ativações e metadados de quantização não entram no total. Tensores esparsos usam a forma lógica; bytes indicam armazenamento real. O TFLite não preserva necessariamente as camadas originais nem informa quais parâmetros eram treináveis; operações fundidas e parâmetros dinâmicos exigem essa distinção."}
    except (ValueError, ImportError):
        raise
    except Exception as error:
        raise ValueError("Não foi possível ler a estrutura do modelo TFLite.") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = analyze(args.model.read_bytes(), args.model.name)
        result = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(result, encoding="utf-8")
        else:
            print(result)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
