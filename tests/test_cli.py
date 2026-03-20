from contextlib import redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ffinspector.cli import main
from ffinspector.models import AudioTrack, MediaInfo, SubtitleTrack, VideoTrack


class CliTests(unittest.TestCase):
    def test_default_output_is_terse(self) -> None:
        with TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir) / "Season 01"
            media_dir.mkdir()
            media_path = media_dir / "Movie.mkv"
            media_path.write_text("", encoding="utf-8")
            stub_media = MediaInfo(
                path=media_path,
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
                audio_tracks=[AudioTrack(index=1, language_code="eng", language_name="English", is_default=True)],
                subtitle_tracks=[SubtitleTrack(index=2, language_code="eng", language_name="English", codec="subrip")],
            )

            buffer = io.StringIO()
            with patch("ffinspector.cli.FFProbeRunner.inspect", return_value=stub_media):
                with redirect_stdout(buffer):
                    exit_code = main([temp_dir])

        rendered = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Movie", rendered)
        self.assertIn("Season 01/Movie.mkv", rendered)
        self.assertNotIn(temp_dir, rendered)
        self.assertIn("V", rendered)
        self.assertIn("A", rendered)
        self.assertIn("S", rendered)
        self.assertNotIn("Meta", rendered)
        self.assertNotIn("audio req", rendered)

    def test_brief_output_uses_single_line_sections(self) -> None:
        with TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir) / "Season 01"
            media_dir.mkdir()
            media_path = media_dir / "Movie.mkv"
            media_path.write_text("", encoding="utf-8")
            stub_media = MediaInfo(
                path=media_path,
                duration_seconds=3600,
                video_tracks=[VideoTrack(index=0, codec="hevc", codec_display="H.265", width=3840, height=2160)],
                audio_tracks=[
                    AudioTrack(index=1, language_code="eng", language_name="English", is_default=True),
                    AudioTrack(index=2, language_code="jpn", language_name="Japanese"),
                    AudioTrack(index=3, language_code="spa", language_name="Spanish"),
                ],
                subtitle_tracks=[
                    SubtitleTrack(index=2, language_code="jpn", language_name="Japanese", codec="subrip"),
                    SubtitleTrack(index=3, language_code="spa", language_name="Spanish", codec="ass"),
                    SubtitleTrack(index=4, language_code="fra", language_name="French", codec="subrip"),
                ],
            )

            buffer = io.StringIO()
            with patch("ffinspector.cli.FFProbeRunner.inspect", return_value=stub_media):
                with redirect_stdout(buffer):
                    exit_code = main(
                        [
                            temp_dir,
                            "--format",
                            "brief",
                            "--require-audio-language",
                            "eng",
                            "--require-subtitle-language",
                            "eng",
                        ]
                    )

        rendered = buffer.getvalue()
        rendered_lines = [line for line in rendered.splitlines() if line and not line.startswith("Summary") and not line.startswith("  ")]
        self.assertEqual(exit_code, 0)
        self.assertGreaterEqual(len(rendered_lines), 4)
        self.assertTrue(rendered_lines[0].startswith("M"))
        self.assertTrue(rendered_lines[1].startswith("V"))
        self.assertTrue(rendered_lines[2].startswith("A"))
        self.assertTrue(rendered_lines[3].startswith("S"))
        self.assertTrue(any(line.startswith("!") for line in rendered_lines))
        self.assertIn("(1 more...)", rendered)
        self.assertIn("req English", rendered)
        self.assertIn("audio req English", rendered)
        self.assertIn("subs req English", rendered)
        self.assertIn("Season 01/Movie.mkv", rendered)
        self.assertNotIn(temp_dir, rendered)

    def test_terse_output_adds_requirement_summary_line(self) -> None:
        with TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir) / "Season 01"
            media_dir.mkdir()
            media_path = media_dir / "Movie.mkv"
            media_path.write_text("", encoding="utf-8")
            stub_media = MediaInfo(
                path=media_path,
                duration_seconds=3600,
                video_tracks=[VideoTrack(index=0, codec="hevc", codec_display="H.265", width=3840, height=2160)],
                audio_tracks=[AudioTrack(index=1, language_code="eng", language_name="English", is_default=True)],
                subtitle_tracks=[SubtitleTrack(index=2, language_code="jpn", language_name="Japanese", codec="subrip")],
            )

            buffer = io.StringIO()
            with patch("ffinspector.cli.FFProbeRunner.inspect", return_value=stub_media):
                with redirect_stdout(buffer):
                    exit_code = main(
                        [
                            temp_dir,
                            "--require-audio-language",
                            "eng",
                            "--require-subtitle-language",
                            "eng",
                        ]
                    )

        rendered = buffer.getvalue()
        rendered_lines = [line for line in rendered.splitlines() if line and not line.startswith("Summary") and not line.startswith("  ")]
        self.assertEqual(exit_code, 0)
        self.assertTrue(any(line.startswith("!") for line in rendered_lines))
        self.assertIn("audio req English", rendered)
        self.assertIn("subs req English", rendered)
        self.assertIn("missing English", rendered)

    def test_json_output_renders_with_mocked_probe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir) / "Season 01"
            media_dir.mkdir()
            media_path = media_dir / "Movie.mkv"
            media_path.write_text("", encoding="utf-8")
            stub_media = MediaInfo(
                path=media_path,
                duration_seconds=3600,
                video_tracks=[VideoTrack(index=0, codec="hevc", codec_display="H.265", width=3840, height=2160)],
                audio_tracks=[AudioTrack(index=1, language_code="eng", language_name="English")],
                subtitle_tracks=[SubtitleTrack(index=2, language_code="eng", language_name="English", codec="subrip")],
            )

            buffer = io.StringIO()
            with patch("ffinspector.cli.FFProbeRunner.inspect", return_value=stub_media):
                with redirect_stdout(buffer):
                    exit_code = main([temp_dir, "--format", "json"])

        rendered = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Season 01/Movie.mkv", rendered)
        self.assertNotIn(temp_dir, rendered)
        self.assertIn('"display_title": "Movie"', rendered)

    def test_table_output_renders_rich_table_headers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            media_dir = Path(temp_dir) / "Season 01"
            media_dir.mkdir()
            media_path = media_dir / "Movie.mkv"
            media_path.write_text("", encoding="utf-8")
            stub_media = MediaInfo(
                path=media_path,
                duration_seconds=3600,
                video_tracks=[
                    VideoTrack(
                        index=0,
                        codec="hevc",
                        codec_display="H.265",
                        width=3840,
                        height=2160,
                        resolution_label="4K",
                    )
                ],
                audio_tracks=[AudioTrack(index=1, language_code="eng", language_name="English", is_default=True)],
                subtitle_tracks=[SubtitleTrack(index=2, language_code="eng", language_name="English", codec="subrip")],
            )

            buffer = io.StringIO()
            with patch("ffinspector.cli.FFProbeRunner.inspect", return_value=stub_media):
                with redirect_stdout(buffer):
                    exit_code = main(
                        [
                            temp_dir,
                            "--format",
                            "table",
                            "--require-audio-language",
                            "eng",
                            "--require-subtitle-language",
                            "eng",
                        ]
                    )

        rendered = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Title", rendered)
        self.assertIn("Dur", rendered)
        self.assertIn("VCodec", rendered)
        self.assertIn("A1", rendered)
        self.assertIn("S1", rendered)
        self.assertIn("Req A", rendered)
        self.assertIn("Req S", rendered)
        self.assertNotIn("Season 01/Movie.mkv", rendered)


if __name__ == "__main__":
    unittest.main()
