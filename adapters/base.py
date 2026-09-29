from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCase:
    path: Path
    label: int | None = None


class TestAdapter(ABC):
    def __init__(self, package):
        self.package = package
        self.config = package.config

    def raw_files(self, path):
        directory = self.package.resolve(path)
        if not directory.is_dir():
            raise ValueError(f"Pasta de testes ausente: {directory}")
        files = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".raw")
        if not files:
            raise ValueError(f"Nenhum RAW em {directory}")
        return files

    @abstractmethod
    def discover_cases(self): ...

    @abstractmethod
    def prepare_input(self, case, input_info): ...

    @abstractmethod
    def evaluate_output(self, case, output, output_info): ...

    @abstractmethod
    def build_report(self, results): ...


def decode_output(output, info):
    import numpy as np
    values = np.frombuffer(output, dtype=info["dtype"])
    return values, (values.astype(float) - info["zero_point"]) * info["scale"]
