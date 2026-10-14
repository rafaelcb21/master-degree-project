"""Inspect current artifacts; does not run inference or rebuild firmware."""
from pathlib import Path
import hashlib
import json
import re
import struct
from importlib.metadata import version
from wasmtime import wat2wasm

ROOT = Path(__file__).resolve().parents[1]


def describe(path, data=None):
    data = (ROOT / path).read_bytes() if data is None else data
    return {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    desktop = "models/drowsiness/generated/model.wasm"
    aot_path = "ESP32/cnn_webassembly_esp32/main/main.aot"
    artifacts = [describe(p) for p in (desktop, "models/mobilenetv2_alpha035/generated/model.wasm", aot_path)]
    source = "ESP32/cnn_webassembly_esp32/main/main.wat"
    converted = bytes(wat2wasm((ROOT / source).read_text(encoding="utf-8")))
    desktop_wat = (ROOT / "models/drowsiness/generated/model.wat").read_text(encoding="utf-8")
    desktop_converted = bytes(wat2wasm(desktop_wat))
    asm_path = "ESP32/cnn_webassembly_esp32/build/main.aot.S"
    payload = bytes(int(h, 16) for line in (ROOT / asm_path).read_text().splitlines()
                    if line.startswith(".byte ") for h in re.findall(r"0x([0-9a-fA-F]{2})", line))
    aot = (ROOT / aot_path).read_bytes()
    assert aot[:4] == b"\x00aot" and struct.unpack_from("<I", aot, 4)[0] == 3
    # Version 3: target-info section, then init-data section (aot_loader.c).
    kind, length = struct.unpack_from("<II", aot, 8)
    assert kind == 0
    offset = (16 + length + 3) & ~3
    kind, length = struct.unpack_from("<II", aot, offset)
    assert kind == 1
    imports, count, flags, page_bytes, initial, maximum = struct.unpack_from("<6I", aot, offset + 8)
    assert imports == 0 and count == 1
    result = {
        "scope": "Current filesystem artifacts, not proof of historical execution or flashed firmware",
        "wasmtime_version": version("wasmtime"),
        "artifacts": artifacts,
        "esp32_wat_reconverted": describe(source + " (reconverted in memory)", converted),
        "esp32_wat_reconverted_matches_desktop_wasm": converted == (ROOT / desktop).read_bytes(),
        "desktop_wat_reconverted_matches_desktop_wasm": desktop_converted == (ROOT / desktop).read_bytes(),
        "build_assembly_payload": describe(asm_path + " (.byte payload)", payload),
        "build_assembly_matches_current_aot": payload == aot,
        "esp32_main_wasm_exists": (ROOT / "ESP32/cnn_webassembly_esp32/main/main.wasm").exists(),
        "aot_memory": {"flags": flags, "page_bytes": page_bytes, "initial_pages": initial,
                       "maximum_pages": maximum, "initial_bytes": page_bytes * initial},
    }
    target = ROOT / "analysis/experimental-method/artifacts-report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
