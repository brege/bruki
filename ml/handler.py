#!/usr/bin/env python3

import argparse
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str
    exclude: list[str] = Field(default_factory=list)


class SeriesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    sources: dict[str, SourceConfig]
    anti_patterns: list[str] = Field(default_factory=list)


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    extensions: list[str]
    anti_patterns: list[str] = Field(default_factory=list)
    data: dict[str, SeriesConfig]


@dataclass(frozen=True)
class ResolvedImage:
    series: str
    source: str
    path: Path


def load_config(config_path: str | Path) -> ConfigModel:
    config_file = Path(config_path).expanduser()
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    with config_file.open("r", encoding="utf-8") as file_handle:
        raw_config = yaml.safe_load(file_handle)
    return ConfigModel.model_validate(raw_config)


def collect_sources(
    config: ConfigModel,
    series_filter: list[str] | None = None,
    source_filter: list[str] | None = None,
    series_prefix: str | None = None,
) -> list[tuple[str, str, SourceConfig, SeriesConfig]]:
    series_names = set(series_filter or [])
    source_names = set(source_filter or [])
    if series_names:
        unknown_series = sorted(series_names - set(config.data.keys()))
        if unknown_series:
            raise ValueError(f"Unknown series filter values: {unknown_series}")

    selected: list[tuple[str, str, SourceConfig, SeriesConfig]] = []
    for series_name, series_config in sorted(config.data.items()):
        if series_names and series_name not in series_names:
            continue
        if series_prefix and not series_name.startswith(series_prefix):
            continue
        for source_name, source_config in sorted(series_config.sources.items()):
            if source_names and source_name not in source_names:
                continue
            selected.append((series_name, source_name, source_config, series_config))
    if not selected:
        raise ValueError("No sources matched the requested filters.")
    return selected


def list_image_paths(
    source_spec: SourceConfig,
    extensions: list[str],
    anti_patterns: list[str],
) -> list[Path]:
    root_path = Path(source_spec.path).expanduser()
    if not root_path.exists():
        return []
    extension_set = {extension.lower() for extension in extensions}
    matches: list[Path] = []
    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in extension_set:
            continue
        relative_path = file_path.relative_to(root_path)
        if any(exclude_dir in relative_path.parts for exclude_dir in source_spec.exclude):
            continue
        if any(fnmatch.fnmatch(file_path.name, anti_pattern) for anti_pattern in anti_patterns):
            continue
        matches.append(file_path)
    return sorted(matches)


def resolve_image_paths(
    config: ConfigModel,
    series_filter: list[str] | None = None,
    source_filter: list[str] | None = None,
    series_prefix: str | None = None,
) -> list[ResolvedImage]:
    resolved: list[ResolvedImage] = []
    sources = collect_sources(
        config=config,
        series_filter=series_filter,
        source_filter=source_filter,
        series_prefix=series_prefix,
    )
    for series_name, source_name, source_config, series_config in sources:
        anti_patterns = config.anti_patterns + series_config.anti_patterns
        file_paths = list_image_paths(source_config, config.extensions, anti_patterns)
        for file_path in file_paths:
            resolved.append(ResolvedImage(series=series_name, source=source_name, path=file_path))
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve image paths from config for notebook or shell pipelines.",
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--series", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--series-prefix", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--format", choices=["path", "tsv", "jsonl"], default="path")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    return args


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    records = resolve_image_paths(
        config=config,
        series_filter=args.series,
        source_filter=args.source,
        series_prefix=args.series_prefix,
    )
    if args.limit > 0:
        records = records[: args.limit]
    for record in records:
        if args.format == "path":
            print(record.path)
            continue
        if args.format == "tsv":
            print(f"{record.series}\t{record.source}\t{record.path}")
            continue
        payload = {"series": record.series, "source": record.source, "path": str(record.path)}
        print(json.dumps(payload))


if __name__ == "__main__":
    main()
