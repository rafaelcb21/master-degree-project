from pathlib import Path
import tflite.Model as TFLModel


def load_model(model_path):
    buf = Path(model_path).read_bytes()

    if hasattr(TFLModel, "GetRootAsModel"):
        model = TFLModel.GetRootAsModel(buf, 0)

    elif (
        hasattr(TFLModel, "Model")
        and hasattr(TFLModel.Model, "GetRootAsModel")
    ):
        model = TFLModel.Model.GetRootAsModel(buf, 0)

    else:
        raise RuntimeError(
            "Binding tflite.Model não possui GetRootAsModel."
        )

    return model


def get_subgraph(model, index=0):
    return model.Subgraphs(index)