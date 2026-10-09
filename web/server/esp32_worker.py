"""Runs under ESP-IDF's Python, separate from the website's environment."""
import argparse
import codecs
import json
import os
from pathlib import Path
import subprocess
import sys
import threading


def ports():
    from serial.tools.list_ports import comports
    return [{"port": p.device, "description": p.description} for p in comports()]


def phase(name):
    print("@@esp32 " + json.dumps({"phase": name}), flush=True)


def probe(port):
    if port not in [p["port"] for p in ports()]:
        raise RuntimeError("Selected serial port is no longer connected.")
    # A USB serial adapter alone does not prove an ESP32 is connected.
    subprocess.run([sys.executable, "-m", "esptool", "--chip", "esp32", "--port", port,
                    "--after", "no_reset", "chip_id"], check=True, timeout=30,
                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def monitor(port):
    import serial
    from esptool.reset import HardReset
    stop = threading.Event()
    def commands():
        sys.stdin.readline()
        stop.set()
    threading.Thread(target=commands, daemon=True).start()
    with serial.Serial(port, 115200, timeout=.5) as connection:
        connection.dtr = False
        HardReset(connection)()
        phase("monitoring")
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while not stop.is_set():
            if port not in [p["port"] for p in ports()]:
                raise RuntimeError("ESP32 disconnected from USB.")
            data = connection.read(max(1, min(connection.in_waiting, 4096)))
            if data:
                print(decoder.decode(data), end="", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ports", action="store_true")
    parser.add_argument("--port")
    parser.add_argument("--action", choices=["flash", "restart"])
    args = parser.parse_args()
    if args.ports:
        print(json.dumps(ports()))
        return
    phase("checking")
    probe(args.port)
    if args.action == "flash":
        script = Path(__file__).with_name("idf_build.ps1")
        phase("building")
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "build"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        phase("checking")
        probe(args.port)
        phase("flashing")
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "flash"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    monitor(args.port)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ESP32 error: {error}", flush=True)
        raise SystemExit(1)
