# Research Explorer

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

A local website for browsing documentation and reports across this repository, including model packages and ESP32. The interface uses HTML, CSS and TypeScript; a small Python server discovers and reads files.

## Start

Requires **Python 3.10 or later**. From the repository root:

```powershell
python web/server/app.py
```

Open **http://127.0.0.1:8000**. Keep the terminal open; press `Ctrl+C` to stop. If `python` is unavailable on Windows, try `py -3 web/server/app.py` or activate your Python environment. The ESP-IDF Python environment can also run this server.

You do not need inference dependencies or Node.js to browse the site. Compiled JavaScript is included in `public/app.js`. Data comes from existing files on disk; starting the site does not run the pipeline or firmware.

If the port is busy:

```powershell
python web/server/app.py --port 8001
```

Then open http://127.0.0.1:8001. The server listens only on the local computer.

## Navigation

### ESP32 over USB (Windows / ESP-IDF 5.3.1)

1. Connect the ESP32 using a USB data cable. Close ESP-IDF Monitor or other programs using its COM port.
2. Open **ESP32 · USB** and click **Check connection**. Select the port and the TFLite Micro or WASM/AOT project. No actions are enabled without a detected port; the server checks again when starting and uses esptool to confirm a classic ESP32 chip before building/flashing. Serial adapters are not assumed to be ESP32 boards.
3. **Build and flash** activates ESP-IDF, builds the selected project (`build-tflite` for TFLite, `build` for WASM), checks the chip again, and flashes it. **Restart benchmark** skips compilation and flashing, and runs the firmware already on the board. Select the matching project. TFLite with checkpoints resumes the current experiment; increment `BENCHMARK_RUN_ID` and rebuild to start from image 1. Firmware without persistence loses reports held only in RAM after reset.
4. Follow build output and serial logs on the page. Keep the server running and USB connected while flashing. **Close monitor** releases the serial port without deliberately resetting the board; it does not stop inference. The button is disabled during build/flash. Closing the server terminates its child processes, so do not close it during flashing.
5. With automatic import enabled, the site reads the IP from serial logs and downloads reports when the firmware announces its HTTP server. The computer and board still need network connectivity. Failed imports can be retried with **Import from ESP32**. The serial monitor must remain open for automatic import.

Configure `esp32.idf_root`, `esp32.python`, and `esp32.tools` in `web/config.json` for your ESP-IDF installation. The supplied values use `C:/Espressif` and ESP-IDF 5.3.1. No manual ESP-IDF terminal is required. The server runs PowerShell's `export.ps1` and `idf.py` in the same child environment. This controls the existing firmware projects; model, Wi-Fi and preprocessing settings still come from their source/configuration files. USB boot/reset requires the board's automatic reset circuit; if esptool cannot identify it, the operation fails with logs instead of proceeding. Desktop and USB executions cannot start concurrently within the same server.

### Run desktop models

Open **Run models** in the sidebar. Select Drowsiness or MobileNetV2 Alpha 0.35, then WASM or TFLite and click **Run**. The page shows live logs (the latest 1,500 lines), status and links to the run's reports. Only one execution is allowed at a time per server. Navigation and page reloads do not stop it; keep the server running. Stopping the server terminates its active process. Execution status is held in memory; report folders remain on disk.

WASM runs `main.py --model <model>` with `.venv-models`, including extraction, WAT/WASM generation and inference. TFLite runs `run_tflite.py --model <model>` with `.venv-tflite`. The complete configured dataset is used. Environments must already have their dependencies installed. To use other Python environments, add `"runner_python": {"wasm": "path/to/python.exe", "tflite": "path/to/python.exe"}` to `web/config.json` (paths relative to the repository root or absolute). Restart the server after changing configuration. Reports use separate UTC folders; WASM files in `generated/` are replaced. Do not launch another benchmark manually while collecting timings.

### Import ESP32 results

Click **Import from ESP32**, select the firmware (TFLite Micro or WebAssembly / AOT), and enter the board's IP address, for example `192.168.0.18`. Wait until the benchmark finishes; the computer must be able to reach the board on port 80.

The local server downloads `/report` into `ESP32/cnn_tflite_esp32/reports/<UTC timestamp>/report.csv` or `ESP32/cnn_webassembly_esp32/reports/<UTC timestamp>/report.csv`. TFLite also downloads `/metadata` as `metadata.json`. Each import creates a new folder such as `20261006T234046384562Z`. If metadata fails, the CSV is kept and a warning appears. The site refreshes its index and offers a link to the imported report. Opening the board's `/report` directly still uses the browser's download folder. Restart the local server after updating the site.

- **EN / PT:** switches the entire interface language, including menus, filters, metrics, dates and numbers. Your preference is saved in the browser. It also selects the library language and opens the current document's translation when available. Original report contents and downloaded files remain unchanged.
- **Visão geral (Overview):** projects, counts and recently modified reports.
- **Relatórios (Reports):** files grouped by folder, with title/path search and project filtering.
- **Documentação (Documentation):** rendered Markdown, section navigation, code copying and Portuguese/English/all language filters. The language button opens the matching translation even when filenames differ.
- **Atualizar índice (Refresh index):** discovers new files and removes deleted ones. Use it or reopen a file to read changed contents.
- **Baixar original (Download original):** saves the source file without changing its contents.

Links between indexed documents open within the site. References to code and other files outside the library remain identified in the text without opening those files. External HTTPS images are allowed; local images and Mermaid diagrams do not have a dedicated viewer in this version. Mermaid blocks appear as code. The interface and documentation are available in Portuguese and English.

### Report views

| Recognized format | Presentation |
|---|---|
| ESP32 CSV | Accuracy, failures, average times, per-sample charts and table |
| Python binary inference | Results, accuracy, invalid predictions and processing errors |
| ImageNet Top-K | Image selection, chart of the first five classes and full table |
| Final memory layout | Region distribution, addresses and sizes |
| `op=...` weight and quantization records | Extracted fields in a table |
| Other TXT, JSON and LOG files | Original content in a text panel |

Tables support column sorting, value search and pages of 50 rows. Reports containing `right` also provide a filter for records that are not correct. Original content remains available below the visualization.

CSV accuracy uses records with `ok=1` and `right` equal to `0` or `1`. Average times use finite, nonnegative values from successful records. In binary inference, invalid predictions and ties with `right=0` remain in the denominator. Top-K scores are model outputs, not accuracy.

## Discovery and configuration

Edit [`config.json`](config.json) to change the port, exclusions, formats and read limit. Restart the server after changing configuration.

- All `.md` files in allowed directories are indexed, including projects with their own `.git` directory.
- Reports are `.txt`, `.csv`, `.json` or `.log` files within folders named `reports`, `report`, `relatorios` or `relatórios`, or whose names contain `report`/`relatório`.
- `build`, `managed_components`, `.git`, `node_modules`, virtual environments and other configured folders are excluded. Symbolic links are not traversed.
- `.pt-BR.md` files are classified as Portuguese; other Markdown files as English. Translation matching uses the document's `English` and `Português (Brasil)` links.
- Files up to 16 MiB can be opened by default. Larger files appear in the catalog but require increasing `max_file_bytes` to read them.

Files remain in their original folders. Library search checks titles and paths; table search checks loaded records. The site does not fetch reports directly from ESP32: save the CSV received from `/report` in the repository, then refresh the index.

## Structure and development

```text
web/
  index.html          Entry page
  config.json         Server and discovery settings
  src/app.ts          Navigation, reader and visualizations
  styles/styles.css   Styles and responsive layout
  public/             Compiled JavaScript and icon
  server/app.py       HTTP server and catalog
  server/reports.py   Report format readers
  tests/              Reader and navigation tests
```

To edit TypeScript, install Node.js 22+ and run:

```powershell
cd web
npm ci
npm run build
```

Include updated `public/app.js` with changes to `src/app.ts`. `npm run watch` rebuilds during editing; keep the Python server in another terminal and refresh the page to see changes. HTML and CSS are served directly.

### Checks

From the repository root:

```powershell
python -m unittest discover -s web/tests -v
```

With the server running on port 8000, from `web/`:

```powershell
npm run test:ui
```

The test uses Microsoft Edge installed on Windows. On other systems, run `npx playwright install chromium` first. For another port, set `EXPLORER_URL`. Screenshots go into `web/test-results/`, which Git ignores. Tests check the example reports included in the repository.

The server exposes only indexed documents/reports and site assets. Markdown is sanitized before rendering. It is intended for local browsing, without authentication or public deployment.
