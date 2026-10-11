# Image to WebP

Convert a directory of raster images to WebP while retaining its subdirectory layout. A SHA-256 cache skips unchanged sources and checks existing output before replacing it.

## Requirements

- Python 3.10 or newer
- Pillow 10–12 with WebP support (`requirements.txt`)

## Configure and run

Copy `config.example.json` and set `source`, `target`, and `cache`. Relative paths resolve from the JSON file, so the command can run from any working directory. `source` and `target` must differ. The tool creates the target and cache directories when needed.

```sh
python convert.py --config path/to/config.json --dry-run
python convert.py --config path/to/config.json
```

`quality` is 1–100 (default 85), and `method` is 0–6 (default 6). `excludeDirectoryPrefixes` ignores matching directory names anywhere below the source root. Supported input extensions are BMP, GIF, ICO, JPEG, PNG, TIFF, and WebP. An animated input fails clearly; it is not silently reduced to one frame. SVG and application-native project files require separate rasterization.

Output is always `.webp`. Two sources mapping to the same output name cause an error before conversion. Existing output that is absent from the cache, or changed since the last cached conversion, is never overwritten. Generated output and cache writes are atomic. Removing a source does not delete its output.

Run `python -m unittest discover -s test` for the converter's local tests. Keep the cache outside version control when outputs are local. When outputs are committed, commit the cache with them so a fresh checkout can verify and skip those outputs; the Cure Interactive development wiki uses that arrangement. The example uses ignored `_temp/`.

This tool is used by the Cure Interactive development wiki, whose `_images/webp.json` maps `_images/_original` to `_images`.
