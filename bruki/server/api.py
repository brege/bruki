import argparse
import json
import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from bruki.server import ml as ml_pipeline

APP_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(APP_DIR),
    static_folder=str(APP_DIR),
    static_url_path="",
)
BASE_DIR = Path(os.environ.get("TAGGER_BASE", ".")).resolve()
STATE_DIR = Path(os.environ.get("TAGGER_STATE_DIR", "data/server"))
CONFIG_PATH = Path(os.environ.get("TAGGER_CONFIG", "config.yaml")).expanduser().resolve()
STATE_DB = Path(os.environ.get("TAGGER_DB", str(STATE_DIR / "state.sqlite3")))
LABELS_PATH = Path(os.environ.get("TAGGER_LABELS", str(STATE_DIR / "labels.jsonl")))
SAMPLE_LABELS_PATH = Path("data/notebook/labels.jsonl")
SAMPLE_STATE_DB = Path("data/notebook/state.sqlite3")
SAMPLE_ITEMS_DIR = Path("data/notebook/samples")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
SAMPLE_MODE = False
_, _, _source_roots = ml_pipeline.resolve_screenshot_records(CONFIG_PATH)
SOURCE_ROOTS = [Path(root) for root in _source_roots]
DEFAULT_STATE_DB = STATE_DB
DEFAULT_LABELS_PATH = LABELS_PATH
DEFAULT_SOURCE_ROOTS = list(SOURCE_ROOTS)

_CACHE_LOCK = threading.Lock()
_LABELS_CACHE: dict[str, list[str]] = {}
_LABELS_MTIME_NS: int | None = None


class AccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return " - - [" not in message or "HTTP/" not in message


def resolve_sample_items_dir() -> Path:
    candidate = SAMPLE_ITEMS_DIR.expanduser()
    return candidate.resolve() if candidate.is_absolute() else (BASE_DIR / candidate).resolve()


def set_sample_mode(enabled: bool) -> None:
    global SAMPLE_MODE, STATE_DB, LABELS_PATH, SOURCE_ROOTS, _LABELS_CACHE, _LABELS_MTIME_NS
    SAMPLE_MODE = enabled
    if enabled:
        STATE_DB = SAMPLE_STATE_DB
        LABELS_PATH = SAMPLE_LABELS_PATH
        SOURCE_ROOTS = [resolve_sample_items_dir()]
    else:
        STATE_DB = DEFAULT_STATE_DB
        LABELS_PATH = DEFAULT_LABELS_PATH
        SOURCE_ROOTS = list(DEFAULT_SOURCE_ROOTS)
    with _CACHE_LOCK:
        _LABELS_CACHE = {}
        _LABELS_MTIME_NS = None


def resolve_state_db() -> Path:
    candidate = STATE_DB.expanduser()
    return candidate.resolve() if candidate.is_absolute() else (BASE_DIR / candidate).resolve()


def read_jsonl(path: Path, strict: bool = True) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                if strict:
                    raise ValueError(f"invalid JSONL in {path}:{line_no}") from None
    return rows


def labels_mtime_ns() -> int | None:
    path = BASE_DIR / LABELS_PATH
    if not path.exists():
        return None
    return path.stat().st_mtime_ns


def read_labels_file() -> dict[str, list[str]]:
    labels: dict[str, list[str]] = {}
    for row in read_jsonl(BASE_DIR / LABELS_PATH, strict=False):
        input_path = row.get("input_path")
        if input_path:
            labels[input_path] = row.get("categories", [])
    return labels


def load_labels_cached() -> dict[str, list[str]]:
    global _LABELS_CACHE, _LABELS_MTIME_NS
    mtime_ns = labels_mtime_ns()
    with _CACHE_LOCK:
        if _LABELS_MTIME_NS == mtime_ns:
            return _LABELS_CACHE
        _LABELS_CACHE = read_labels_file()
        _LABELS_MTIME_NS = mtime_ns
        return _LABELS_CACHE


def write_labels_file(labels_by_path: dict[str, list[str]]) -> None:
    global _LABELS_CACHE, _LABELS_MTIME_NS
    labels_path = BASE_DIR / LABELS_PATH
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = labels_path.with_suffix(labels_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for input_path, categories in sorted(labels_by_path.items()):
            handle.write(json.dumps({"input_path": input_path, "categories": categories}) + "\n")
    tmp_path.replace(labels_path)
    with _CACHE_LOCK:
        _LABELS_CACHE = {}
        _LABELS_MTIME_NS = None


def load_sample_items() -> list[dict]:
    root = resolve_sample_items_dir()
    if not root.exists():
        return []
    items: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        try:
            input_path = str(path.relative_to(BASE_DIR))
        except ValueError:
            input_path = str(path)
        items.append(
            {
                "input_path": input_path,
                "series": "sample",
                "source": path.parent.name,
                "cluster": 0,
            }
        )
    return items


def load_items() -> list[dict]:
    if SAMPLE_MODE:
        return load_sample_items()
    return ml_pipeline.get_items(db_path=resolve_state_db())


def load_all() -> list[dict]:
    labels = load_labels_cached()
    merged: list[dict] = []
    for item in load_items():
        row = dict(item)
        input_path = row.get("input_path")
        if input_path in labels:
            row["categories"] = labels[input_path]
        merged.append(row)
    return merged


@app.get("/")
def index():
    return render_template("index.html", sample_mode=SAMPLE_MODE)


@app.get("/api/items")
def get_items():
    selected_cluster = request.args.get("cluster", "")
    payload = []
    for item_idx, item in enumerate(load_all()):
        if selected_cluster:
            cluster_id = item.get("cluster")
            if str(cluster_id) != selected_cluster:
                continue
        row = dict(item)
        row["_idx"] = item_idx
        payload.append(row)
    return jsonify(payload)


@app.get("/api/tags")
def get_tags():
    tags = set()
    for item in load_all():
        tags.update(item.get("categories", []))
    return jsonify(sorted(tags))


@app.patch("/api/item/<int:idx>")
def patch_item(idx):
    body = request.get_json(silent=True) or {}
    categories = body.get("categories", [])
    if not isinstance(categories, list) or any(not isinstance(entry, str) for entry in categories):
        return jsonify({"error": "categories must be a list of strings"}), 400
    items = load_items()
    if idx < 0 or idx >= len(items):
        return jsonify({"error": "out of range"}), 404
    input_path = items[idx].get("input_path")
    if not input_path:
        return jsonify({"error": "missing input_path"}), 500
    labels_by_path = dict(load_labels_cached())
    labels_by_path[input_path] = categories
    write_labels_file(labels_by_path)
    response = dict(items[idx])
    response["categories"] = categories
    response["_idx"] = idx
    return jsonify(response)


@app.post("/api/purge")
def purge_labels():
    items = load_all()
    valid_paths = {item["input_path"] for item in items if "input_path" in item}
    labels_by_path = dict(load_labels_cached())
    before_count = len(labels_by_path)
    labels_by_path = {
        input_path: categories
        for input_path, categories in labels_by_path.items()
        if input_path in valid_paths
    }
    write_labels_file(labels_by_path)
    after_count = len(labels_by_path)
    return jsonify({"removed": before_count - after_count, "remaining": after_count})


@app.get("/api/purge-preview")
def purge_preview():
    items = load_all()
    valid_paths = {item["input_path"] for item in items if "input_path" in item}
    labels_by_path = load_labels_cached()
    removed = sorted([input_path for input_path in labels_by_path if input_path not in valid_paths])
    return jsonify({"remove": removed, "count": len(removed)})


@app.post("/api/ml/start")
def start_ml():
    if SAMPLE_MODE:
        return jsonify({"started": False, "disabled": True})
    started = ml_pipeline.start_job(config_path=CONFIG_PATH, db_path=resolve_state_db())
    return jsonify({"started": started})


@app.get("/api/ml/status")
def ml_status():
    if SAMPLE_MODE:
        return jsonify({"stage": "disabled", "disabled": True})
    return jsonify(ml_pipeline.get_status(config_path=CONFIG_PATH, db_path=resolve_state_db()))


@app.get("/api/ml/clusters")
def ml_clusters():
    if SAMPLE_MODE:
        return jsonify([])
    return jsonify(ml_pipeline.get_clusters(db_path=resolve_state_db()))


@app.post("/api/ml/ocr")
def ml_ocr():
    if SAMPLE_MODE:
        return jsonify({"disabled": True})
    return jsonify(ml_pipeline.sync_ocr_db(config_path=CONFIG_PATH, db_path=resolve_state_db()))


def path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@app.get("/image")
def serve_image():
    path_text = request.args.get("path", "")
    if not path_text:
        return "no path", 400
    candidate = Path(path_text).expanduser()
    abs_path = candidate.resolve() if candidate.is_absolute() else (BASE_DIR / candidate).resolve()
    allowed_roots = [BASE_DIR] + SOURCE_ROOTS
    if not any(path_within(abs_path, root.resolve()) for root in allowed_roots):
        return "forbidden", 403
    if not abs_path.exists() or not abs_path.is_file():
        return "not found", 404
    return send_file(abs_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tagger server.")
    parser.add_argument("--sample", action="store_true", help="Run labeling-only sample mode.")
    args = parser.parse_args()
    set_sample_mode(args.sample)

    access_log = os.environ.get("TAGGER_ACCESS_LOG", "").lower() in {"1", "true", "yes", "on"}
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    if not access_log and not any(
        isinstance(existing_filter, AccessLogFilter) for existing_filter in werkzeug_logger.filters
    ):
        werkzeug_logger.addFilter(AccessLogFilter())
    debug = os.environ.get("TAGGER_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug, port=5000)


if __name__ == "__main__":
    main()
