from pathlib import Path

from wasmtime import (
    Func,
    FuncType,
    Instance,
    Memory,
    Module,
    Store,
)

from extractor.layer_params import (
    FORMAT_FLAG_ADDR,
    FORMAT_RGB565,
)


DEBUG_IMPORTS = {
    "log",
    "logf",
    "log64",
}


def _instantiate_wasm(
    wasm_path,
):
    """
    Carrega e instancia o módulo WASM uma única vez.

    Também atende aos imports de debug env.log, env.logf e
    env.log64, caso ainda existam no módulo.
    """

    wasm_path = Path(
        wasm_path
    )

    if not wasm_path.is_file():
        raise FileNotFoundError(
            "Arquivo WASM não encontrado: "
            f"{wasm_path}"
        )

    wasm_bytes = (
        wasm_path.read_bytes()
    )

    store = Store()

    module = Module(
        store.engine,
        wasm_bytes,
    )

    imports = []

    for import_type in module.imports:
        module_name = (
            import_type.module
        )

        import_name = (
            import_type.name
        )

        extern_type = (
            import_type.type
        )

        if (
            module_name == "env"
            and import_name in DEBUG_IMPORTS
            and isinstance(
                extern_type,
                FuncType,
            )
        ):
            imports.append(
                Func(
                    store,
                    extern_type,
                    lambda *args: None,
                )
            )
            continue

        raise RuntimeError(
            "Import WASM não suportado: "
            f"{module_name}.{import_name}"
        )

    instance = Instance(
        store,
        module,
        imports,
    )

    exports = instance.exports(
        store
    )

    required_exports = [
        "memory",
        "run_mobilenetv2",
        "get_result_ptr",
    ]

    missing = []

    for name in required_exports:
        try:
            exports[name]
        except KeyError:
            missing.append(
                name
            )

    if missing:
        raise RuntimeError(
            "WASM não possui exports obrigatórios: "
            + ", ".join(missing)
        )

    memory = exports[
        "memory"
    ]

    if not isinstance(
        memory,
        Memory,
    ):
        raise RuntimeError(
            "Export 'memory' não é uma "
            "memória WebAssembly."
        )

    return {
        "store": store,
        "instance": instance,
        "memory": memory,
        "run": exports[
            "run_mobilenetv2"
        ],
        "get_result_ptr": exports[
            "get_result_ptr"
        ],
    }


"""Execução WASM compartilhada; interpretação dos resultados pertence ao adapter."""
import math

from extractor.layer_params import FORMAT_FLAG_ADDR, FORMAT_RGB565
from extractor.tflite_utils import scale_scalar, zp_scalar, tensor_shape_list


def tensor_info(tensor):
    if tensor.Type() not in (3, 9):
        raise ValueError("layerparam-v1 suporta apenas entrada/saída uint8 ou int8.")
    scale = float(scale_scalar(tensor))
    if scale <= 0:
        raise ValueError("Tensor deve ter escala de quantização positiva.")
    shape = tensor_shape_list(tensor)
    return {"shape": shape, "elements": math.prod(shape), "scale": scale,
            "zero_point": int(zp_scalar(tensor)), "dtype": "uint8" if tensor.Type() == 3 else "int8"}


def run_wasm_inference(*, wasm_path, adapter, cases, input_info, output_info, input_ptr, slot_bytes):
    runtime = _instantiate_wasm(wasm_path)
    store, memory = runtime["store"], runtime["memory"]
    synthetic = adapter.config.synthetic_layer_count
    expected = input_info["elements"] // 3 * 2 if synthetic else input_info["elements"]
    if expected > slot_bytes or input_ptr < 0 or input_ptr + expected > memory.data_len(store):
        raise ValueError("Entrada ultrapassa o slot ou a memória WASM.")
    records, errors = [], []
    for index, case in enumerate(cases, 1):
        try:
            data = adapter.prepare_input(case, input_info)
            if len(data) != expected:
                raise ValueError(f"Tamanho RAW inválido: {len(data)}; esperado={expected}")
            memory.write(store, data, input_ptr)
            if synthetic:
                memory.write(store, bytes([FORMAT_RGB565]), FORMAT_FLAG_ADDR)
            runtime["run"](store)
            ptr = int(runtime["get_result_ptr"](store))
            end = ptr + output_info["elements"]
            if ptr < 0 or end > memory.data_len(store):
                raise ValueError("Saída ultrapassa a memória WASM.")
            output = bytes(memory.read(store, ptr, end))
            records.append(adapter.evaluate_output(case, output, output_info))
        except Exception as exc:
            errors.append({"file": str(case.path), "error": str(exc)})
        if index % 100 == 0:
            print(f"RAW processadas: {index}/{len(cases)}", flush=True)
    return {"records": records, "errors": errors, "processed": len(records)}
