from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from convert import run


ROOT = Path(__file__).resolve().parents[1]


class ConvertTest(unittest.TestCase):
    def setUp(self) -> None:
        scratch = ROOT / "_temp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "input"
        self.target = self.root / "output"
        self.source.mkdir()
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({
            "version": 1,
            "source": "input",
            "target": "output",
            "cache": "cache.json",
            "excludeDirectoryPrefixes": ["__"],
        }), encoding="utf-8")

    def image_save(self, name: str, color: str) -> Path:
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 6), color).save(path)
        return path

    def test_convert_skip_and_rebuild_changed_source(self) -> None:
        source = self.image_save("nested/picture with space.png", "red")
        self.image_save("__archive/old.png", "blue")
        self.assertEqual(run(self.config, True), {"converted": 0, "skipped": 0, "planned": 1})
        self.assertFalse(self.target.exists())
        self.assertEqual(run(self.config), {"converted": 1, "skipped": 0, "planned": 0})
        output = self.target / "nested/picture with space.webp"
        with Image.open(output) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (8, 6)))
        initial = output.read_bytes()
        self.assertEqual(run(self.config), {"converted": 0, "skipped": 1, "planned": 0})
        self.assertEqual(output.read_bytes(), initial)
        Image.new("RGB", (8, 6), "green").save(source)
        self.assertEqual(run(self.config), {"converted": 1, "skipped": 0, "planned": 0})
        self.assertNotEqual(output.read_bytes(), initial)

    def test_refuse_untracked_and_modified_output(self) -> None:
        self.image_save("picture.png", "red")
        self.target.mkdir()
        output = self.target / "picture.webp"
        output.write_bytes(b"independent output")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            run(self.config)
        self.assertEqual(output.read_bytes(), b"independent output")
        output.unlink()
        run(self.config)
        output.write_bytes(b"manual edit")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            run(self.config)

    def test_detect_output_collision_before_writing(self) -> None:
        self.image_save("picture.png", "red")
        self.image_save("picture.jpg", "blue")
        with self.assertRaisesRegex(ValueError, "output collision"):
            run(self.config)
        self.assertFalse(self.target.exists())

    def test_generate_thumbnail_from_full_size_source(self) -> None:
        self.config.write_text(json.dumps({
            "version": 1, "source": "input", "target": "output", "cache": "cache.json",
            "thumbnail": {"suffix": ".thumb", "maxWidth": 200, "maxHeight": 100},
        }), encoding="utf-8")
        source = self.source / "photo.png"
        Image.new("RGB", (800, 400), "red").save(source)
        self.assertEqual(run(self.config), {"converted": 2, "skipped": 0, "planned": 0})
        with Image.open(self.target / "photo.webp") as image:
            self.assertEqual(image.size, (800, 400))
        thumbnail = self.target / "photo.thumb.webp"
        with Image.open(thumbnail) as image:
            self.assertEqual(image.size, (200, 100))
        self.assertEqual(run(self.config, True), {"converted": 0, "skipped": 2, "planned": 0})
        self.config.write_text(json.dumps({
            "version": 1, "source": "input", "target": "output", "cache": "cache.json",
            "thumbnail": {"suffix": ".thumb", "maxWidth": 100, "maxHeight": 100},
        }), encoding="utf-8")
        self.assertEqual(run(self.config), {"converted": 1, "skipped": 1, "planned": 0})
        with Image.open(thumbnail) as image:
            self.assertEqual(image.size, (100, 50))
        Image.new("RGB", (800, 400), "blue").save(source)
        self.assertEqual(run(self.config), {"converted": 2, "skipped": 0, "planned": 0})
        thumbnail.write_bytes(b"independent edit")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            run(self.config)

    def test_thumbnail_collision_with_existing_source(self) -> None:
        self.config.write_text(json.dumps({
            "version": 1, "source": "input", "target": "output", "cache": "cache.json",
            "thumbnail": {"suffix": ".thumb", "maxWidth": 200, "maxHeight": 100},
        }), encoding="utf-8")
        self.image_save("photo.png", "red")
        self.image_save("photo.thumb.png", "blue")
        with self.assertRaisesRegex(ValueError, "output collision"):
            run(self.config)
        self.assertFalse(self.target.exists())

    def test_repository_named_and_legacy_cli(self) -> None:
        self.image_save("picture.png", "red")
        for script in ("image-to-webp.py", "convert.py"):
            with self.subTest(script=script):
                completed = subprocess.run(
                    [sys.executable, str(ROOT / script), "--config", str(self.config), "--dry-run"],
                    cwd=self.root, capture_output=True, text=True, check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(json.loads(completed.stdout.splitlines()[-1]),
                                 {"converted": 0, "planned": 1, "skipped": 0})
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
