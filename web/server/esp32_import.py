"""Download completed ESP32 benchmarks into separate UTC report folders."""
import csv
import io
import ipaddress
import json
from datetime import datetime, timezone, timedelta
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

PROJECTS = {"tflite": "cnn_tflite_esp32", "wasm": "cnn_webassembly_esp32"}
MAX_BYTES = 16 * 1024 * 1024


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(ip, endpoint):
    opener = build_opener(ProxyHandler({}), NoRedirects())
    with opener.open(Request(f"http://{ip}:80/{endpoint}"), timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("response_too_large")
    return data


def import_reports(root, ip, runtime):
    if not isinstance(runtime, str) or runtime not in PROJECTS:
        raise ValueError("invalid_runtime")
    try:
        address = ipaddress.IPv4Address(ip.strip())
    except (ValueError, AttributeError):
        raise ValueError("invalid_ip") from None
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_link_local:
        raise ValueError("invalid_ip")
    root = root.resolve()
    destination = (root / "ESP32" / PROJECTS[runtime] / "reports").resolve()
    if not destination.is_relative_to(root):
        raise ValueError("invalid_destination")
    report = download(str(address), "report")
    try:
        header = next(csv.reader(io.StringIO(report.decode("utf-8-sig"))))
        if not {"name_image", "ok", "inference_ms"}.issubset(header):
            raise ValueError("invalid_report")
    except (UnicodeError, StopIteration, csv.Error):
        raise ValueError("invalid_report") from None
    files = {"report.csv": report}
    warnings = []
    if runtime == "tflite":
        try:
            metadata = download(str(address), "metadata")
            value = json.loads(metadata)
            if not isinstance(value, dict) or value.get("runtime") != "TensorFlow Lite Micro":
                raise ValueError("invalid_metadata")
            files["metadata.json"] = metadata
        except (OSError, ValueError):
            warnings.append("metadata_unavailable")
    started = datetime.now(timezone.utc)
    while True:
        folder = destination / started.strftime("%Y%m%dT%H%M%S%fZ")
        try:
            folder.mkdir(parents=True, exist_ok=False)
            destination = folder
            break
        except FileExistsError:
            started += timedelta(microseconds=1)
    for name, data in files.items():
        with (destination / name).open("xb") as output:
            output.write(data)
    return {"folder": destination.relative_to(root).as_posix(),
            "files": [(destination / name).relative_to(root).as_posix() for name in files],
            "warnings": warnings}
