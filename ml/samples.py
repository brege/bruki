#!/usr/bin/env python3

import argparse
import random
import shutil
from pathlib import Path

from activity import list_image_paths, load_config


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


def collect_screenshot_sources(config) -> list[tuple[str, str, object, object]]:
    sources: list[tuple[str, str, object, object]] = []
    for series_name, series_config in config.data.items():
        if not series_name.startswith("screenshot"):
            continue
        for source_name, source_config in series_config.sources.items():
            sources.append((series_name, source_name, source_config, series_config))
    return sources


def sample_screenshot_sources(config, seed: int, samples: int) -> None:
    random_state = random.Random(seed)
    sources = collect_screenshot_sources(config)
    output_root = Path("data") / "samples"
    output_root.mkdir(parents=True, exist_ok=True)

    for index, (series_name, source_name, source_config, series_config) in enumerate(
        sources, start=1
    ):
        anti_patterns = config.anti_patterns + series_config.anti_patterns
        file_paths = list_image_paths(source_config, config.extensions, anti_patterns)
        if len(file_paths) < samples:
            raise RuntimeError(
                f"Not enough files for {series_name}:{source_name}: "
                f"found {len(file_paths)}, need {samples}"
            )
        selected = random_state.sample(file_paths, samples)
        output_dir = output_root / str(index)
        output_dir.mkdir(parents=True, exist_ok=True)
        for file_path in selected:
            shutil.copy2(file_path, output_dir / file_path.name)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    sample_screenshot_sources(config, args.seed, args.samples)


if __name__ == "__main__":
    main()
