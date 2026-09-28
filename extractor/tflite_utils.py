import tflite
import numpy as np


TENSOR_TYPE_MAP = {
    0: ("float32", np.float32),
    1: ("float16", np.float16),
    2: ("int32", np.int32),
    3: ("uint8", np.uint8),
    4: ("int64", np.int64),
    6: ("bool", np.bool_),
    7: ("int16", np.int16),
    9: ("int8", np.int8),
}

BYTES_PER_TYPE = {
    0: 4,  # float32
    1: 2,  # float16
    2: 4,  # int32
    3: 1,  # uint8
    4: 8,  # int64
    6: 1,  # bool
    7: 2,  # int16
    9: 1,  # int8
}


def op_name(model, op):
    code = model.OperatorCodes(
        op.OpcodeIndex()
    ).BuiltinCode()

    for name, value in tflite.BuiltinOperator.__dict__.items():
        if isinstance(value, int) and value == code:
            return name

    return "CUSTOM"


def is_constant_tensor(
    model,
    subgraph,
    tensor_id,
):
    tensor = subgraph.Tensors(
        tensor_id
    )

    buffer = model.Buffers(
        tensor.Buffer()
    )

    try:
        data = buffer.DataAsNumpy()
    except AttributeError:
        return False

    return (
        hasattr(data, "__len__")
        and len(data) > 0
    )


def safe_bytes_from_tensor(
    model,
    subgraph,
    tensor_id,
):
    tensor = subgraph.Tensors(
        int(tensor_id)
    )

    buffer = model.Buffers(
        tensor.Buffer()
    )

    try:
        data_bytes = buffer.DataAsNumpy()
    except AttributeError:
        return None, None, None

    if (
        not hasattr(data_bytes, "__len__")
        or len(data_bytes) == 0
    ):
        return None, None, None

    shape = tensor.ShapeAsNumpy()
    dtype = int(tensor.Type())

    _, numpy_dtype = TENSOR_TYPE_MAP.get(
        dtype,
        (None, None),
    )

    if numpy_dtype is None:
        return None, None, None

    array = np.frombuffer(
        data_bytes.tobytes(),
        dtype=numpy_dtype,
    )

    try:
        array = array.reshape(shape)
    except Exception:
        pass

    raw = array.flatten().tobytes()

    return tensor, array, raw


def scale_scalar(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return 1.0

    scales = quantization.ScaleAsNumpy()

    if scales is None or len(scales) == 0:
        return 1.0

    return float(
        np.array(
            scales,
            dtype=np.float64,
        ).flatten()[0]
    )


def zp_scalar(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return 0

    zero_points = (
        quantization.ZeroPointAsNumpy()
    )

    if (
        zero_points is None
        or len(zero_points) == 0
    ):
        return 0

    return int(
        np.array(
            zero_points,
            dtype=np.int64,
        ).flatten()[0]
    )


def tensor_shape_list(tensor):
    shape = tensor.ShapeAsNumpy()

    if shape is None:
        return []

    return [
        int(value)
        for value in shape.tolist()
    ]


def qparams_np(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return None

    scales = (
        quantization.ScaleAsNumpy()
    )

    zero_points = (
        quantization.ZeroPointAsNumpy()
    )

    if scales is None:
        return None

    scales = np.atleast_1d(
        np.array(
            scales,
            dtype=np.float64,
        )
    )

    zero_points = np.atleast_1d(
        np.array(
            (
                zero_points
                if zero_points is not None
                else []
            ),
            dtype=np.int64,
        )
    )

    if scales.size == 0:
        return None

    return {
        "scales": scales,
        "zps": zero_points,
        "qdim": (
            quantization
            .QuantizedDimension()
        ),
    }