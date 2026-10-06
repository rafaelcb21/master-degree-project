"""Run original TFLite files independently of the WASM generation pipeline."""
import argparse

from pipeline.model_package import ModelPackage


def main():
    parser = argparse.ArgumentParser(description="Executa TFLite e grava relatórios separados por modelo e execução.")
    parser.add_argument("--model", default="all", help="Nome em models/ ou all (padrão)")
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads deve ser positivo")
    try:
        from inference.tflite_inference import run_tflite
        packages = ModelPackage.available() if args.model == "all" else [ModelPackage.load(args.model)]
        failures = 0
        for package in packages:
            _, metadata = run_tflite(package, threads=args.threads)
            failures += metadata["summary"]["errors"]
        return 1 if failures else 0
    except ImportError as error:
        parser.exit(1, f"Dependência ausente: {error}. Instale requirements-tflite.txt no ambiente ativo.\n")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Erro: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
