"""Structural tests with small FlatBuffers whose parameter totals are known."""
import json
from pathlib import Path
import sys
import unittest

import flatbuffers
import tflite

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_tflite_parameters import analyze


def fixture(shared=False, bias=True, fp16=False):
    builder = flatbuffers.Builder(2048)

    def vector(values, offsets=False):
        builder.StartVector(4, len(values), 4)
        for value in reversed(values):
            if offsets:
                builder.PrependUOffsetTRelative(value)
            else:
                builder.PrependInt32(value)
        return builder.EndVector()

    buffers = []
    for size in (0, 12 if fp16 else 24, 8, 4):
        data = builder.CreateByteVector(bytes(size)) if size else None
        tflite.BufferStart(builder)
        if data:
            tflite.BufferAddData(builder, data)
        buffers.append(tflite.BufferEnd(builder))
    tensors = []
    specs = [([1, 3], 0, tflite.TensorType.FLOAT32), ([2, 3], 1, tflite.TensorType.FLOAT16 if fp16 else tflite.TensorType.FLOAT32),
             ([2], 2, tflite.TensorType.FLOAT32), ([1, 2], 0, tflite.TensorType.FLOAT32),
             ([1], 3, tflite.TensorType.INT32), ([1, 2], 0, tflite.TensorType.FLOAT32)]
    if fp16:
        specs.append(([2, 3], 0, tflite.TensorType.FLOAT32))
    for i, (shape, buffer, dtype) in enumerate(specs):
        name = builder.CreateString(f"tensor_{i}")
        dims = vector(shape)
        tflite.TensorStart(builder)
        tflite.TensorAddName(builder, name)
        tflite.TensorAddShape(builder, dims)
        tflite.TensorAddBuffer(builder, buffer)
        tflite.TensorAddType(builder, dtype)
        tensors.append(tflite.TensorEnd(builder))
    codes = []
    for builtin in (tflite.BuiltinOperator.FULLY_CONNECTED, tflite.BuiltinOperator.RESHAPE, tflite.BuiltinOperator.DEQUANTIZE):
        tflite.OperatorCodeStart(builder)
        tflite.OperatorCodeAddBuiltinCode(builder, builtin)
        tflite.OperatorCodeAddDeprecatedBuiltinCode(builder, builtin)
        codes.append(tflite.OperatorCodeEnd(builder))
    ops = []

    def operation(code, inputs, outputs):
        inputs, outputs = vector(inputs), vector(outputs)
        tflite.OperatorStart(builder)
        tflite.OperatorAddOpcodeIndex(builder, code)
        tflite.OperatorAddInputs(builder, inputs)
        tflite.OperatorAddOutputs(builder, outputs)
        ops.append(tflite.OperatorEnd(builder))

    if fp16:
        operation(2, [1], [6])
    operation(0, [0, 6 if fp16 else 1, 2 if bias else -1], [3])
    if shared:
        operation(0, [0, 1, 2 if bias else -1], [5])
    else:
        operation(1, [3, 4], [5])
    tensors, ops = vector(tensors, True), vector(ops, True)
    inputs, outputs = vector([0]), vector([5])
    tflite.SubGraphStart(builder)
    tflite.SubGraphAddTensors(builder, tensors)
    tflite.SubGraphAddOperators(builder, ops)
    tflite.SubGraphAddInputs(builder, inputs)
    tflite.SubGraphAddOutputs(builder, outputs)
    graph = tflite.SubGraphEnd(builder)
    graphs, buffers, codes = vector([graph], True), vector(buffers, True), vector(codes, True)
    tflite.ModelStart(builder)
    tflite.ModelAddVersion(builder, 3)
    tflite.ModelAddSubgraphs(builder, graphs)
    tflite.ModelAddBuffers(builder, buffers)
    tflite.ModelAddOperatorCodes(builder, codes)
    model = tflite.ModelEnd(builder)
    builder.Finish(model, file_identifier=b"TFL3")
    return bytes(builder.Output())


class ParameterTests(unittest.TestCase):
    def test_dense_and_auxiliary_shape(self):
        report = analyze(fixture())
        self.assertEqual(report["totals"]["total"], 8)
        self.assertEqual(report["totals"]["weights"], 6)
        self.assertEqual(report["totals"]["bias"], 2)
        self.assertEqual(report["totals"]["auxiliaryElements"], 1)
        self.assertEqual(report["layers"][1]["total"], 0)
        self.assertIn("2 × 3 = 6", report["layers"][0]["parameters"][0]["calculation"])
        self.assertFalse(report["warnings"])
        json.dumps(report, allow_nan=False)

    def test_optional_bias(self):
        self.assertEqual(analyze(fixture(bias=False))["totals"]["total"], 6)

    def test_shared_parameters_not_duplicated(self):
        report = analyze(fixture(shared=True))
        self.assertEqual(report["totals"]["total"], 8)
        self.assertEqual(report["totals"]["layerSum"], 16)
        self.assertTrue(all(t["shared"] for t in report["layers"][1]["parameters"]))

    def test_fp16_dequantized_weights(self):
        report = analyze(fixture(fp16=True))
        self.assertEqual(report["totals"]["total"], 8)
        self.assertEqual(report["totals"]["parameterBytes"], 20)
        self.assertEqual(report["layers"][0]["total"], 0)
        self.assertEqual(report["layers"][1]["parameters"][0]["dtype"], "FLOAT16")

    def test_invalid_file(self):
        for content in (b"", b"not a tflite", b"\xff\xff\xff\xffTFL3"):
            with self.assertRaises(ValueError):
                analyze(content)


if __name__ == "__main__":
    unittest.main()
