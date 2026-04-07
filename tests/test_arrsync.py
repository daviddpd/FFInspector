from __future__ import annotations

import io
import sqlite3
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ffinspector.cli import main


class ArrDateSyncTests(unittest.TestCase):
    def test_radarr_dry_run_uses_movie_file_without_updating_database(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "radarr.db"
            movie_dir = root / "Movies" / "Example Movie (1999)"
            movie_dir.mkdir(parents=True)
            movie_path = movie_dir / "Example.Movie.1999.mkv"
            movie_path.write_text("", encoding="utf-8")

            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE Movies (
                    Id INTEGER PRIMARY KEY,
                    Path TEXT NOT NULL,
                    Added TEXT,
                    MovieFileId INTEGER,
                    MovieMetadataId INTEGER
                );
                CREATE TABLE MovieFiles (
                    Id INTEGER PRIMARY KEY,
                    MovieId INTEGER,
                    RelativePath TEXT,
                    OriginalFilePath TEXT
                );
                CREATE TABLE MovieMetadata (
                    Id INTEGER PRIMARY KEY,
                    Title TEXT NOT NULL
                );
                """,
            )
            connection.execute("INSERT INTO MovieMetadata (Id, Title) VALUES (1, 'Example Movie')")
            connection.execute(
                "INSERT INTO MovieFiles (Id, MovieId, RelativePath) VALUES (7, 1, ?)",
                (movie_path.name,),
            )
            connection.execute(
                "INSERT INTO Movies (Id, Path, Added, MovieFileId, MovieMetadataId) VALUES (1, ?, '2025-05-01 00:00:00Z', 7, 1)",
                (str(movie_dir),),
            )
            connection.commit()
            connection.close()

            buffer = io.StringIO()
            timestamp_map = {
                movie_path: _resolved_timestamp("2020-01-02T03:04:05+00:00", "modified"),
            }
            with patch(
                "ffinspector.arrsync._effective_timestamp_for_path",
                side_effect=lambda path: timestamp_map.get(path),
            ):
                with redirect_stdout(buffer):
                    exit_code = main(["arr-date-sync", "radarr", str(db_path)])

            self.assertEqual(exit_code, 0)
            rendered = buffer.getvalue()
            self.assertIn("DRY RUN radarr first-media", rendered)
            self.assertIn("movie: Example Movie", rendered)
            self.assertIn("2025-05-01 00:00:00Z", rendered)
            self.assertIn("2020-01-02 03:04:05Z", rendered)

            connection = sqlite3.connect(db_path)
            added = connection.execute("SELECT Added FROM Movies WHERE Id = 1").fetchone()[0]
            connection.close()
            self.assertEqual(added, "2025-05-01 00:00:00Z")

    def test_sonarr_apply_prefers_s01e01_when_present(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "sonarr.db"
            series_dir = root / "TV" / "Example Show"
            season_zero = series_dir / "Season 00"
            season_one = series_dir / "Season 01"
            season_zero.mkdir(parents=True)
            season_one.mkdir(parents=True)
            special_path = season_zero / "Example.Show.S00E01.mkv"
            episode_path = season_one / "Example.Show.S01E01.mkv"
            special_path.write_text("", encoding="utf-8")
            episode_path.write_text("", encoding="utf-8")

            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE Series (
                    Id INTEGER PRIMARY KEY,
                    Title TEXT NOT NULL,
                    Path TEXT NOT NULL,
                    Added TEXT
                );
                CREATE TABLE EpisodeFiles (
                    Id INTEGER PRIMARY KEY,
                    SeriesId INTEGER NOT NULL,
                    RelativePath TEXT,
                    OriginalFilePath TEXT
                );
                CREATE TABLE Episodes (
                    Id INTEGER PRIMARY KEY,
                    SeriesId INTEGER NOT NULL,
                    EpisodeFileId INTEGER NOT NULL,
                    SeasonNumber INTEGER NOT NULL,
                    EpisodeNumber INTEGER NOT NULL
                );
                """,
            )
            connection.execute(
                "INSERT INTO Series (Id, Title, Path, Added) VALUES (1, 'Example Show', ?, '2024-07-01 00:00:00Z')",
                (str(series_dir),),
            )
            connection.execute(
                "INSERT INTO EpisodeFiles (Id, SeriesId, RelativePath) VALUES (11, 1, ?)",
                ("Season 00/Example.Show.S00E01.mkv",),
            )
            connection.execute(
                "INSERT INTO EpisodeFiles (Id, SeriesId, RelativePath) VALUES (12, 1, ?)",
                ("Season 01/Example.Show.S01E01.mkv",),
            )
            connection.execute(
                "INSERT INTO Episodes (Id, SeriesId, EpisodeFileId, SeasonNumber, EpisodeNumber) VALUES (1, 1, 11, 0, 1)"
            )
            connection.execute(
                "INSERT INTO Episodes (Id, SeriesId, EpisodeFileId, SeasonNumber, EpisodeNumber) VALUES (2, 1, 12, 1, 1)"
            )
            connection.commit()
            connection.close()

            buffer = io.StringIO()
            timestamp_map = {
                special_path: _resolved_timestamp("2010-01-01T00:00:00+00:00", "modified"),
                episode_path: _resolved_timestamp("2015-01-01T00:00:00+00:00", "modified"),
            }
            buffer = io.StringIO()
            with patch(
                "ffinspector.arrsync._effective_timestamp_for_path",
                side_effect=lambda path: timestamp_map.get(path),
            ):
                with redirect_stdout(buffer):
                    exit_code = main(["arr-date-sync", "sonarr", str(db_path), "--apply"])

            self.assertEqual(exit_code, 0)
            rendered = buffer.getvalue()
            self.assertIn("APPLY sonarr first-media", rendered)
            self.assertIn("first episode S01E01", rendered)
            self.assertIn("Result   : updated", rendered)

            connection = sqlite3.connect(db_path)
            added = connection.execute("SELECT Added FROM Series WHERE Id = 1").fetchone()[0]
            connection.close()
            self.assertEqual(added, "2015-01-01 00:00:00Z")

    def test_radarr_oldest_media_ignores_non_video_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "radarr.db"
            movie_dir = root / "Movies" / "Example Movie (1999)"
            movie_dir.mkdir(parents=True)
            movie_path = movie_dir / "Example.Movie.1999.mkv"
            poster_path = movie_dir / "poster.jpg"
            movie_path.write_text("", encoding="utf-8")
            poster_path.write_text("", encoding="utf-8")

            _create_basic_radarr_db(db_path, movie_dir, movie_path, title="Example Movie")

            timestamp_map = {
                movie_path: _resolved_timestamp("2020-01-02T03:04:05+00:00", "modified"),
                poster_path: _resolved_timestamp("2010-01-02T03:04:05+00:00", "modified"),
            }
            buffer = io.StringIO()
            with patch(
                "ffinspector.arrsync._effective_timestamp_for_path",
                side_effect=lambda path: timestamp_map.get(path),
            ):
                with redirect_stdout(buffer):
                    exit_code = main(["arr-date-sync", "radarr", str(db_path), "--mode", "oldest-media", "--apply"])

            self.assertEqual(exit_code, 0)
            connection = sqlite3.connect(db_path)
            added = connection.execute("SELECT Added FROM Movies WHERE Id = 1").fetchone()[0]
            connection.close()
            self.assertEqual(added, "2020-01-02 03:04:05Z")

    def test_radarr_oldest_any_can_use_non_media_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "radarr.db"
            movie_dir = root / "Movies" / "Example Movie (1999)"
            movie_dir.mkdir(parents=True)
            movie_path = movie_dir / "Example.Movie.1999.mkv"
            nfo_path = movie_dir / "movie.nfo"
            movie_path.write_text("", encoding="utf-8")
            nfo_path.write_text("", encoding="utf-8")

            _create_basic_radarr_db(db_path, movie_dir, movie_path, title="Example Movie")

            timestamp_map = {
                movie_path: _resolved_timestamp("2020-01-02T03:04:05+00:00", "modified"),
                nfo_path: _resolved_timestamp("2010-01-02T03:04:05+00:00", "modified"),
            }
            buffer = io.StringIO()
            with patch(
                "ffinspector.arrsync._effective_timestamp_for_path",
                side_effect=lambda path: timestamp_map.get(path),
            ):
                with redirect_stdout(buffer):
                    exit_code = main(["arr-date-sync", "radarr", str(db_path), "--mode", "oldest-any", "--apply"])

            self.assertEqual(exit_code, 0)
            connection = sqlite3.connect(db_path)
            added = connection.execute("SELECT Added FROM Movies WHERE Id = 1").fetchone()[0]
            connection.close()
            self.assertEqual(added, "2010-01-02 03:04:05Z")


def _create_basic_radarr_db(db_path: Path, movie_dir: Path, movie_path: Path, title: str) -> None:
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE Movies (
            Id INTEGER PRIMARY KEY,
            Path TEXT NOT NULL,
            Added TEXT,
            MovieFileId INTEGER,
            MovieMetadataId INTEGER
        );
        CREATE TABLE MovieFiles (
            Id INTEGER PRIMARY KEY,
            MovieId INTEGER,
            RelativePath TEXT,
            OriginalFilePath TEXT
        );
        CREATE TABLE MovieMetadata (
            Id INTEGER PRIMARY KEY,
            Title TEXT NOT NULL
        );
        """
    )
    connection.execute("INSERT INTO MovieMetadata (Id, Title) VALUES (1, ?)", (title,))
    connection.execute(
        "INSERT INTO MovieFiles (Id, MovieId, RelativePath) VALUES (7, 1, ?)",
        (movie_path.name,),
    )
    connection.execute(
        "INSERT INTO Movies (Id, Path, Added, MovieFileId, MovieMetadataId) VALUES (1, ?, '2025-05-01 00:00:00Z', 7, 1)",
        (str(movie_dir),),
    )
    connection.commit()
    connection.close()


def _resolved_timestamp(value: str, basis: str):
    from ffinspector.arrsync import _ResolvedTimestamp

    return _ResolvedTimestamp(datetime.fromisoformat(value), basis)


if __name__ == "__main__":
    unittest.main()
