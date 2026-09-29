"""Manifestos dos pacotes; caminhos são relativos ao model.toml."""
from dataclasses import dataclass
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


@dataclass(frozen=True)
class ModelConfig:
    name: str
    tflite: str
    wat_template: str
    contract: str
    num_slots: int
    input_format: str
    synthetic_layer: str
    test: dict
    classes: list

    @property
    def synthetic_layer_count(self):
        return int(self.synthetic_layer != "none")

    @classmethod
    def load(cls, path):
        with Path(path).open("rb") as stream:
            data = tomllib.load(stream)
        try:
            model, runtime, input_, test = (data[k] for k in ("model", "runtime", "input", "test"))
            config = cls(model["name"], model["tflite"], runtime["wat_template"],
                         runtime["contract"], runtime.get("num_slots", 3),
                         input_["format"], input_["synthetic_layer"], test, data.get("classes", []))
            test["adapter"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Manifesto incompleto: {path}: {exc}") from exc
        if config.contract != "layerparam-v1":
            raise ValueError(f"Contrato não suportado: {config.contract}")
        if config.num_slots != 3:
            raise ValueError("layerparam-v1 requer 3 slots no gerador atual.")
        if (config.input_format, config.synthetic_layer) not in {
            ("rgb565", "rgb565_to_rgb888"), ("bgr888", "none"), ("rgb888", "none")
        }:
            raise ValueError("Combinação de formato e camada sintética não suportada.")
        return config
