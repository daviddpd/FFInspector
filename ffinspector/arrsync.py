from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Iterable, Sequence, TextIO


TIMESTAMP_PRECEDENCE = "birth -> modified -> access"
SELECTION_MODES = {"first-media", "oldest-media", "oldest-any"}


class ArrSyncError(ValueError):
    """Raised when an arr database cannot be processed safely."""


@dataclass
class FileTimestamp:
    path: Path
    timestamp: datetime
    basis: str
    label: str


@dataclass
class SyncPlan:
    item_id: int
    item_type: str
    title: str
    current_added: object
    proposed: FileTimestamp | None
    reason: str | None = None


@dataclass(frozen=True)
class RootMap:
    source: str
    target: Path


def run_added_date_sync(
    db_path: Path,
    app: str,
    mode: str,
    apply: bool,
    media_extensions: Sequence[str],
    root_maps: Sequence[RootMap],
    out: TextIO,
) -> int:
    normalized_app = app.strip().lower()
    normalized_mode = mode.strip().lower()
    if normalized_app not in {"radarr", "sonarr"}:
        raise ArrSyncError(f"Unsupported app '{app}'. Expected 'radarr' or 'sonarr'.")
    if normalized_mode not in SELECTION_MODES:
        raise ArrSyncError(f"Unsupported mode '{mode}'.")
    if not db_path.exists():
        raise ArrSyncError(f"Database not found: {db_path}")

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        adapter = _build_adapter(connection, normalized_app, media_extensions, root_maps)
        plans = adapter.build_plans(normalized_mode)
        if not plans:
            out.write("No matching movies or series were found in the database.\n")
            return 1

        action = "APPLY" if apply else "DRY RUN"
        out.write(f"{action} {normalized_app} {normalized_mode} ({TIMESTAMP_PRECEDENCE})\n")
        for root_map in root_maps:
            out.write(f"  map-root: {root_map.source} -> {root_map.target}\n")

        for index, plan in enumerate(plans, start=1):
            current_display = _display_db_value(plan.current_added)
            out.write(f"[{index}/{len(plans)}] {plan.item_type}: {plan.title}\n")
            out.write(f"  Current DB: {current_display}\n")

            if plan.proposed is None:
                out.write(f"  Proposed : skipped ({plan.reason or 'no candidate file found'})\n")
                continue

            encoded = adapter.encode_datetime(plan.current_added, plan.proposed.timestamp)
            proposed_display = _display_datetime(plan.proposed.timestamp)
            out.write(
                f"  Proposed : {proposed_display} ({plan.proposed.label}, {plan.proposed.basis}, {plan.proposed.path})\n"
            )

            if not apply:
                continue

            if _values_match(plan.current_added, encoded):
                out.write("  Result   : unchanged\n")
                continue

            adapter.update_added(plan.item_id, encoded)
            connection.commit()
            out.write("  Result   : updated\n")

        return 0
    finally:
        connection.close()


def parse_root_maps(values: Sequence[str]) -> list[RootMap]:
    parsed: list[RootMap] = []
    for value in values:
        source_text, separator, target_text = str(value).partition("=")
        if not separator:
            raise ArrSyncError(f"Invalid --map-root '{value}'. Expected SOURCE=TARGET.")
        source = _normalize_root_source(source_text)
        if not target_text.strip():
            raise ArrSyncError(f"Invalid --map-root '{value}'. Target path cannot be empty.")
        target = Path(target_text.strip()).expanduser()
        parsed.append(RootMap(source=source, target=target))
    parsed.sort(key=lambda item: len(item.source), reverse=True)
    return parsed


class _BaseArrAdapter:
    item_type: str
    table_name: str

    def __init__(
        self,
        connection: sqlite3.Connection,
        media_extensions: Sequence[str],
        root_maps: Sequence[RootMap],
    ) -> None:
        self.connection = connection
        self.media_extensions = {extension.lower() for extension in media_extensions}
        self.root_maps = list(root_maps)
        self._sample_added_value = self._load_added_sample()

    def build_plans(self, mode: str) -> list[SyncPlan]:
        plans = []
        for row in self._load_rows():
            title = row["title"] or row["folder_path"] or f"{self.item_type.title()} {row['item_id']}"
            proposed = self._select_timestamp(row, mode)
            plans.append(
                SyncPlan(
                    item_id=row["item_id"],
                    item_type=self.item_type,
                    title=str(title),
                    current_added=row["current_added"],
                    proposed=proposed,
                    reason=None if proposed else self._missing_reason(row, mode),
                )
            )
        return plans

    def encode_datetime(self, current_value: object, value: datetime) -> object:
        sample = current_value if current_value not in {None, ""} else self._sample_added_value
        return _encode_db_datetime(value, sample)

    def update_added(self, item_id: int, encoded: object) -> None:
        self.connection.execute(f'UPDATE "{self.table_name}" SET Added = ? WHERE Id = ?', (encoded, item_id))

    def _load_added_sample(self) -> object:
        row = self.connection.execute(
            f'SELECT Added FROM "{self.table_name}" WHERE Added IS NOT NULL AND Added != \'\' LIMIT 1'
        ).fetchone()
        return row[0] if row else None

    def _load_rows(self) -> list[sqlite3.Row]:
        raise NotImplementedError

    def _select_timestamp(self, row: sqlite3.Row, mode: str) -> FileTimestamp | None:
        raise NotImplementedError

    def _missing_reason(self, row: sqlite3.Row, mode: str) -> str:
        del row
        if mode == "first-media":
            return "no primary media file found on disk"
        if mode == "oldest-media":
            return "no media files found on disk"
        return "no files found on disk"

    def _scan_candidates(self, root: str | None, include_all_files: bool) -> list[Path]:
        candidate = _apply_root_maps(root, self.root_maps)
        if candidate is None:
            return []
        if not candidate.exists():
            return []
        if candidate.is_file():
            if include_all_files or candidate.suffix.lower() in self.media_extensions:
                return [candidate]
            return []

        matches = []
        for path in candidate.rglob("*"):
            if not path.is_file():
                continue
            if include_all_files or path.suffix.lower() in self.media_extensions:
                matches.append(path)
        return matches

    def _oldest_from_paths(self, paths: Iterable[Path], label: str) -> FileTimestamp | None:
        chosen: FileTimestamp | None = None
        for path in paths:
            timestamp = _effective_timestamp_for_path(path)
            if timestamp is None:
                continue
            if chosen is None or timestamp.timestamp < chosen.timestamp:
                chosen = FileTimestamp(path=path, timestamp=timestamp.timestamp, basis=timestamp.basis, label=label)
        return chosen


class _RadarrAdapter(_BaseArrAdapter):
    item_type = "movie"
    table_name = "Movies"

    def __init__(
        self,
        connection: sqlite3.Connection,
        media_extensions: Sequence[str],
        root_maps: Sequence[RootMap],
    ) -> None:
        _require_columns(connection, "Movies", {"Id", "Path", "Added"})
        super().__init__(connection, media_extensions, root_maps)
        self._movie_columns = _table_columns(connection, "Movies")
        self._movie_file_columns = _table_columns(connection, "MovieFiles")
        self._movie_metadata_columns = _table_columns(connection, "MovieMetadata")

    def _load_rows(self) -> list[sqlite3.Row]:
        joins = []
        title_expr = "m.Path"
        if "Title" in self._movie_columns:
            title_expr = "m.Title"
        elif "MovieMetadataId" in self._movie_columns and "Title" in self._movie_metadata_columns:
            joins.append("LEFT JOIN MovieMetadata mm ON mm.Id = m.MovieMetadataId")
            title_expr = "mm.Title"

        media_relative_expr = "NULL"
        media_original_expr = "NULL"
        if "MovieFileId" in self._movie_columns and "Id" in self._movie_file_columns:
            if "RelativePath" in self._movie_file_columns:
                media_relative_expr = "(SELECT RelativePath FROM MovieFiles mf WHERE mf.Id = m.MovieFileId LIMIT 1)"
            if "OriginalFilePath" in self._movie_file_columns:
                media_original_expr = "(SELECT OriginalFilePath FROM MovieFiles mf WHERE mf.Id = m.MovieFileId LIMIT 1)"
        elif "MovieId" in self._movie_file_columns:
            if "RelativePath" in self._movie_file_columns:
                media_relative_expr = "(SELECT RelativePath FROM MovieFiles mf WHERE mf.MovieId = m.Id ORDER BY mf.Id LIMIT 1)"
            if "OriginalFilePath" in self._movie_file_columns:
                media_original_expr = "(SELECT OriginalFilePath FROM MovieFiles mf WHERE mf.MovieId = m.Id ORDER BY mf.Id LIMIT 1)"

        sql = "\n".join(
            [
                "SELECT",
                "  m.Id AS item_id,",
                f"  COALESCE({title_expr}, m.Path, 'Movie ' || m.Id) AS title,",
                "  m.Path AS folder_path,",
                "  m.Added AS current_added,",
                f"  {media_relative_expr} AS media_relative_path,",
                f"  {media_original_expr} AS media_original_path",
                "FROM Movies m",
                *joins,
                f"ORDER BY lower(COALESCE({title_expr}, m.Path, ''))",
            ]
        )
        return list(self.connection.execute(sql))

    def _select_timestamp(self, row: sqlite3.Row, mode: str) -> FileTimestamp | None:
        folder_path = row["folder_path"]
        media_path = _resolve_arr_file_path(
            folder_path,
            row["media_relative_path"],
            row["media_original_path"],
            self.root_maps,
        )
        if mode == "first-media":
            if media_path:
                resolved = _effective_timestamp_for_path(media_path)
                if resolved is not None:
                    return FileTimestamp(
                        path=media_path,
                        timestamp=resolved.timestamp,
                        basis=resolved.basis,
                        label="movie file",
                    )
            return self._oldest_from_paths(self._scan_candidates(folder_path, include_all_files=False), "movie folder media")

        if mode == "oldest-media":
            return self._oldest_from_paths(self._scan_candidates(folder_path, include_all_files=False), "oldest media")

        return self._oldest_from_paths(self._scan_candidates(folder_path, include_all_files=True), "oldest file")


class _SonarrAdapter(_BaseArrAdapter):
    item_type = "series"
    table_name = "Series"

    def __init__(
        self,
        connection: sqlite3.Connection,
        media_extensions: Sequence[str],
        root_maps: Sequence[RootMap],
    ) -> None:
        _require_columns(connection, "Series", {"Id", "Path", "Added"})
        _require_columns(connection, "Episodes", {"SeriesId", "EpisodeFileId", "SeasonNumber", "EpisodeNumber"})
        _require_columns(connection, "EpisodeFiles", {"Id"})
        super().__init__(connection, media_extensions, root_maps)
        self._series_columns = _table_columns(connection, "Series")
        self._episode_file_columns = _table_columns(connection, "EpisodeFiles")

    def _load_rows(self) -> list[sqlite3.Row]:
        title_expr = "s.Title" if "Title" in self._series_columns else "s.Path"
        sql = "\n".join(
            [
                "SELECT",
                "  s.Id AS item_id,",
                f"  COALESCE({title_expr}, s.Path, 'Series ' || s.Id) AS title,",
                "  s.Path AS folder_path,",
                "  s.Added AS current_added",
                "FROM Series s",
                f"ORDER BY lower(COALESCE({title_expr}, s.Path, ''))",
            ]
        )
        return list(self.connection.execute(sql))

    def _select_timestamp(self, row: sqlite3.Row, mode: str) -> FileTimestamp | None:
        folder_path = row["folder_path"]
        if mode == "first-media":
            relative_expr = "ef.RelativePath" if "RelativePath" in self._episode_file_columns else "NULL"
            original_expr = "ef.OriginalFilePath" if "OriginalFilePath" in self._episode_file_columns else "NULL"
            episode_row = self.connection.execute(
                "\n".join(
                    [
                        "SELECT",
                        f"  {relative_expr} AS media_relative_path,",
                        f"  {original_expr} AS media_original_path,",
                        "  e.SeasonNumber AS season_number,",
                        "  e.EpisodeNumber AS episode_number",
                        "FROM Episodes e",
                        "JOIN EpisodeFiles ef ON ef.Id = e.EpisodeFileId",
                        "WHERE e.SeriesId = ? AND e.EpisodeFileId > 0",
                        "ORDER BY CASE",
                        "  WHEN e.SeasonNumber = 1 AND e.EpisodeNumber = 1 THEN 0",
                        "  ELSE 1",
                        "END, e.SeasonNumber, e.EpisodeNumber, e.Id",
                        "LIMIT 1",
                    ]
                ),
                (row["item_id"],),
            ).fetchone()
            if episode_row:
                media_path = _resolve_arr_file_path(
                    folder_path,
                    episode_row["media_relative_path"],
                    episode_row["media_original_path"],
                    self.root_maps,
                )
                resolved = _effective_timestamp_for_path(media_path) if media_path is not None else None
                if resolved is not None:
                    label = (
                        f"first episode S{episode_row['season_number']:02d}E{episode_row['episode_number']:02d}"
                    )
                    return FileTimestamp(
                        path=media_path,
                        timestamp=resolved.timestamp,
                        basis=resolved.basis,
                        label=label,
                    )
            return None

        if mode == "oldest-media":
            return self._oldest_from_paths(self._scan_candidates(folder_path, include_all_files=False), "oldest media")

        return self._oldest_from_paths(self._scan_candidates(folder_path, include_all_files=True), "oldest file")


@dataclass
class _ResolvedTimestamp:
    timestamp: datetime
    basis: str


def _build_adapter(
    connection: sqlite3.Connection,
    app: str,
    media_extensions: Sequence[str],
    root_maps: Sequence[RootMap],
) -> _BaseArrAdapter:
    if app == "radarr":
        return _RadarrAdapter(connection, media_extensions, root_maps)
    return _SonarrAdapter(connection, media_extensions, root_maps)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def _require_columns(connection: sqlite3.Connection, table_name: str, columns: set[str]) -> None:
    present = _table_columns(connection, table_name)
    missing = sorted(column for column in columns if column not in present)
    if missing:
        raise ArrSyncError(f"Database table '{table_name}' is missing columns: {', '.join(missing)}")


def _effective_timestamp_for_path(path: Path) -> _ResolvedTimestamp | None:
    try:
        stat_result = path.stat()
    except OSError:
        return None

    birth = _safe_datetime_from_timestamp(getattr(stat_result, "st_birthtime", None))
    if birth is not None:
        return _ResolvedTimestamp(birth, "birth")

    modified = _safe_datetime_from_timestamp(getattr(stat_result, "st_mtime", None))
    if modified is not None:
        return _ResolvedTimestamp(modified, "modified")

    accessed = _safe_datetime_from_timestamp(getattr(stat_result, "st_atime", None))
    if accessed is not None:
        return _ResolvedTimestamp(accessed, "access")
    return None


def _safe_datetime_from_timestamp(value: object) -> datetime | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    try:
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _normalize_root_source(value: str) -> str:
    source = value.strip()
    if not source:
        raise ArrSyncError("Invalid --map-root. Source path cannot be empty.")
    stripped = source.rstrip("/")
    return stripped or "/"


def _apply_root_maps(value: str | None, root_maps: Sequence[RootMap]) -> Path | None:
    if not value:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    for root_map in root_maps:
        source = root_map.source
        if normalized == source:
            return root_map.target
        if source != "/" and normalized.startswith(source + "/"):
            suffix = normalized[len(source) + 1 :]
            return root_map.target / Path(suffix)
        if source == "/" and normalized.startswith("/"):
            suffix = normalized[1:]
            return root_map.target / Path(suffix) if suffix else root_map.target

    return Path(normalized)


def _resolve_arr_file_path(
    folder_path: str | None,
    relative_path: str | None,
    original_path: str | None,
    root_maps: Sequence[RootMap],
) -> Path | None:
    mapped_original = _apply_root_maps(original_path, root_maps)
    if mapped_original is not None and mapped_original.exists():
        return mapped_original

    mapped_folder = _apply_root_maps(folder_path, root_maps)
    if mapped_folder is not None and relative_path:
        candidate = mapped_folder / Path(relative_path)
        if candidate.exists():
            return candidate

    if mapped_original is not None:
        return mapped_original
    if mapped_folder is not None and relative_path:
        return mapped_folder / Path(relative_path)
    return None


def _parse_db_datetime(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _display_db_value(value: object) -> str:
    parsed = _parse_db_datetime(value)
    if parsed is not None:
        return _display_datetime(parsed)
    if value in {None, ""}:
        return "(unset)"
    return str(value)


def _display_datetime(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    if utc_value.microsecond:
        return utc_value.strftime("%Y-%m-%d %H:%M:%S.%f").rstrip("0").rstrip(".") + "Z"
    return utc_value.strftime("%Y-%m-%d %H:%M:%SZ")


def _encode_db_datetime(value: datetime, sample: object) -> object:
    utc_value = value.astimezone(timezone.utc)
    if isinstance(sample, int):
        return int(utc_value.timestamp())
    if isinstance(sample, float):
        return float(utc_value.timestamp())
    if isinstance(sample, bytes):
        sample = sample.decode("utf-8", errors="replace")
    if isinstance(sample, str) and sample.strip():
        return _format_like_sample(utc_value, sample)
    return _display_datetime(utc_value)


def _format_like_sample(value: datetime, sample: str) -> str:
    sample_text = sample.strip()
    separator = "T" if "T" in sample_text else " "
    fraction_match = re.search(r"\.(\d+)", sample_text)
    offset_match = re.search(r"([+-]\d{2}:\d{2})$", sample_text)
    has_z_suffix = sample_text.endswith("Z")

    rendered = value.strftime(f"%Y-%m-%d{separator}%H:%M:%S")
    if fraction_match:
        digits = len(fraction_match.group(1))
        rendered += f".{value.microsecond:06d}"[: digits + 1]
    if has_z_suffix:
        return rendered + "Z"
    if offset_match:
        return rendered + "+00:00"
    return rendered


def _values_match(current_value: object, encoded_value: object) -> bool:
    if current_value == encoded_value:
        return True
    current_dt = _parse_db_datetime(current_value)
    encoded_dt = _parse_db_datetime(encoded_value)
    if current_dt is not None and encoded_dt is not None:
        return current_dt == encoded_dt
    return False
