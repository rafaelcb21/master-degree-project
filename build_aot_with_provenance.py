"""Compile a preserved WASM snapshot and record evidence in a new directory."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OPTIONS = ["--target=xtensa", "--target-abi=ilp32", "--cpu=esp32",
           "--cpu-features=-fp", "--opt-level=3", "--size-level=3",
           "--bounds-checks=1", "--stack-bounds-checks=1"]


def identity(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def run(argv, cwd):
    result = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    return result.returncode, result.stdout.decode("utf-8", errors="replace")


def build(wamrc, wasm, directory, evidence=()):
    wamrc, wasm, directory = Path(wamrc).resolve(), Path(wasm).resolve(), Path(directory).resolve()
    compiler = identity(wamrc)
    source_data = wasm.read_bytes()
    if source_data[:8] != b"\x00asm\x01\x00\x00\x00":
        raise ValueError("Input must be a version-1 binary WASM, not WAT text.")
    # A fresh directory prevents overwriting an old AOT or accepting a stale output.
    directory.mkdir(parents=True, exist_ok=False)
    source, output = directory / "input.wasm", directory / "output.aot"
    source.write_bytes(source_data)
    recorded_source = identity(source)
    argv = [str(wamrc), *OPTIONS, "-o", str(output), str(source)]
    report = {
        "schema_version": 1,
        "scope": "Compilation provenance only; not evidence of flashing or benchmark execution",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "compiler": compiler,
        "source_wasm": {**recorded_source, "original_path": str(wasm), "archive_path": "input.wasm"},
        "command_argv": argv,
        "command_cwd": str(directory),
        "settings": {"target": "xtensa", "abi": "ilp32", "cpu": "esp32", "cpu_features": "-fp",
                     "opt_level": 3, "size_level": 3, "bounds_checks": 1, "stack_bounds_checks": 1},
        "build_evidence": [],
    }
    try:
        version_code, version_text = run([str(wamrc), "--version"], directory)
        report["compiler"].update(version_exit_code=version_code, version_output=version_text)
        if version_code != 0:
            raise RuntimeError("wamrc --version failed; compilation was not started.")
        for index, path in enumerate(evidence):
            path = Path(path).resolve()
            archived = directory / f"evidence-{index}-{path.name}"
            archived.write_bytes(path.read_bytes())
            report["build_evidence"].append({**identity(archived), "original_path": str(path),
                                             "archive_path": archived.name})
        code, log = run(argv, directory)
        (directory / "compile-report.txt").write_text(log, encoding="utf-8")
        report["compile_exit_code"] = code
        report["compile_log"] = {**identity(directory / "compile-report.txt"), "archive_path": "compile-report.txt"}
        if code != 0:
            raise RuntimeError(f"wamrc failed with exit code {code}; see compile-report.txt.")
        if identity(source)["sha256"] != recorded_source["sha256"]:
            raise RuntimeError("Input WASM changed during compilation.")
        if identity(wamrc)["sha256"] != compiler["sha256"]:
            raise RuntimeError("Compiler executable changed during compilation.")
        aot = output.read_bytes()
        if len(aot) < 8 or aot[:4] != b"\x00aot" or struct.unpack_from("<I", aot, 4)[0] != 3:
            raise RuntimeError("Output is not AOT format version 3 required by this runtime.")
        report["output_aot"] = {**identity(output), "archive_path": "output.aot", "format_version": 3}
        report["status"] = "compilation_verified"
    except (OSError, RuntimeError) as error:
        report["error"] = str(error)
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (directory / "provenance-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def verify(manifest):
    manifest = Path(manifest).resolve()
    report = json.loads(manifest.read_text(encoding="utf-8"))
    if report["status"] != "compilation_verified":
        raise ValueError("Manifest does not record a successful verified compilation.")
    for item in [report["source_wasm"], report["output_aot"], report["compile_log"], *report["build_evidence"]]:
        path = (manifest.parent / item["archive_path"]).resolve()
        if path.parent != manifest.parent:
            raise ValueError("Archive path must stay within the manifest directory.")
        actual = identity(path)
        if (actual["sha256"], actual["bytes"]) != (item["sha256"], item["bytes"]):
            raise ValueError(f"Artifact does not match manifest: {path.name}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    compile_parser = commands.add_parser("build")
    compile_parser.add_argument("--wamrc", required=True)
    compile_parser.add_argument("--wasm", type=Path, default=ROOT / "models/drowsiness/generated/model.wasm")
    compile_parser.add_argument("--output-dir", type=Path)
    compile_parser.add_argument("--evidence", type=Path, action="append", default=[])
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify":
            verify(args.manifest)
            print("Archived WASM, AOT, log and build evidence match the manifest.")
        else:
            executable = shutil.which(args.wamrc) or args.wamrc
            directory = args.output_dir or ROOT / "analysis/aot-provenance/reports" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            report = build(executable, args.wasm, directory, args.evidence)
            print(f"Status: {report['status']}\nManifest: {directory / 'provenance-report.json'}")
            if report["status"] != "compilation_verified":
                print(report["error"], file=sys.stderr)
                return 1
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
