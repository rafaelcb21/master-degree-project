"""Verify the transferred package using only its preserved sources."""
import json
from pathlib import Path
from analyze import digest, summarize


def main():
    root = Path(__file__).resolve().parent
    report = json.loads((root / "evidencias-report.json").read_text(encoding="utf-8"))
    for run, record in report["runs"].items():
        folder = root / "fontes" / run
        for filename, key in [("report.csv", "csv_identity"), ("metadata.json", "metadata_identity")]:
            if digest(folder / filename) != record[key]:
                raise ValueError(f"Hash/size mismatch: {run}/{filename}")
        stats, _ = summarize(folder / "report.csv")
        if stats != record["stats"]:
            raise ValueError(f"Statistics mismatch: {run}")
        if json.loads((folder / "metadata.json").read_text(encoding="utf-8")) != record["metadata"]:
            raise ValueError(f"Metadata mismatch: {run}")
    if digest(root / "fontes/acuracia-representativa.csv") != report["representative_accuracy"]["identity"]:
        raise ValueError("Representative report hash/size mismatch")
    print("OK: source CSV/metadata hashes, sizes and per-run statistics verified.")


if __name__ == "__main__":
    main()
