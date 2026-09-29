from pathlib import Path
from wasmtime import wat2wasm

def compile_wat_to_wasm(
    wat_path,
    wasm_path,
):
    """
    Converte o WAT gerado para o binário WASM.

    A função utiliza o parser oficial do Wasmtime,
    portanto não depende do executável externo wat2wasm.
    """

    wat_path = Path(
        wat_path
    )

    wasm_path = Path(
        wasm_path
    )

    if not wat_path.is_file():
        raise FileNotFoundError(
            "Arquivo WAT não encontrado: "
            f"{wat_path}"
        )

    wat_source = (
        wat_path.read_text(
            encoding="utf-8"
        )
    )

    wasm_binary = bytes(
        wat2wasm(
            wat_source
        )
    )

    if not wasm_binary.startswith(
        b"\x00asm"
    ):
        raise RuntimeError(
            "O binário gerado não possui "
            "o magic number WebAssembly."
        )

    wasm_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    wasm_path.write_bytes(
        wasm_binary
    )

    return {
        "output_path": wasm_path,
        "wasm_bytes": len(
            wasm_binary
        ),
    }
