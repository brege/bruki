from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from pathlib import Path

import hdbscan
import joblib
import numpy as np
import torch
import umap
from PIL import Image
from tqdm import tqdm


@dataclass(frozen=True)
class EmbedConfig:
    min_size: int = 10
    checkpoint_every: int = 100


@dataclass(frozen=True)
class ClusterConfig:
    umap_n_components: int = 2
    umap_n_neighbors: int = 15
    umap_min_dist: float = 0.1
    umap_metric: str = "cosine"
    hdbscan_min_cluster_size: int = 10
    hdbscan_min_samples: int = 5
    hdbscan_metric: str = "euclidean"
    seed: int = 42


_HF_LOADERS = {
    "clip": ("CLIPProcessor", "CLIPModel"),
    "siglip": ("SiglipProcessor", "SiglipModel"),
    "dinov2": ("AutoProcessor", "AutoModel"),
}


def load_model(spec: dict):
    name, backend = spec["name"], spec["backend"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if backend == "open_clip_hf":
        open_clip = importlib.import_module("open_clip")
        model, preprocess = open_clip.create_model_from_pretrained(f"hf-hub:{name}")
        model.eval().to(device)
        return model, preprocess, device

    family = spec["family"]
    t = importlib.import_module("transformers")
    proc_cls, model_cls = _HF_LOADERS[family]
    processor = getattr(t, proc_cls).from_pretrained(name)
    model = getattr(t, model_cls).from_pretrained(name)
    model.eval().to(device)
    return model, processor, device


def prepare_image(path: Path, config: EmbedConfig):
    try:
        with Image.open(path) as img:
            if img.size[0] < config.min_size or img.size[1] < config.min_size:
                return None
            return img.convert("RGB")
    except OSError:
        return None


def _send(inputs: dict, device) -> dict:
    return {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}


def _cls_token(outputs) -> torch.Tensor:
    p = getattr(outputs, "pooler_output", None)
    if p is not None:
        return p
    h = getattr(outputs, "last_hidden_state", None)
    if h is not None:
        return h[:, 0]
    raise RuntimeError("no usable output tensor")


def encode_features(spec: dict, model, processor, image, device) -> torch.Tensor:
    backend, family = spec["backend"], spec["family"]

    if backend == "open_clip_hf":
        features = model.encode_image(processor(image).unsqueeze(0).to(device))
    elif family == "clip":
        inputs = _send(processor(images=image, return_tensors="pt"), device)
        outputs = model.vision_model(pixel_values=inputs["pixel_values"], return_dict=True)
        features = model.visual_projection(outputs.pooler_output)
    elif family == "siglip":
        inputs = _send(processor(images=image, return_tensors="pt"), device)
        features = _cls_token(model.get_image_features(**inputs))
    elif family == "dinov2":
        inputs = _send(processor(images=image, return_tensors="pt"), device)
        features = _cls_token(model(**inputs))
    else:
        raise RuntimeError(f"unsupported family: {family}")

    return features / features.norm(dim=-1, keepdim=True)


def load_or_embed(spec: dict, paths: list[Path], cache_dir: Path, config: EmbedConfig):
    model_name = spec["name"]
    cache_file = cache_dir / f"{model_name.replace('/', '__')}.pkl"
    path_strings = [str(p) for p in paths]

    if cache_file.exists():
        cached = joblib.load(cache_file)
        cached_paths = list(cached["paths"])
        cached_embeddings = np.asarray(cached["embeddings"], dtype=np.float32)
        cached_valid_mask = np.asarray(cached["valid_mask"], dtype=bool)
    else:
        cached_paths = []
        cached_embeddings = np.zeros((0, 0), dtype=np.float32)
        cached_valid_mask = np.zeros((0,), dtype=bool)

    old_idx = {p: i for i, p in enumerate(cached_paths)}
    old_dim = cached_embeddings.shape[1] if cached_embeddings.ndim == 2 else 0
    n = len(path_strings)

    embeddings = np.zeros((n, old_dim), dtype=np.float32) if old_dim > 0 else None
    valid_mask = np.zeros(n, dtype=bool)
    pending = []

    for i, p in enumerate(path_strings):
        j = old_idx.get(p)
        if j is None or not cached_valid_mask[j]:
            pending.append(i)
            continue
        if embeddings is None:
            embeddings = np.zeros((n, cached_embeddings.shape[1]), dtype=np.float32)
        embeddings[i] = cached_embeddings[j]
        valid_mask[i] = True

    if not pending and embeddings is not None:
        return {
            "paths": path_strings,
            "embeddings": embeddings,
            "valid_mask": valid_mask,
            "elapsed_s": 0.0,
        }, "hit"

    model, processor, device = load_model(spec)
    started = time.perf_counter()

    with torch.inference_mode():
        for step, i in enumerate(tqdm(pending, desc=f"embed:{model_name}"), start=1):
            image = prepare_image(Path(path_strings[i]), config)
            if image is None:
                valid_mask[i] = False
            else:
                vec = (
                    encode_features(spec, model, processor, image, device)
                    .cpu()
                    .numpy()[0]
                    .astype(np.float32)
                )
                if embeddings is None:
                    embeddings = np.zeros((n, vec.shape[0]), dtype=np.float32)
                embeddings[i] = vec
                valid_mask[i] = True

            if step % config.checkpoint_every == 0:
                joblib.dump(
                    {
                        "paths": path_strings,
                        "embeddings": embeddings
                        if embeddings is not None
                        else np.zeros((n, 0), dtype=np.float32),
                        "valid_mask": valid_mask,
                    },
                    cache_file,
                )

    elapsed = time.perf_counter() - started
    if embeddings is None:
        embeddings = np.zeros((n, 0), dtype=np.float32)

    result = {"paths": path_strings, "embeddings": embeddings, "valid_mask": valid_mask}
    joblib.dump(result, cache_file)
    state = "miss" if len(pending) == n else "partial"
    return {**result, "elapsed_s": elapsed}, state


def cluster_embeddings(
    embeddings: np.ndarray, config: ClusterConfig
) -> tuple[np.ndarray, np.ndarray]:
    reducer = umap.UMAP(
        n_components=config.umap_n_components,
        n_neighbors=config.umap_n_neighbors,
        min_dist=config.umap_min_dist,
        metric=config.umap_metric,
        random_state=config.seed,
    )
    embedding_2d = reducer.fit_transform(embeddings)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=config.hdbscan_min_cluster_size,
        min_samples=config.hdbscan_min_samples,
        metric=config.hdbscan_metric,
    )
    labels = clusterer.fit_predict(embedding_2d)
    return embedding_2d, labels
