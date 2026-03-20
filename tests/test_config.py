from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ffinspector.config import load_config


class ConfigTests(unittest.TestCase):
    def test_default_report_format_is_terse(self) -> None:
        config = load_config(None)
        self.assertEqual(config.report.format, "terse")

    def test_loads_fallback_yaml_shape(self) -> None:
        document = """
ffprobe_path: /usr/local/bin/ffprobe
scan:
  recursive: false
  extensions:
    - .mkv
    - mp4
report:
  sections:
    - meta
    - audio
  format: brief
requirements:
  audio_languages:
    - eng
comparison:
  duration_tolerance_seconds: 90
""".strip()
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "ffinspect.yaml"
            config_path.write_text(document, encoding="utf-8")
            config = load_config(config_path)

        self.assertEqual(config.ffprobe_path, "/usr/local/bin/ffprobe")
        self.assertFalse(config.scan.recursive)
        self.assertEqual(config.scan.extensions, [".mkv", ".mp4"])
        self.assertEqual(config.report.sections, ["meta", "audio"])
        self.assertEqual(config.report.format, "brief")
        self.assertEqual(config.requirements.audio_languages, ["eng"])
        self.assertEqual(config.comparison.duration_tolerance_seconds, 90)


if __name__ == "__main__":
    unittest.main()
