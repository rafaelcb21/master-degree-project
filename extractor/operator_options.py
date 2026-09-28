from tflite import (
    ActivationFunctionType,
    AddOptions,
    Padding,
    Conv2DOptions,
    DepthwiseConv2DOptions,
    FullyConnectedOptions,
)


ACT_NONE = 0
ACT_RELU = 1
ACT_RELU6 = 3


def parse_fused_activation(
    activation_value,
):
    try:
        if (
            activation_value
            == ActivationFunctionType.NONE
        ):
            return ACT_NONE

        if (
            activation_value
            == ActivationFunctionType.RELU
        ):
            return ACT_RELU

        if (
            activation_value
            == ActivationFunctionType.RELU6
        ):
            return ACT_RELU6

    except Exception:
        pass

    if activation_value == 0:
        return ACT_NONE

    if activation_value == 1:
        return ACT_RELU

    if activation_value == 3:
        return ACT_RELU6

    return ACT_NONE


def parse_add_options(op):
    try:
        builtin_options = (
            op.BuiltinOptions()
        )

        if (
            hasattr(
                builtin_options,
                "Bytes",
            )
            and hasattr(
                builtin_options,
                "Pos",
            )
        ):
            options = (
                AddOptions.AddOptions()
                if hasattr(
                    AddOptions,
                    "AddOptions",
                )
                else AddOptions()
            )

            options.Init(
                builtin_options.Bytes,
                builtin_options.Pos,
            )

            return (
                parse_fused_activation(
                    int(
                        options
                        .FusedActivationFunction()
                    )
                )
            )

    except Exception:
        pass

    return ACT_NONE


def padding_is_same(
    padding_value,
):
    try:
        return (
            padding_value
            == Padding.SAME
        )
    except Exception:
        return padding_value == 0


def parse_conv2d_options(op):
    try:
        builtin_options = (
            op.BuiltinOptions()
        )

        if (
            hasattr(
                builtin_options,
                "Bytes",
            )
            and hasattr(
                builtin_options,
                "Pos",
            )
        ):
            options = (
                Conv2DOptions.Conv2DOptions()
                if hasattr(
                    Conv2DOptions,
                    "Conv2DOptions",
                )
                else Conv2DOptions()
            )

            options.Init(
                builtin_options.Bytes,
                builtin_options.Pos,
            )

            stride_h = int(
                options.StrideH()
            )

            stride_w = int(
                options.StrideW()
            )

            try:
                dil_h = int(
                    options
                    .DilationHFactor()
                )

                dil_w = int(
                    options
                    .DilationWFactor()
                )

            except Exception:
                dil_h = 1
                dil_w = 1

            padding_same = (
                padding_is_same(
                    int(
                        options.Padding()
                    )
                )
            )

            padding_kind = (
                0 if padding_same
                else 1
            )

            activation = (
                parse_fused_activation(
                    int(
                        options
                        .FusedActivationFunction()
                    )
                )
            )

            return (
                stride_h,
                stride_w,
                dil_h,
                dil_w,
                padding_kind,
                activation,
            )

    except Exception:
        pass

    return (
        1,
        1,
        1,
        1,
        1,
        ACT_NONE,
    )


def parse_dwconv2d_options(op):
    try:
        builtin_options = (
            op.BuiltinOptions()
        )

        if (
            hasattr(
                builtin_options,
                "Bytes",
            )
            and hasattr(
                builtin_options,
                "Pos",
            )
        ):
            options = (
                DepthwiseConv2DOptions
                .DepthwiseConv2DOptions()
                if hasattr(
                    DepthwiseConv2DOptions,
                    "DepthwiseConv2DOptions",
                )
                else DepthwiseConv2DOptions()
            )

            options.Init(
                builtin_options.Bytes,
                builtin_options.Pos,
            )

            stride_h = int(
                options.StrideH()
            )

            stride_w = int(
                options.StrideW()
            )

            try:
                dil_h = int(
                    options
                    .DilationHFactor()
                )

                dil_w = int(
                    options
                    .DilationWFactor()
                )

            except Exception:
                dil_h = 1
                dil_w = 1

            depth_mult = int(
                options.DepthMultiplier()
            )

            padding_same = (
                padding_is_same(
                    int(
                        options.Padding()
                    )
                )
            )

            padding_kind = (
                0 if padding_same
                else 1
            )

            activation = (
                parse_fused_activation(
                    int(
                        options
                        .FusedActivationFunction()
                    )
                )
            )

            return (
                stride_h,
                stride_w,
                dil_h,
                dil_w,
                padding_kind,
                activation,
                depth_mult,
            )

    except Exception:
        pass

    return (
        1,
        1,
        1,
        1,
        1,
        ACT_NONE,
        1,
    )


def parse_fc_options(op):
    try:
        builtin_options = (
            op.BuiltinOptions()
        )

        if (
            hasattr(
                builtin_options,
                "Bytes",
            )
            and hasattr(
                builtin_options,
                "Pos",
            )
        ):
            options = (
                FullyConnectedOptions
                .FullyConnectedOptions()
                if hasattr(
                    FullyConnectedOptions,
                    "FullyConnectedOptions",
                )
                else FullyConnectedOptions()
            )

            options.Init(
                builtin_options.Bytes,
                builtin_options.Pos,
            )

            return (
                parse_fused_activation(
                    int(
                        options
                        .FusedActivationFunction()
                    )
                )
            )

    except Exception:
        pass

    return ACT_NONE


def same_padding(
    in_h,
    in_w,
    kernel_h,
    kernel_w,
    stride_h,
    stride_w,
    dil_h=1,
    dil_w=1,
):
    out_h = (
        in_h + stride_h - 1
    ) // stride_h

    out_w = (
        in_w + stride_w - 1
    ) // stride_w

    effective_kernel_h = (
        (kernel_h - 1)
        * dil_h
        + 1
    )

    effective_kernel_w = (
        (kernel_w - 1)
        * dil_w
        + 1
    )

    pad_h_total = max(
        0,
        (
            (out_h - 1)
            * stride_h
            + effective_kernel_h
            - in_h
        ),
    )

    pad_w_total = max(
        0,
        (
            (out_w - 1)
            * stride_w
            + effective_kernel_w
            - in_w
        ),
    )

    pad_top = (
        pad_h_total // 2
    )

    pad_bottom = (
        pad_h_total - pad_top
    )

    pad_left = (
        pad_w_total // 2
    )

    pad_right = (
        pad_w_total - pad_left
    )

    return (
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        out_h,
        out_w,
    )