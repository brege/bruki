#!/usr/bin/env python3

import argparse
import json
import random
from pathlib import Path

from bruki.config import load_config, resolve_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sample screenshots from each screenshot source in config.yaml.",
    )
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("-s", "--seed", type=int, required=True)
    parser.add_argument("-n", "--samples", type=int, required=True)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    return args


def main() -> None:
    args = parse_args()
    random_state = random.Random(args.seed)
    config = load_config(args.config)
    sample_rows: list[dict[str, str]] = []
    for series_name, source_name, file_paths in resolve_paths(config, prefix="screenshot"):
        if len(file_paths) < args.samples:
            raise RuntimeError(
                f"Not enough files for {series_name}:{source_name}: "
                f"found {len(file_paths)}, need {args.samples}"
            )
        for file_path in random_state.sample(file_paths, args.samples):
            sample_rows.append(
                {
                    "input_path": str(file_path),
                    "series": series_name,
                    "source": source_name,
                }
            )

    output_path = Path("data") / "notebook" / "sample.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in sample_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
