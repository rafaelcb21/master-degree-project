from pathlib import Path


MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)

WAT_TEMPLATE_PATH = Path(
    "wat/model_template.wat"
)

OUT_WAT_PATH = Path(
    "generated/model.wat"
)

REPORTS_DIR = Path(
    "reports"
)

NUM_SLOTS = 3

BATCH = 1

ALIGN = 16

KERNEL_BASE_HINT = 2048