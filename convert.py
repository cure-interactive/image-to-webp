#!/usr/bin/env python3
"""Convert a configured raster source tree to WebP without repeating unchanged work."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from PIL import Image, UnidentifiedImageError, __version__ as PILLOW_VERSION


FORMAT_VERSION = 1
CONVERTER_VERSION = 1
SOURCE_SUFFIXES = {".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class Conversion:
    source: Path
    destination: Path
    cache_key: str
    thumbnail_size: tuple[int, int] | None = None


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_load(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("version") != FORMAT_VERSION:
        raise ValueError(f"config must declare version {FORMAT_VERSION}")
    for name in ("source", "target", "cache"):
        if not isinstance(config.get(name), str) or not config[name].strip():
            raise ValueError(f"config {name} must be a nonempty path")
    for name, lower, upper, default in (("quality", 1, 100, 85), ("method", 0, 6, 6)):
        value = config.get(name, default)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"config {name} must be an integer from {lower} to {upper}")
        config[name] = value
    prefixes = config.get("excludeDirectoryPrefixes", [])
    if not isinstance(prefixes, list) or any(not isinstance(item, str) or not item for item in prefixes):
        raise ValueError("config excludeDirectoryPrefixes must be a list of nonempty strings")
    config["excludeDirectoryPrefixes"] = prefixes
    thumbnail = config.get("thumbnail")
    if thumbnail is not None:
        if not isinstance(thumbnail, dict):
            raise ValueError("config thumbnail must be an object")
        suffix = thumbnail.get("suffix")
        if (not isinstance(suffix, str) or not suffix or suffix in (".", "..")
                or any(character in suffix for character in ("/", "\\", ":"))):
            raise ValueError("config thumbnail suffix must be a nonempty filename suffix")
        for name in ("maxWidth", "maxHeight"):
            value = thumbnail.get(name)
            if type(value) is not int or not 1 <= value <= 16384:
                raise ValueError(f"config thumbnail {name} must be an integer from 1 to 16384")
        config["thumbnail"] = thumbnail
    for name in ("source", "target", "cache"):
        config[name] = (path.parent / config[name]).resolve()
    if not config["source"].is_dir():
        raise ValueError(f"source directory does not exist: {config['source']}")
    if config["source"] == config["target"]:
        raise ValueError("source and target directories must differ")
    if config["target"].is_relative_to(config["source"]):
        raise ValueError("target directory must not be inside the source directory")
    if config["cache"].is_relative_to(config["source"]):
        raise ValueError("cache must be outside the source directory")
    return config


def cache_load(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != FORMAT_VERSION or not isinstance(value.get("entries"), dict):
        raise ValueError(f"invalid cache: {path}")
    return value["entries"]


def cache_save(path: Path, entries: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": FORMAT_VERSION, "entries": entries}, indent=2, sort_keys=True) + "\n"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=".webp-cache-", suffix=".tmp", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def source_list(config: dict) -> list[Conversion]:
    source = config["source"]
    prefixes = config["excludeDirectoryPrefixes"]
    candidates: list[Conversion] = []
    destination_by_folded_path = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(source)
        if any(part.startswith(prefix) for part in relative.parts[:-1] for prefix in prefixes):
            continue
        if not path.resolve().is_relative_to(source):
            raise ValueError(f"source file leaves source directory: {path}")
        planned = [(relative, None)]
        if config.get("thumbnail") is not None:
            thumbnail = config["thumbnail"]
            thumbnail_relative = relative.with_name(relative.stem + thumbnail["suffix"] + relative.suffix)
            planned.append((thumbnail_relative, (thumbnail["maxWidth"], thumbnail["maxHeight"])))
        for output_relative, thumbnail_size in planned:
            destination = config["target"] / output_relative.with_suffix(".webp")
            if not destination.parent.resolve().is_relative_to(config["target"]):
                raise ValueError(f"output path leaves target directory: {destination}")
            if destination.resolve() == path.resolve():
                raise ValueError(f"source and output are the same file: {path}")
            folded = str(destination).casefold()
            if folded in destination_by_folded_path:
                raise ValueError(f"output collision: {destination_by_folded_path[folded]} and {path}")
            destination_by_folded_path[folded] = path
            candidates.append(Conversion(path, destination, output_relative.as_posix(), thumbnail_size))
    return candidates


def image_convert(source: Path, destination: Path, quality: int, method: int,
                  thumbnail_size: tuple[int, int] | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with Image.open(source) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError(f"animated image requires separate handling: {source}")
            mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
            rendered = image.convert(mode)
            if thumbnail_size is not None:
                rendered.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
            dimensions = rendered.size
            icc_profile = image.info.get("icc_profile")
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".webp-output-",
                                             suffix=".webp", delete=False) as stream:
                temporary_path = Path(stream.name)
            options = {"format": "WEBP", "quality": quality, "method": method}
            if icc_profile:
                options["icc_profile"] = icc_profile
            rendered.save(temporary_path, **options)
        with Image.open(temporary_path) as result:
            if result.format != "WEBP" or result.size != dimensions:
                raise ValueError(f"output validation failed: {temporary_path}")
            result.verify()
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def run(config_path: Path, dry_run_is_active: bool = False) -> dict[str, int]:
    config = config_load(config_path.resolve())
    sources = source_list(config)
    entries = cache_load(config["cache"])
    signature = f"converter={CONVERTER_VERSION};pillow={PILLOW_VERSION};quality={config['quality']};method={config['method']}"
    counts = {"converted": 0, "skipped": 0, "planned": 0}
    for conversion in sources:
        source, destination = conversion.source, conversion.destination
        relative = conversion.cache_key
        job_signature = signature
        if conversion.thumbnail_size is not None:
            width, height = conversion.thumbnail_size
            job_signature += f";thumbnail={width}x{height};resample=lanczos;noUpscale=true"
        source_digest = file_hash(source)
        entry = entries.get(relative)
        output_digest = file_hash(destination) if destination.is_file() else None
        if (isinstance(entry, dict) and entry.get("sourceSha256") == source_digest
                and entry.get("signature") == job_signature and entry.get("outputSha256") == output_digest):
            counts["skipped"] += 1
            continue
        if output_digest is not None and (not isinstance(entry, dict) or entry.get("outputSha256") != output_digest):
            raise ValueError(f"output is not the last cached result; refusing to overwrite: {destination}")
        if dry_run_is_active:
            counts["planned"] += 1
            print(f"would convert: {source} -> {destination}")
            continue
        try:
            image_convert(source, destination, config["quality"], config["method"], conversion.thumbnail_size)
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise ValueError(f"could not convert {source}: {error}") from error
        entries[relative] = {"sourceSha256": source_digest, "outputSha256": file_hash(destination),
                             "signature": job_signature}
        cache_save(config["cache"], entries)
        counts["converted"] += 1
        print(f"converted: {source} -> {destination}")
    print(json.dumps(counts, sort_keys=True))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="JSON mapping file")
    parser.add_argument("--dry-run", action="store_true", help="inspect conversion work without writing files")
    arguments = parser.parse_args()
    try:
        run(arguments.config, arguments.dry_run)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
