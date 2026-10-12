"""Behavioral checks for desktop config history."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from source.recent import MAX_RECENT, RecentConfigs


class RecentConfigsTests(unittest.TestCase):
    def test_order_restore_prune_and_clear_without_touching_configs(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            history = RecentConfigs(root / "app-state.json")
            history.remember(first)
            history.remember(second)
            history.remember(first)
            self.assertEqual(history.paths, [str(first), str(second)])
            second.unlink()
            self.assertEqual(RecentConfigs(history.state_path).paths, [str(first)])
            history.clear()
            self.assertEqual(RecentConfigs(history.state_path).paths, [])
            self.assertEqual(first.read_text(encoding="utf-8"), "first")

    def test_invalid_and_long_history_is_bounded(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            configs = [root / f"{index}.json" for index in range(MAX_RECENT + 2)]
            for config in configs:
                config.touch()
            state = root / "app-state.json"
            state.write_text(json.dumps({"recent_configs": [str(config) for config in configs] +
                                          [str(configs[0]), 42, str(root / "missing.json")]}), encoding="utf-8")
            self.assertEqual(RecentConfigs(state).paths, [str(config) for config in configs[:MAX_RECENT]])
            state.write_text("not json", encoding="utf-8")
            self.assertEqual(RecentConfigs(state).paths, [])


if __name__ == "__main__":
    unittest.main()
