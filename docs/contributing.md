## Contributing

### Linters / Formatters

| Formatter    | Extension              | Description |
|:------------ |:---------------------- |:----------- |
| `nbstripout` | `.ipynb` | don't commit any Jupyter notebook outputs |
| `nbqa`       | `.ipynb` | opinionated notebook linter (preserves aligned '=' cells) |
| `ruff`       | `.py`    | general purpose python linter and formatter |
| `biome`      | `.js`, `.css`, `.html` | formats client-side code |

### Architecture

Subject to change. One dependency direction:

```
image_activity/activity.py   config, path resolution, timestamp extraction
        ↓
www/ml.py                    pipeline: embed, cluster, write state
        ↓
www/api.py                   Flask app; the only runtime entry point
```

`activity.py` is the only place config is loaded. `ml.py` is a library. It has no CLI. `api.py` imports `ml`; nothing imports back up the chain.

### Code conventions
- Typed dataclasses for structured data. `dict[str, Any]` only for genuinely open-ended config blobs.
- String-keyed dispatch tables for routing by type or kind.
- File-backed data (JSONL, labels) is cached by fingerprint or mtime. Avoid adding per-request reads.
- Progress/status writes in loops are throttled by count and time. Avoid writing on every iteration.
- Config validation is strict and happens at load time. Unknown references raise immediately.

### Tools

- **Pydantic** is the config contract. All YAML input is validated through `ConfigModel` at load time. Do not re-validate or re-parse config downstream.

- **pandas** is the data layer for anything involving image records, timestamps, or aggregations in the notebook, and sometimes in the app code. Manipulate JSON structures through and around the Flask API code only.
