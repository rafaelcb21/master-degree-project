"""CLI para executar um pacote de modelo."""
import argparse
from pipeline.model_package import ModelPackage


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extração TFLite, geração WASM e testes por pacote.")
    parser.add_argument("--model", default="drowsiness", help="Nome da pasta em models/ (padrão: drowsiness)")
    parser.add_argument("--list-models", action="store_true", help="Lista os pacotes disponíveis")
    args = parser.parse_args(argv)
    try:
        if args.list_models:
            for package in ModelPackage.available():
                print(f"{package.root.name}\n  {package.config.name}")
            return 0
        from pipeline.model_pipeline import ModelPipeline
        ModelPipeline(ModelPackage.load(args.model)).run()
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Erro: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
