# Image to WebP

Convert a directory of raster images to WebP while retaining its subdirectory layout. A SHA-256 cache skips unchanged sources and checks existing output before replacing it.

## Requirements

- Python 3.10 or newer
- Pillow 10–12 with WebP support and CustomTkinter (`requirements.txt`)

## Install

```sh
python setup.py --venv
```

This creates `.venv` beside the script and installs `requirements.txt`. The setup command works from any current directory; use `--print-only` to inspect its commands. Activate the environment or run its Python directly when using `image-to-webp.py`.

## Desktop app

Double-click `image-to-webp.py` on Windows, or run `python image-to-webp.py` without arguments, to open the desktop interface. The Windows `.py` association may use a different Python from `python` on `PATH`; if its GUI dependencies are unavailable, this launcher uses the `python` on `PATH` when that interpreter has Tkinter and the packages in `requirements.txt`. Otherwise it prints a setup error. It is the only root-level app launcher; the GUI implementation and converter live in `source/`. Choose an input folder, an output folder, and a cache file. Adjust quality (1–100), method (0–6), excluded folder prefixes, and optional thumbnail settings. **Dry run** previews conversion work; **Convert images** writes WebP files. Both actions save the current settings to the selected config file first. The default local `config.json` is ignored by Git. Use **Browse...** and **Load** to open an existing config, including `config.example.json` as a starting point; use **Save as...** to keep the example unchanged. The config dropdown lists recently loaded or saved configs, newest first, and the latest is restored when the app opens. **Clear history** forgets that list without deleting configs or changing the current form. Missing configs are removed from the list. History is kept in ignored, machine-local `app-state.json`.

The progress area reports each image and the converted, skipped, and planned totals. Existing output changed outside this tool is refused rather than overwritten.
Hover over a field, label, or action button for detailed help about its effect and valid values.

## Configure and run

Copy `config.example.json` and set `source`, `target`, and `cache`. Relative paths resolve from the JSON file, so the command can run from any working directory. `source` and `target` must differ. The tool creates the target and cache directories when needed.

```sh
python image-to-webp.py --config path/to/config.json --dry-run
python image-to-webp.py --config path/to/config.json
```

`image-to-webp.py` opens the desktop app without arguments and accepts the same command-line options when arguments are provided. Automation can also run `source/convert.py` directly or import `run()` from `source.convert`.

`quality` is 1–100 (default 85), and `method` is 0–6 (default 6). `excludeDirectoryPrefixes` ignores matching directory names anywhere below the source root. Supported input extensions are BMP, GIF, ICO, JPEG, PNG, TIFF, and WebP. An animated input fails clearly; it is not silently reduced to one frame. SVG and application-native project files require separate rasterization.

An optional `thumbnail` recipe generates a second WebP from each source without requiring another original. Its `suffix` is appended before `.webp`; `maxWidth` and `maxHeight` bound the thumbnail while preserving aspect ratio and avoiding enlargement. For example, `photo.png` produces both `photo.webp` and `photo.thumb.webp` with the example configuration. Set `skipWhenSourceFits` to `true` to omit the thumbnail when the source width and height are both within those bounds; the full WebP is still created. This setting defaults to `false` for existing configurations. Omit `thumbnail` to retain the original one-output behavior. Existing source files that would collide with a generated thumbnail cause an error before conversion; remove or rename those sources only after preserving them separately.

Output is always `.webp`. Two sources mapping to the same output name cause an error before conversion. Existing output that is absent from the cache, or changed since the last cached conversion, is never overwritten. Generated output and cache writes are atomic. Thumbnail cache entries include their size and resampling recipe, so changing those settings regenerates only affected thumbnails. Removing a source or enabling the thumbnail skip option does not delete existing output or cache entries; review any links before removing old thumbnails yourself.

Run `python -m unittest discover -s test` for the converter's local tests. Keep the cache outside version control when outputs are local. When outputs are committed, commit the cache with them so a fresh checkout can verify and skip those outputs; the Cure Interactive development wiki uses that arrangement. The example uses ignored `_temp/`.

This tool is used by the Cure Interactive development wiki, whose `_images/webp.json` maps `_images/_original` to `_images`.

## Icon proposal

`_development/icon.svg` is the editable icon source, following the neighboring utilities' layout: a blue-to-magenta image tile, a white conversion arrow, and a green `W` tile for WebP. `icon.png` and `icon.ico` are its root-level derived assets. The desktop app uses `icon.ico` as its window icon on Windows.
