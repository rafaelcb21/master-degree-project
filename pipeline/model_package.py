from dataclasses import dataclass
from pathlib import Path
from pipeline.model_config import ModelConfig

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


@dataclass(frozen=True)
class ModelPackage:
    root: Path
    config: ModelConfig

    @classmethod
    def load(cls, name="drowsiness", models_dir=MODELS_DIR):
        root = Path(models_dir).resolve() / name
        if root.parent != Path(models_dir).resolve():
            raise ValueError("Informe o nome de uma pasta em models/.")
        return cls(root, ModelConfig.load(root / "model.toml"))

    def resolve(self, path):
        return (self.root / path).resolve()

    @property
    def reports_dir(self):
        return self.root / "reports"

    @property
    def wat_path(self):
        return self.root / "generated/model.wat"

    @property
    def wasm_path(self):
        return self.wat_path.with_suffix(".wasm")

    def validate_sources(self):
        for source in (self.config.tflite, self.config.wat_template):
            path = self.resolve(source)
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f"Arquivo ausente ou vazio: {path}")

    @classmethod
    def available(cls, models_dir=MODELS_DIR):
        return [cls.load(p.parent.name, models_dir) for p in sorted(Path(models_dir).glob("*/model.toml"))]
