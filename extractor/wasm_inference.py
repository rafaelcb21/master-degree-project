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


def run_wasm_inference(
    *,
    wasm_path,
    datasets,
    classes,
    input_ptr,
    input_bytes,
    result_count,
):
    """
    Executa o mesmo módulo WASM para todas as imagens RAW.

    datasets:
        Lista de dicionários com "dir" e "label".

    classes:
        Ordem real das classes na saída da rede.
    """

    input_ptr = int(
        input_ptr
    )

    input_bytes = int(
        input_bytes
    )

    result_count = int(
        result_count
    )

    if result_count <= 0:
        raise RuntimeError(
            "result_count deve ser maior que zero."
        )

    if len(classes) != result_count:
        raise RuntimeError(
            "Quantidade de classes incompatível: "
            f"classes={len(classes)}, "
            f"result_count={result_count}."
        )

    runtime = _instantiate_wasm(
        wasm_path
    )

    store = runtime[
        "store"
    ]

    memory = runtime[
        "memory"
    ]

    run = runtime[
        "run"
    ]

    get_result_ptr = runtime[
        "get_result_ptr"
    ]

    memory_bytes = int(
        memory.data_len(
            store
        )
    )

    if input_ptr < 0:
        raise RuntimeError(
            f"INPUT_PTR inválido: {input_ptr}."
        )

    if (
        input_ptr
        + input_bytes
        > memory_bytes
    ):
        raise RuntimeError(
            "Entrada RGB565 ultrapassa a memória WASM: "
            f"input_ptr={input_ptr}, "
            f"input_bytes={input_bytes}, "
            f"memory_bytes={memory_bytes}."
        )

    if (
        FORMAT_FLAG_ADDR < 0
        or FORMAT_FLAG_ADDR >= memory_bytes
    ):
        raise RuntimeError(
            "FORMAT_FLAG_ADDR fora da memória WASM: "
            f"{FORMAT_FLAG_ADDR}."
        )

    records = []
    errors = []
    folders = []

    total_files = 0

    for dataset in datasets:
        directory = Path(
            dataset["dir"]
        )

        label = int(
            dataset["label"]
        )

        if not directory.exists():
            errors.append(
                {
                    "file": None,
                    "directory": str(
                        directory
                    ),
                    "error": (
                        "Pasta não encontrada."
                    ),
                }
            )
            continue

        files = sorted(
            path
            for path in directory.iterdir()
            if (
                path.is_file()
                and path.suffix.lower()
                == ".raw"
            )
        )

        folders.append(
            {
                "directory": str(
                    directory
                ),
                "label": label,
                "files": len(
                    files
                ),
            }
        )

        for file_index, filepath in enumerate(
            files,
            start=1,
        ):
            total_files += 1

            try:
                image = (
                    filepath.read_bytes()
                )

                if (
                    len(image)
                    != input_bytes
                ):
                    errors.append(
                        {
                            "file": filepath.name,
                            "directory": str(
                                directory
                            ),
                            "error": (
                                "Tamanho RAW inválido: "
                                f"{len(image)} bytes; "
                                f"esperado={input_bytes}."
                            ),
                        }
                    )
                    continue

                memory.write(
                    store,
                    image,
                    input_ptr,
                )

                memory.write(
                    store,
                    bytes([
                        FORMAT_RGB565
                    ]),
                    FORMAT_FLAG_ADDR,
                )

                run(
                    store
                )

                result_ptr = int(
                    get_result_ptr(
                        store
                    )
                )

                if result_ptr < 0:
                    raise RuntimeError(
                        "get_result_ptr() retornou "
                        f"endereço inválido: {result_ptr}."
                    )

                if (
                    result_ptr
                    + result_count
                    > memory_bytes
                ):
                    raise RuntimeError(
                        "Saída ultrapassa a memória WASM: "
                        f"result_ptr={result_ptr}, "
                        f"result_count={result_count}, "
                        f"memory_bytes={memory_bytes}."
                    )

                output = memory.read(
                    store,
                    result_ptr,
                    (
                        result_ptr
                        + result_count
                    ),
                )

                quantized = [
                    int(value)
                    for value in output
                ]

                percentages = [
                    round(
                        (
                            value
                            / 255.0
                        )
                        * 100.0,
                        2,
                    )
                    for value
                    in quantized
                ]

                total_probability = sum(
                    quantized
                )

                max_value = max(
                    quantized
                )

                winners = [
                    index
                    for index, value
                    in enumerate(
                        quantized
                    )
                    if value == max_value
                ]

                invalid = (
                    total_probability == 0
                    or len(winners) != 1
                )

                if invalid:
                    result = -1
                    predicted_class = None
                    right = 0
                else:
                    winner_index = (
                        winners[0]
                    )

                    predicted_class = (
                        classes[
                            winner_index
                        ]
                    )

                    result = int(
                        predicted_class[
                            "label"
                        ]
                    )

                    right = int(
                        result == label
                    )

                records.append(
                    {
                        "directory": str(
                            directory
                        ),
                        "file": filepath.name,
                        "file_index": file_index,
                        "label": label,
                        "result": result,
                        "right": right,
                        "invalid": invalid,
                        "result_ptr": result_ptr,
                        "quantized": quantized,
                        "percentages": percentages,
                    }
                )

            except Exception as exc:
                errors.append(
                    {
                        "file": filepath.name,
                        "directory": str(
                            directory
                        ),
                        "error": str(
                            exc
                        ),
                    }
                )

    processed = len(
        records
    )

    correct = sum(
        record["right"]
        for record in records
    )

    invalid_count = sum(
        1
        for record in records
        if record["invalid"]
    )

    accuracy = (
        (
            correct
            / processed
        )
        * 100.0
        if processed
        else 0.0
    )

    return {
        "wasm_path": str(
            wasm_path
        ),
        "input_ptr": input_ptr,
        "input_bytes": input_bytes,
        "format_flag_addr": (
            FORMAT_FLAG_ADDR
        ),
        "format_rgb565": (
            FORMAT_RGB565
        ),
        "result_count": result_count,
        "classes": classes,
        "folders": folders,
        "records": records,
        "errors": errors,
        "total_files": total_files,
        "processed": processed,
        "correct": correct,
        "invalid": invalid_count,
        "accuracy": accuracy,
    }


def wasm_inference_to_text(
    inference,
):
    lines = []

    lines.append(
        "INFERENCIA WASM"
    )
    lines.append(
        "=" * 100
    )

    lines.append(
        "WASM: "
        f"{inference['wasm_path']}"
    )

    lines.append(
        "INPUT_PTR: "
        f"{inference['input_ptr']}"
    )

    lines.append(
        "INPUT_BYTES: "
        f"{inference['input_bytes']}"
    )

    lines.append(
        "FORMAT_FLAG_ADDR: "
        f"{inference['format_flag_addr']}"
    )

    lines.append(
        "FORMAT_RGB565: "
        f"{inference['format_rgb565']}"
    )

    lines.append(
        "RESULT_COUNT: "
        f"{inference['result_count']}"
    )

    lines.append("")
    lines.append(
        "CLASSES"
    )
    lines.append(
        "=" * 100
    )

    for index, item in enumerate(
        inference["classes"]
    ):
        lines.append(
            f"output[{index}] "
            f"name={item['name']} "
            f"label={item['label']}"
        )

    lines.append("")
    lines.append(
        "RESULTADOS"
    )
    lines.append(
        "=" * 100
    )

    classes = inference[
        "classes"
    ]

    current_directory = None

    for record in inference[
        "records"
    ]:
        if (
            record["directory"]
            != current_directory
        ):
            current_directory = (
                record["directory"]
            )

            lines.append("")
            lines.append(
                "Pasta: "
                f"{current_directory}"
            )
            lines.append(
                "-" * 100
            )

        output_parts = []

        for class_index, class_info in enumerate(
            classes
        ):
            output_parts.append(
                (
                    f"{class_info['name']}="
                    f"{record['quantized'][class_index]} "
                    "("
                    f"{record['percentages'][class_index]:.2f}%"
                    ")"
                )
            )

        if record["invalid"]:
            status = "INVALIDO"
        elif record["right"]:
            status = "CERTO"
        else:
            status = "ERRADO"

        lines.append(
            f"{record['file']} | "
            + " | ".join(
                output_parts
            )
            + " | "
            f"result={record['result']} "
            f"label={record['label']} "
            f"right={record['right']} "
            f"| {status}"
        )

    if inference["errors"]:
        lines.append("")
        lines.append(
            "ERROS"
        )
        lines.append(
            "=" * 100
        )

        for error in inference[
            "errors"
        ]:
            file_name = (
                error["file"]
                if error["file"]
                is not None
                else "-"
            )

            lines.append(
                f"{error['directory']} | "
                f"{file_name} | "
                f"{error['error']}"
            )

    lines.append("")
    lines.append(
        "RESUMO"
    )
    lines.append(
        "=" * 100
    )

    lines.append(
        "Arquivos RAW encontrados: "
        f"{inference['total_files']}"
    )

    lines.append(
        "Inferencias executadas: "
        f"{inference['processed']}"
    )

    lines.append(
        "Erros de processamento: "
        f"{len(inference['errors'])}"
    )

    lines.append(
        "Invalidos/empates: "
        f"{inference['invalid']}"
    )

    lines.append(
        "Acertos: "
        f"{inference['correct']}"
    )

    lines.append(
        "Acuracia: "
        f"{inference['correct']}/"
        f"{inference['processed']} "
        f"= {inference['accuracy']:.2f}%"
    )

    return "\n".join(
        lines
    )
