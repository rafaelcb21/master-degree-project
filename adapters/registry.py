from adapters.binary_folders import BinaryFoldersAdapter
from adapters.imagenet_topk import ImageNetTopKAdapter

ADAPTERS = {"binary-folders": BinaryFoldersAdapter, "imagenet-topk": ImageNetTopKAdapter}


def create_adapter(package):
    name = package.config.test["adapter"]
    if name not in ADAPTERS:
        raise ValueError(f"Adapter desconhecido: {name}; disponíveis: {', '.join(ADAPTERS)}")
    return ADAPTERS[name](package)
