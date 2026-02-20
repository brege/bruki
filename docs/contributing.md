## Contributing

### Linters / Formatters

<table>
  <thead>
    <tr>
      <th>Formatter</th>
      <th>Extension</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="https://github.com/kynan/nbstripout">nbstripout</a></td>
      <td><code>.ipynb</code></td>
      <td>ensures Jupyter notebook output cells aren't committed</td>
    </tr>
    <tr>
      <td><a href="https://github.com/nbQA-dev/nbQA">nbqa</a></td>
      <td><code>.ipynb</code></td>
      <td>Jupyter notebook linter and formatter</td>
    </tr>
    <tr>
      <td><a href="https://github.com/astral-sh/ruff">ruff</a></td>
      <td><code>.py</code></td>
      <td>general purpose python linter and formatter</td>
    </tr>
    <tr>
      <td><a href="https://github.com/astral-sh/ty">ty</a></td>
      <td><code>.py</code></td>
      <td>static type checker</td>
    </tr>
    <tr>
      <td><a href="https://github.com/biomejs/biome">biome</a></td>
      <td><code>.js</code>, <code>.css</code>, <code>.html</code></td>
      <td>formats client-side code</td>
    </tr>
  </tbody>
</table>

While [ruff](https://github.com/charliermarsh/ruff) can format Jupyter notebooks, [nbqa](https://github.com/nbQA-dev/nbQA) has relaxed alignment rules that cannot be configured in Ruff; specifically: aligning code blocks on equal signs.

### Architecture

> [!WARNING] 
> Subject to change. 

One dependency direction:

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
