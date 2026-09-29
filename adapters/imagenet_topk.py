import json
import numpy as np
from adapters.base import TestAdapter, TestCase, decode_output


class ImageNetTopKAdapter(TestAdapter):
    def discover_cases(self):
        self.labels = json.loads(self.package.resolve(self.config.test["labels"]).read_text(encoding="utf-8"))
        if not isinstance(self.labels, dict) or not self.labels:
            raise ValueError("Labels ImageNet devem ser um objeto JSON não vazio.")
        for index, entry in self.labels.items():
            if not isinstance(entry, list) or len(entry) != 2 or not all(isinstance(value, str) and value for value in entry):
                raise ValueError(f"Label ImageNet inválido no índice {index}: esperado [wnid, class_name].")
        top_k = self.config.test.get("top_k", 15)
        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k deve ser um inteiro positivo.")
        return [TestCase(p) for p in self.raw_files(self.config.test["path"])]

    def prepare_input(self, case, input_info):
        pixels = np.frombuffer(case.path.read_bytes(), dtype=np.uint8)
        if pixels.size != input_info["elements"]:
            raise ValueError(f"Tamanho RAW inválido: {pixels.size}; esperado={input_info['elements']}")
        if self.config.input_format == "bgr888":
            pixels = pixels.reshape(-1, 3)[:, ::-1].copy().reshape(-1)
        elif self.config.input_format != "rgb888":
            raise ValueError("imagenet-topk espera BGR888 ou RGB888.")
        if input_info["dtype"] == "int8":
            # MobileNet: pixels [0,255] -> [-1,1] antes da quantização.
            real = pixels.astype(np.float64) / 127.5 - 1.0
            pixels = np.clip(np.rint(real / input_info["scale"] + input_info["zero_point"]), -128, 127).astype(np.int8)
        return pixels.tobytes()

    def evaluate_output(self, case, output, output_info):
        values, scores = decode_output(output, output_info)
        if any(str(i) not in self.labels for i in range(len(values))):
            raise ValueError("Labels incompletos para os índices de saída.")
        indices = np.argsort(-scores, kind="stable")[:self.config.test.get("top_k", 15)]
        return {"file": str(case.path), "top": [
            {"index": int(i), "wnid": self.labels[str(i)][0], "class_name": self.labels[str(i)][1],
             "quantized": int(values[i]), "score": float(scores[i])}
            for i in indices]}

    def build_report(self, results):
        lines = ["INFERÊNCIA WASM — ImageNet Top-K"]
        for record in results["records"]:
            lines.append(record["file"])
            for rank, item in enumerate(record["top"], 1):
                lines.extend([
                    f"{rank:2}. [{item['index']}] {item['class_name']}",
                    f"    wnid={item['wnid']}",
                    f"    q={item['quantized']}",
                    f"    score={item['score']:.8f}",
                ])
        return "\n".join(lines)
