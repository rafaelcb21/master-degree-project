from adapters.base import TestAdapter, TestCase, decode_output


class BinaryFoldersAdapter(TestAdapter):
    def discover_cases(self):
        if len(self.config.classes) != 2:
            raise ValueError("binary-folders requer duas classes na ordem da saída.")
        datasets = self.config.test.get("datasets", [])
        if not datasets:
            raise ValueError("binary-folders requer test.datasets.")
        labels = {item["label"] for item in self.config.classes}
        for dataset in datasets:
            if dataset["label"] not in labels:
                raise ValueError("Label do dataset ausente em classes.")
            for path in self.raw_files(dataset["path"]):
                yield TestCase(path, dataset["label"])

    def prepare_input(self, case, input_info):
        if self.config.input_format != "rgb565":
            raise ValueError("binary-folders espera RGB565.")
        return case.path.read_bytes()

    def evaluate_output(self, case, output, output_info):
        import numpy as np
        values, scores = decode_output(output, output_info)
        if len(values) != len(self.config.classes):
            raise ValueError("Número de classes incompatível com a saída.")
        winners = np.flatnonzero(values == values.max())
        invalid = len(winners) != 1 or float(scores.sum()) <= 0
        predicted = None if invalid else self.config.classes[int(winners[0])]["label"]
        return {"file": str(case.path), "label": case.label, "result": predicted,
                "invalid": invalid, "right": not invalid and predicted == case.label,
                "quantized": values.tolist(), "scores": scores.tolist()}

    def build_report(self, results):
        records = results["records"]
        correct = sum(r["right"] for r in records)
        invalid = sum(r["invalid"] for r in records)
        accuracy = 100 * correct / len(records) if records else 0
        lines = ["INFERÊNCIA WASM — binary-folders", f"Classes (ordem da saída): {self.config.classes}"]
        for r in records:
            lines.append(f"{r['file']} | quantized={r['quantized']} | scores={r['scores']} | "
                         f"result={r['result']} label={r['label']} right={int(r['right'])} invalid={r['invalid']}")
        lines.extend([f"Inferências executadas: {len(records)}", f"Inválidos/empates: {invalid}",
                      f"Acertos: {correct}", f"Acurácia: {accuracy:.2f}%"])
        return "\n".join(lines)
