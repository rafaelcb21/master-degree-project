import tempfile
import re
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from adapters.base import TestCase, decode_output
from adapters.imagenet_topk import ImageNetTopKAdapter
from adapters.binary_folders import BinaryFoldersAdapter
from pipeline.model_package import ModelPackage
from pipeline.model_config import ModelConfig
from extractor.layer_params import build_layer_params


class ModelPackagesTests(unittest.TestCase):
    def test_wasm_quantize_uses_output_type_at_any_layer_index(self):
        from inference.wasm_inference import _instantiate_wasm
        from wasmtime import wat2wasm
        template = ModelPackage.load().resolve(ModelPackage.load().config.wat_template).read_text(encoding="utf-8")
        replacements = {"MEM_PAGES": 1, "PARAMS_BASE": 1024, "LP_SIZE": 116,
                        "NUM_LAYERS": 1, "DATA_SEGMENTS": ""}
        wat = re.sub(r"@@([A-Z0-9_]+)@@", lambda m: str(replacements.get(m[1], 0)), template)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.wasm"
            path.write_bytes(wat2wasm(wat))
            runtime = _instantiate_wasm(path)
            store, memory = runtime["store"], runtime["memory"]
            quantize = runtime["instance"].exports(store)["quantize"]
            params = [0] * 29
            for field, value in {0: 7, 2: 3, 3: 4096, 4: 8192, 8: 3,
                                 9: 1073741824, 10: 1, 24: -128, 27: 1, 28: 1}.items():
                params[field] = value
            memory.write(store, struct.pack("<29i", *params), 1024)
            memory.write(store, bytes([128, 0, 127]), 4096)
            quantize(store, 0)
            self.assertEqual(bytes(memory.read(store, 8192, 8195)), bytes([0, 128, 255]))
            params[2], params[24], params[26] = 0, 0, -128
            memory.write(store, struct.pack("<29i", *params), 1024)
            memory.write(store, bytes([0, 128, 255]), 4096)
            quantize(store, 0)
            self.assertEqual(bytes(memory.read(store, 8192, 8195)), bytes([128, 0, 127]))

    def test_paths_are_relative_to_package(self):
        for package in ModelPackage.available():
            package.validate_sources()
            self.assertEqual(package.wat_path.parent, package.root / "generated")
            self.assertNotEqual(package.resolve(package.config.wat_template), package.wat_path)

    def test_unknown_contract_rejected(self):
        manifest = (ModelPackage.load().root / "model.toml").read_text()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.toml"
            path.write_text(manifest.replace("layerparam-v1", "layerparam-v2"))
            with self.assertRaisesRegex(ValueError, "Contrato"):
                ModelConfig.load(path)

    def test_synthetic_layer_optional(self):
        graph = SimpleNamespace(OperatorsLength=lambda: 0)
        kwargs = dict(old_idx_to_label={}, runtime_tensor_to_slot={}, slot_bases=[0, 100, 200],
                      weight_tensor_off={}, bias_tensor_off={}, mul_q6_off={})
        with patch("extractor.layer_params.build_rgb565_layer", return_value={"optype": "RGB565_TO_RGB888"}) as rgb:
            self.assertEqual(build_layer_params(None, graph, synthetic_layer="none", **kwargs), [])
            rgb.assert_not_called()
            self.assertEqual(len(build_layer_params(None, graph, **kwargs)), 1)

    def test_bgr_conversion_and_invalid_size(self):
        adapter = ImageNetTopKAdapter(ModelPackage.load("mobilenetv2_alpha035"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pixel.raw"
            path.write_bytes(bytes([10, 20, 30]))
            info = dict(elements=3, dtype="uint8")
            self.assertEqual(adapter.prepare_input(TestCase(path), info), bytes([30, 20, 10]))
            with self.assertRaisesRegex(ValueError, "Tamanho RAW"):
                adapter.prepare_input(TestCase(path), dict(elements=6, dtype="uint8"))

    def test_signed_output_and_stable_topk(self):
        info = dict(dtype="int8", scale=1 / 256, zero_point=-128)
        values, scores = decode_output(bytes([128, 255, 127]), info)
        self.assertEqual(values.tolist(), [-128, -1, 127])
        self.assertEqual(scores.tolist(), [0, 127 / 256, 255 / 256])
        adapter = ImageNetTopKAdapter(ModelPackage.load("mobilenetv2_alpha035"))
        adapter.labels = {str(i): [f"n{i:08d}", str(i)] for i in range(3)}
        result = adapter.evaluate_output(TestCase(Path("x.raw")), bytes([127, 127, 128]), info)
        self.assertEqual([item["index"] for item in result["top"]], [0, 1, 2])

    def test_binary_class_order_and_ties(self):
        adapter = BinaryFoldersAdapter(ModelPackage.load())
        info = dict(dtype="uint8", scale=1 / 256, zero_point=0)
        case = TestCase(Path("x.raw"), 1)
        self.assertTrue(adapter.evaluate_output(case, bytes([200, 55]), info)["right"])
        self.assertTrue(adapter.evaluate_output(case, bytes([100, 100]), info)["invalid"])
        self.assertTrue(adapter.evaluate_output(case, bytes([0, 0]), info)["invalid"])


if __name__ == "__main__":
    unittest.main()
