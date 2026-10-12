"""Desktop controls for the Image to WebP converter."""

from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Empty, Queue
import tempfile
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk
from CTkToolTip import CTkToolTip

from .convert import FORMAT_VERSION, config_validate, run
from .recent import RecentConfigs


ROOT = Path(__file__).resolve().parents[1]
APP_TITLE = "Image to WebP - Cure Interactive"
APP_USER_MODEL_ID = "CureInteractive.ImageToWebP"


def set_windows_app_user_model_id(app_id: str) -> None:
    """Set an explicit Windows AppUserModelID before creating the Tk window."""
    try:
        if os.name != "nt":
            return

        import ctypes  # stdlib

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
    except Exception:
        # Best-effort; app should still run.
        return


def tooltip(*widgets, text: str) -> None:
    """Keep each hover tip alive for as long as its control exists."""
    for widget in widgets:
        widget._cure_tooltip = CTkToolTip(widget, message=text, delay=0.4,
                                         wraplength=420, justify="left")


class App(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("880x750")
        self.minsize(720, 650)
        if os.name == "nt" and (ROOT / "icon.ico").is_file():
            self.iconbitmap(str(ROOT / "icon.ico"))

        self.recents = RecentConfigs(ROOT / "app-state.json")
        self.config_path = tk.StringVar(value=str(ROOT / "config.json"))
        self.active_config_path = self.config_path.get()
        self.source = tk.StringVar()
        self.target = tk.StringVar()
        self.cache = tk.StringVar(value="_temp/webp-cache.json")
        self.quality = tk.StringVar(value="85")
        self.method = tk.StringVar(value="6")
        self.prefixes = tk.StringVar(value="__")
        self.thumbnail_enabled = tk.BooleanVar(value=False)
        self.thumbnail_suffix = tk.StringVar(value=".thumb")
        self.thumbnail_width = tk.StringVar(value="512")
        self.thumbnail_height = tk.StringVar(value="256")
        self.thumbnail_skip_when_source_fits = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Choose an input folder and output folder to begin.")
        self.events: Queue[tuple] = Queue()
        self.busy = False
        self._build()
        initial_config = Path(self.recents.paths[0]) if self.recents.paths else Path(self.config_path.get())
        if initial_config.is_file():
            self._load_config(initial_config)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Image to WebP", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        ctk.CTkLabel(header, text="Convert a folder of images while preserving its layout. Unchanged files are skipped.").grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        form = ctk.CTkScrollableFrame(self)
        form.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        form.grid_columnconfigure(1, weight=1)
        self._config_row(form)
        self._path_row(form, 1, "Input folder", self.source, lambda: self._choose_directory(self.source),
                       "The source folder to scan recursively for BMP, GIF, ICO, JPEG, PNG, TIFF, and WebP images. "
                       "Its subfolder layout is preserved in the output. Animated images stop with an error.")
        self._path_row(form, 2, "Output folder", self.target, lambda: self._choose_directory(self.target),
                       "Where converted .webp files are written. It must be different from and outside the input folder. "
                       "Existing files are only replaced when the cache proves they are the tool's previous output.")
        self._path_row(form, 3, "Cache file", self.cache, self._choose_cache,
                       "A JSON record of source hashes, conversion settings, and output hashes. "
                       "It lets repeat runs skip unchanged images and protects independently edited output. "
                       "Keep it outside the input folder.")

        ctk.CTkLabel(form, text="Conversion settings", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(18, 5))
        settings = ctk.CTkFrame(form)
        settings.grid(row=5, column=0, columnspan=3, sticky="ew", padx=10)
        for column in range(4):
            settings.grid_columnconfigure(column, weight=1 if column % 2 else 0)
        quality_label = ctk.CTkLabel(settings, text="Quality (1–100)")
        quality_label.grid(row=0, column=0, sticky="w", padx=12, pady=10)
        quality_entry = ctk.CTkEntry(settings, textvariable=self.quality, width=100)
        quality_entry.grid(row=0, column=1, sticky="w", padx=8)
        tooltip(quality_label, quality_entry, text="WebP quality from 1 to 100. Higher values usually preserve more detail "
                "and produce larger files. The default is 85; changing it regenerates cached output.")
        method_label = ctk.CTkLabel(settings, text="Method (0–6)")
        method_label.grid(row=0, column=2, sticky="w", padx=12)
        method_entry = ctk.CTkEntry(settings, textvariable=self.method, width=100)
        method_entry.grid(row=0, column=3, sticky="w", padx=8)
        tooltip(method_label, method_entry, text="WebP encoding effort from 0 to 6. Higher values take longer to encode "
                "and may compress better. The default is 6; changing it regenerates cached output.")
        prefixes_label = ctk.CTkLabel(settings, text="Exclude folder prefixes")
        prefixes_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        prefixes_entry = ctk.CTkEntry(settings, textvariable=self.prefixes)
        prefixes_entry.grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(8, 12), pady=(0, 10))
        tooltip(prefixes_label, prefixes_entry, text="Comma-separated starts of folder names to skip anywhere below "
                "the input root. For example, __ skips __archive and __draft. This matches directories only, "
                "not filenames; leave the field empty to scan every folder.")
        ctk.CTkLabel(settings, text="Comma separated; for example, __, .git", text_color="gray70").grid(
            row=2, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 10))

        thumbnail = ctk.CTkFrame(form)
        thumbnail.grid(row=6, column=0, columnspan=3, sticky="ew", padx=10, pady=(12, 0))
        for column in range(6):
            thumbnail.grid_columnconfigure(column, weight=1 if column % 2 else 0)
        thumbnail_check = ctk.CTkCheckBox(thumbnail, text="Create thumbnails", variable=self.thumbnail_enabled)
        thumbnail_check.grid(
            row=0, column=0, columnspan=6, sticky="w", padx=12, pady=12)
        tooltip(thumbnail_check, text="Create a second WebP beside each full-size output. The thumbnail keeps its "
                "aspect ratio, fits within the width and height below, and is never enlarged. "
                "Turn this off to make only full-size output.")
        for column, label, variable in (
            (0, "Suffix", self.thumbnail_suffix),
            (2, "Max width", self.thumbnail_width),
            (4, "Max height", self.thumbnail_height),
        ):
            field_label = ctk.CTkLabel(thumbnail, text=label)
            field_label.grid(row=1, column=column, sticky="w", padx=(12, 4), pady=(0, 12))
            field_entry = ctk.CTkEntry(thumbnail, textvariable=variable, width=105)
            field_entry.grid(
                row=1, column=column + 1, sticky="ew", padx=(0, 12), pady=(0, 12))
            help_text = {
                "Suffix": "Text inserted before .webp in the thumbnail filename. For example, .thumb produces "
                          "photo.thumb.webp. It must be a filename suffix without a path separator.",
                "Max width": "Maximum thumbnail width in pixels, from 1 to 16384. The original aspect ratio "
                             "is kept, so a thumbnail may be narrower than this limit.",
                "Max height": "Maximum thumbnail height in pixels, from 1 to 16384. The original aspect ratio "
                              "is kept, so a thumbnail may be shorter than this limit.",
            }[label]
            tooltip(field_label, field_entry, text=help_text)
        thumbnail_skip_check = ctk.CTkCheckBox(
            thumbnail, text="Skip thumbnails when the source already fits",
            variable=self.thumbnail_skip_when_source_fits)
        thumbnail_skip_check.grid(row=2, column=0, columnspan=6, sticky="w", padx=12, pady=(0, 8))
        tooltip(thumbnail_skip_check, text="When enabled, omit the .thumb.webp if the source width and height "
                "are both within the maximum dimensions above. The full .webp is still created. "
                "Existing thumbnail files are not deleted. Off by default for existing links.")
        ctk.CTkLabel(thumbnail, text="A .thumb suffix creates photo.thumb.webp beside photo.webp.",
                     text_color="gray70").grid(row=3, column=0, columnspan=6, sticky="w", padx=12, pady=(0, 12))

        bottom = ctk.CTkFrame(self)
        bottom.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        bottom.grid_columnconfigure(0, weight=1)
        actions = ctk.CTkFrame(bottom, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.save_button = ctk.CTkButton(actions, text="Save config", width=125, command=self._save_clicked)
        self.save_button.pack(side="left", padx=(0, 8))
        tooltip(self.save_button, text="Validate and save the current fields to the config file shown above. "
                "This does not convert images. An existing config at that path is replaced.")
        self.save_as_button = ctk.CTkButton(actions, text="Save as...", width=105, command=self._save_as_clicked)
        self.save_as_button.pack(side="left", padx=(0, 8))
        tooltip(self.save_as_button, text="Choose a different JSON config path and save the current settings there. "
                "Use this after loading the example so the example file stays unchanged.")
        self.dry_button = ctk.CTkButton(actions, text="Dry run", width=125, command=lambda: self._start(True))
        self.dry_button.pack(side="left", padx=8)
        tooltip(self.dry_button, text="Save the current config, scan the input, compare source and output hashes, "
                "and report what would be converted. No WebP output or cache entries are written.")
        self.convert_button = ctk.CTkButton(actions, text="Convert images", width=150,
                                            command=lambda: self._start(False))
        self.convert_button.pack(side="left", padx=8)
        tooltip(self.convert_button, text="Save the current config and convert images that are new or changed. "
                "Unchanged output is skipped. Output modified outside this tool is refused, never silently overwritten.")
        self.progress = ctk.CTkProgressBar(bottom)
        self.progress.grid(row=1, column=0, sticky="ew", padx=12)
        self.progress.set(0)
        ctk.CTkLabel(bottom, textvariable=self.status, anchor="w").grid(
            row=2, column=0, sticky="ew", padx=12, pady=(8, 4))
        self.log = ctk.CTkTextbox(bottom, height=85)
        self.log.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.log.configure(state="disabled")

    def _config_row(self, parent) -> None:
        help_text = ("The JSON file that stores this conversion setup. Pick a recent config from the "
                     "dropdown to load its input, output, cache, and settings, or type a path and press Load. "
                     "Paths in a config may be relative to that file. Save, Dry run, and Convert add the "
                     "selected config to local history after saving it.")
        label = ctk.CTkLabel(parent, text="Config file")
        label.grid(row=0, column=0, sticky="w", padx=10, pady=7)
        self.config_combo = ctk.CTkComboBox(parent, variable=self.config_path,
                                             values=self.recents.paths, command=self._select_recent)
        self.config_combo.grid(row=0, column=1, sticky="ew", padx=10, pady=7)
        tooltip(label, self.config_combo, text=help_text)
        buttons = ctk.CTkFrame(parent, fg_color="transparent")
        buttons.grid(row=0, column=2, sticky="e", padx=10, pady=7)
        browse = ctk.CTkButton(buttons, text="Browse...", width=85, command=self._choose_config)
        browse.pack(side="left")
        tooltip(browse, text="Choose an existing conversion JSON file and load its settings. " + help_text)
        load = ctk.CTkButton(buttons, text="Load", width=85, command=self._load_selected)
        load.pack(side="left", padx=(8, 0))
        tooltip(load, text="Load the JSON path shown in the config field. This replaces current form values "
                "without starting a conversion. A successful load moves the config to the top of Recents.")
        clear = ctk.CTkButton(buttons, text="Clear history", width=105, command=self._clear_recents)
        clear.pack(side="left", padx=(8, 0))
        tooltip(clear, text="Forget the list of recent conversion configs on this computer. "
                "The current form and saved JSON config files are not changed or deleted.")

    def _refresh_recents(self) -> None:
        self.config_combo.configure(values=self.recents.paths)

    def _remember_config(self, path: Path) -> None:
        try:
            self.recents.remember(path)
        except OSError as error:
            self.status.set(f"Config ready, but recent history could not be saved: {error}")
        self._refresh_recents()

    def _select_recent(self, chosen: str) -> None:
        if not self._load_config(Path(chosen)):
            self.config_path.set(self.active_config_path)

    def _clear_recents(self) -> None:
        try:
            self.recents.clear()
        except OSError as error:
            messagebox.showerror(APP_TITLE, f"Could not clear history:\n{error}")
            return
        self._refresh_recents()
        self.status.set("Recent config history cleared. Current settings are unchanged.")

    def _path_row(self, parent, row: int, label: str, variable: tk.StringVar, browse: Callable[[], None],
                  help_text: str,
                  button_label: str = "Browse...") -> None:
        field_label = ctk.CTkLabel(parent, text=label)
        field_label.grid(row=row, column=0, sticky="w", padx=10, pady=7)
        field_entry = ctk.CTkEntry(parent, textvariable=variable)
        field_entry.grid(row=row, column=1, sticky="ew", padx=10, pady=7)
        tooltip(field_label, field_entry, text=help_text)
        buttons = ctk.CTkFrame(parent, fg_color="transparent")
        buttons.grid(row=row, column=2, sticky="e", padx=10, pady=7)
        browse_button = ctk.CTkButton(buttons, text=button_label, width=85, command=browse)
        browse_button.pack(side="left")
        tooltip(browse_button, text="Choose the " + label.lower() + " using a file or folder picker. " + help_text)

    def _choose_directory(self, variable: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(initialdir=variable.get() or str(ROOT))
        if chosen:
            variable.set(chosen)

    def _choose_config(self) -> None:
        current = Path(self.config_path.get()).expanduser()
        initial = current.parent if current.parent.is_dir() else ROOT
        chosen = filedialog.askopenfilename(title="Load conversion config", initialdir=initial,
                                             filetypes=[("JSON", "*.json")])
        if chosen:
            self.config_path.set(chosen)
            self._load_config(Path(chosen))

    def _choose_cache(self) -> None:
        chosen = filedialog.asksaveasfilename(title="Choose cache file", defaultextension=".json",
                                               filetypes=[("JSON", "*.json")])
        if chosen:
            self.cache.set(chosen)

    def _load_selected(self) -> None:
        self._load_config(Path(self.config_path.get()).expanduser())

    def _load_config(self, path: Path) -> bool:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(config, dict) or config.get("version") != FORMAT_VERSION:
                raise ValueError(f"config must declare version {FORMAT_VERSION}")
            prefixes = config.get("excludeDirectoryPrefixes", [])
            if not isinstance(prefixes, list) or not all(isinstance(item, str) for item in prefixes):
                raise ValueError("excludeDirectoryPrefixes must be a list of strings")
            thumb = config.get("thumbnail")
            if thumb is not None and not isinstance(thumb, dict):
                raise ValueError("thumbnail must be an object or null")
            self.source.set(config.get("source", ""))
            self.target.set(config.get("target", ""))
            self.cache.set(config.get("cache", ""))
            self.quality.set(str(config.get("quality", 85)))
            self.method.set(str(config.get("method", 6)))
            self.prefixes.set(", ".join(prefixes))
            self.thumbnail_enabled.set(thumb is not None)
            self.thumbnail_skip_when_source_fits.set(False)
            if isinstance(thumb, dict):
                self.thumbnail_suffix.set(str(thumb.get("suffix", ".thumb")))
                self.thumbnail_width.set(str(thumb.get("maxWidth", 512)))
                self.thumbnail_height.set(str(thumb.get("maxHeight", 256)))
                self.thumbnail_skip_when_source_fits.set(thumb.get("skipWhenSourceFits", False))
            self.config_path.set(str(path.resolve()))
            self.active_config_path = self.config_path.get()
            self.status.set(f"Loaded {path}")
            self._remember_config(path)
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            messagebox.showerror(APP_TITLE, f"Could not load config:\n{error}")
            return False

    def _settings(self) -> dict:
        try:
            settings = {
                "version": FORMAT_VERSION,
                "source": self.source.get().strip(),
                "target": self.target.get().strip(),
                "cache": self.cache.get().strip(),
                "quality": int(self.quality.get()),
                "method": int(self.method.get()),
                "excludeDirectoryPrefixes": [part.strip() for part in self.prefixes.get().split(",") if part.strip()],
            }
            if self.thumbnail_enabled.get():
                settings["thumbnail"] = {
                    "suffix": self.thumbnail_suffix.get().strip(),
                    "maxWidth": int(self.thumbnail_width.get()),
                    "maxHeight": int(self.thumbnail_height.get()),
                    "skipWhenSourceFits": self.thumbnail_skip_when_source_fits.get(),
                }
            path = Path(self.config_path.get()).expanduser().resolve()
            if not path.parent.is_dir():
                raise ValueError(f"config directory does not exist: {path.parent}")
            config_validate(settings, path.parent)
            return settings
        except ValueError as error:
            raise ValueError(f"Invalid settings: {error}") from error

    def _save_config(self) -> Path:
        settings = self._settings()
        path = Path(self.config_path.get()).expanduser().resolve()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                             prefix=".webp-config-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(settings, stream, indent=2)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.config_path.set(str(path))
        self.active_config_path = self.config_path.get()
        self._remember_config(path)
        return path

    def _save_clicked(self) -> None:
        try:
            path = self._save_config()
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_TITLE, str(error))
            return
        self.status.set(f"Saved {path}")

    def _save_as_clicked(self) -> None:
        current = Path(self.config_path.get()).expanduser()
        initial = current.parent if current.parent.is_dir() else ROOT
        chosen = filedialog.asksaveasfilename(title="Save conversion config", initialdir=initial,
                                               defaultextension=".json",
                                               filetypes=[("JSON", "*.json")])
        if chosen:
            self.config_path.set(chosen)
            self._save_clicked()

    def _start(self, dry_run: bool) -> None:
        if self.busy:
            return
        try:
            path = self._save_config()
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_TITLE, str(error))
            return
        self.busy = True
        for button in (self.save_button, self.save_as_button, self.dry_button, self.convert_button):
            button.configure(state="disabled")
        self.progress.set(0)
        self.status.set("Checking images...")
        self._append(f"{'Dry run' if dry_run else 'Conversion'}: {path}")
        Thread(target=self._work, args=(path, dry_run), daemon=True).start()
        self.after(100, self._drain)

    def _work(self, path: Path, dry_run: bool) -> None:
        def report(index: int, total: int, detail: str) -> None:
            self.events.put(("progress", index, total, detail))

        try:
            counts = run(path, dry_run, progress=report)
            self.events.put(("done", counts))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.events.put(("error", str(error)))

    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, index, total, detail = event
                    self.progress.set(index / total)
                    self.status.set(f"{index}/{total}: {detail}")
                    self._append(detail)
                elif event[0] == "done":
                    counts = event[1]
                    summary = f"Converted {counts['converted']}; skipped {counts['skipped']}; planned {counts['planned']}."
                    self.status.set(summary)
                    self._append(summary)
                    self._finish()
                elif event[0] == "error":
                    self.status.set("Conversion stopped: " + event[1])
                    self._append("Error: " + event[1])
                    messagebox.showerror(APP_TITLE, event[1])
                    self._finish()
        except Empty:
            pass
        if self.busy:
            self.after(100, self._drain)

    def _append(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _finish(self) -> None:
        self.busy = False
        for button in (self.save_button, self.save_as_button, self.dry_button, self.convert_button):
            button.configure(state="normal")

    def _close(self) -> None:
        if self.busy:
            messagebox.showinfo(APP_TITLE, "Wait for the current run to finish before closing.")
            return
        self.destroy()


def main() -> int:
    # Must happen early for best taskbar behavior on Windows.
    set_windows_app_user_model_id(APP_USER_MODEL_ID)

    app = App()
    app.mainloop()
    return 0
