from __future__ import annotations

import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
