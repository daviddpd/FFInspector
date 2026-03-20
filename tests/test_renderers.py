from pathlib import Path
import re
import unittest

from ffinspector.config import AppConfig
from ffinspector.models import InspectionResult, MediaInfo, RequirementCheck, SubtitleTrack, VideoTrack
from ffinspector.renderers import TerseRenderer


class RendererTests(unittest.TestCase):
    def test_rich_renderer_emits_ansi_and_preserves_plain_text_content(self) -> None:
        result = InspectionResult(
            path=Path("/tmp/media/Show/Episode.mkv"),
            display_path="Show/Episode.mkv",
            display_title="Episode",
            media=MediaInfo(
                path=Path("/tmp/media/Show/Episode.mkv"),
                duration_seconds=3600,
                video_tracks=[
                    VideoTrack(
                        index=0,
                        codec="hevc",
                        codec_display="H.265",
                        width=3840,
                        height=2160,
                        resolution_label="4K",
                        fps=23.976,
                        dynamic_range="HDR10",
                    )
                ],
                subtitle_tracks=[SubtitleTrack(index=1, language_code="jpn", language_name="Japanese", codec="subrip")],
            ),
            nfo=None,
            audio_languages=RequirementCheck(required=["English"], present=[], missing=["English"]),
            subtitle_languages=RequirementCheck(required=["English"], present=[], missing=["English"]),
        )
        config = AppConfig()
        renderer = TerseRenderer(use_color=True, use_unicode=True)

        rendered = renderer.render([result], config)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)

        self.assertIn("\x1b[", rendered)
        self.assertIn("Show/Episode.mkv", plain)
        self.assertIn("audio req English", plain)
        self.assertIn("subs req English", plain)
        self.assertIn("Summary", plain)


if __name__ == "__main__":
    unittest.main()
