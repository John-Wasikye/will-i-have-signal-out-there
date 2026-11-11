"""Tests for the Ookla tile loader (C13 part 1, contract ookla_open_data).

Ookla keeps one worldwide Parquet file per quarter in a public bucket. The loader finds the newest
published quarter with a header request, downloads it to a work folder, keeps only a manifest in
the raw bucket, and turns the tiles inside Arizona's box into ``ookla_tile`` rows with an H3
resolution 8 cell. No test calls Ookla or AWS: the file is a tiny real Parquet file.
"""

import hashlib
import io
import json
import urllib.error
from datetime import UTC, date, datetime
from pathlib import Path

import h3
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from ookla_tiles import (
    MANIFEST_PREFIX,
    OoklaNotPublished,
    Quarter,
    WrongOoklaFile,
    arizona_tile_rows,
    download_quarter,
    newest_published_quarter,
    quarter_prefix,
    recent_quarters,
    store_quarter_manifest,
)
from raw_store import FetchRefused
from test_signal_nightly import FakeS3

NOW = datetime(2026, 11, 12, 10, 3, tzinfo=UTC)
Q3 = Quarter(2026, 3)
Q3_URL = (
    "https://ookla-open-data.s3.us-west-2.amazonaws.com/parquet/performance/type=mobile/"
    "year=2026/quarter=3/2026-07-01_performance_mobile_tiles.parquet"
)

GRAND_CANYON = {"quadkey": "0230102033332101", "tile_x": -112.1, "tile_y": 36.06}
PHOENIX = {"quadkey": "0230123012301230", "tile_x": -112.07, "tile_y": 33.45}
ON_EAST_EDGE = {"quadkey": "0230133300000000", "tile_x": -109.04, "tile_y": 35.0}
LAS_VEGAS = {"quadkey": "0230102200000000", "tile_x": -115.14, "tile_y": 36.17}
DENVER = {"quadkey": "0231010000000000", "tile_x": -104.99, "tile_y": 39.74}


def _source_table(tiles, drop=()):
    rows = [
        tile
        | {
            "tile": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            "avg_d_kbps": 10_000 + n,
            "avg_u_kbps": 2_000 + n,
            "avg_lat_ms": 40 + n,
            "avg_lat_down_ms": 300.0,
            "avg_lat_up_ms": 200.0,
            "tests": 3 + n,
            "devices": 2 + n,
        }
        for n, tile in enumerate(tiles)
    ]
    table = pa.Table.from_pylist(rows)
    return table.drop_columns(list(drop)) if drop else table


def _parquet_bytes(table) -> bytes:
    sink = io.BytesIO()
    pq.write_table(table, sink)
    return sink.getvalue()


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.status = status
        self._body = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOokla:
    """Answers header and download requests for the quarters it holds, 404 for the others."""

    def __init__(self, files: dict[str, bytes], error_status: int = 404):
        self.files = files
        self.error_status = error_status
        self.requests: list[tuple[str, str]] = []

    def __call__(self, request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        method = "GET" if isinstance(request, str) else request.get_method()
        self.requests.append((method, url))
        if url not in self.files:
            raise urllib.error.HTTPError(url, self.error_status, "Not Found", {}, None)
        return FakeResponse(b"" if method == "HEAD" else self.files[url])


def test_a_quarter_names_itself_and_its_file_as_the_contract_does():
    assert Q3.label == "2026-Q3"
    assert Q3.url == Q3_URL
    q4_file = "year=2026/quarter=4/2026-10-01_performance_mobile_tiles.parquet"
    assert Quarter(2026, 4).url.endswith(q4_file)


@pytest.mark.parametrize(
    ("run_date", "expected"),
    [
        (date(2026, 11, 12), [Quarter(2026, 3), Quarter(2026, 2)]),
        (date(2026, 10, 1), [Quarter(2026, 3), Quarter(2026, 2)]),
        (date(2026, 9, 30), [Quarter(2026, 2), Quarter(2026, 1)]),
        (date(2027, 1, 5), [Quarter(2026, 4), Quarter(2026, 3)]),
        (date(2027, 4, 2), [Quarter(2027, 1), Quarter(2026, 4)]),
    ],
)
def test_the_recent_quarters_are_the_two_that_ended_before_the_run(run_date, expected):
    assert recent_quarters(run_date) == expected


def test_the_newest_published_quarter_is_found_with_header_requests_only():
    ookla = FakeOokla({Q3_URL: b"file"})

    assert newest_published_quarter(date(2026, 11, 12), opener=ookla) == Q3
    assert ookla.requests == [("HEAD", Q3_URL)]


def test_a_quarter_not_published_yet_falls_back_to_the_one_before():
    """Ookla publishes a quarter some weeks after it ends; until then the previous one is newest."""
    ookla = FakeOokla({Quarter(2026, 2).url: b"file"})

    assert newest_published_quarter(date(2026, 10, 3), opener=ookla) == Quarter(2026, 2)


def test_no_published_quarter_stops_the_step():
    with pytest.raises(OoklaNotPublished):
        newest_published_quarter(date(2026, 11, 12), opener=FakeOokla({}))


def test_an_error_other_than_not_found_is_not_taken_as_unpublished():
    """A 403 or 500 means something is wrong with the request, not that the file is missing."""
    with pytest.raises(urllib.error.HTTPError):
        newest_published_quarter(date(2026, 11, 12), opener=FakeOokla({}, error_status=403))


def test_the_download_goes_to_the_work_folder_with_a_manifest(tmp_path):
    body = _parquet_bytes(_source_table([GRAND_CANYON]))

    path, manifest = download_quarter(Q3, tmp_path, now_utc=NOW, opener=FakeOokla({Q3_URL: body}))

    assert path.parent == tmp_path
    assert path.read_bytes() == body
    assert manifest == {
        "quarter": "2026-Q3",
        "source_url": Q3_URL,
        "fetched_at_utc": "2026-11-12T10:03:00Z",
        "size_bytes": len(body),
        "content_sha256": hashlib.sha256(body).hexdigest(),
    }


def test_an_empty_download_is_refused(tmp_path):
    with pytest.raises(FetchRefused):
        download_quarter(Q3, tmp_path, now_utc=NOW, opener=FakeOokla({Q3_URL: b""}))


def _manifest(body: bytes) -> dict:
    return {
        "quarter": "2026-Q3",
        "source_url": Q3_URL,
        "fetched_at_utc": "2026-11-12T10:03:00Z",
        "size_bytes": len(body),
        "content_sha256": hashlib.sha256(body).hexdigest(),
    }


def _kept(tmp_path: Path, table) -> tuple[Path, dict]:
    body = _parquet_bytes(table)
    path = tmp_path / "tiles.parquet"
    path.write_bytes(body)
    return path, _manifest(body)


def test_only_tiles_centred_inside_arizona_are_kept(tmp_path):
    path, manifest = _kept(
        tmp_path, _source_table([GRAND_CANYON, LAS_VEGAS, PHOENIX, DENVER, ON_EAST_EDGE])
    )

    rows = arizona_tile_rows(path, manifest)

    assert [row["tile_key"] for row in rows] == [
        GRAND_CANYON["quadkey"],
        PHOENIX["quadkey"],
        ON_EAST_EDGE["quadkey"],
    ]


def test_each_row_has_the_contract_columns_and_the_h3_cell_of_the_tile_centre(tmp_path):
    path, manifest = _kept(tmp_path, _source_table([GRAND_CANYON]))

    (row,) = arizona_tile_rows(path, manifest)

    assert row == {
        "quarter": "2026-Q3",
        "tile_key": GRAND_CANYON["quadkey"],
        "h3_cell_res8": h3.latlng_to_cell(36.06, -112.1, 8),
        "test_count": 3,
        "device_count": 2,
        "avg_download_kbps": 10_000,
        "avg_upload_kbps": 2_000,
        "avg_latency_ms": 40,
        "source_url": Q3_URL,
        "fetched_at_utc": datetime(2026, 11, 12, 10, 3, tzinfo=UTC),
        "content_sha256": manifest["content_sha256"],
    }


def test_the_rows_match_the_contract(tmp_path):
    contract = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
    from lake_write import contract_columns

    path, manifest = _kept(tmp_path, _source_table([GRAND_CANYON]))
    columns = contract_columns(contract / "ookla_open_data.yaml", "ookla_tile")
    names = [column.name for column in columns]

    assert list(arizona_tile_rows(path, manifest)[0]) == names


def test_a_file_without_a_field_the_contract_needs_is_refused(tmp_path):
    path, manifest = _kept(tmp_path, _source_table([GRAND_CANYON], drop=["devices"]))

    with pytest.raises(WrongOoklaFile, match="devices"):
        arizona_tile_rows(path, manifest)


def test_the_manifest_is_kept_under_its_quarter_and_never_replaced():
    s3 = FakeS3()
    manifest = _manifest(b"file")

    key = store_quarter_manifest(s3, "raw", manifest)

    assert quarter_prefix(Q3) == f"{MANIFEST_PREFIX}/quarter=2026-Q3/"
    assert key == f"{MANIFEST_PREFIX}/quarter=2026-Q3/fetched_at=2026-11-12T10:03:00Z/manifest.json"
    assert json.loads(s3.objects[key]) == manifest
    with pytest.raises(RuntimeError, match="PreconditionFailed"):
        store_quarter_manifest(s3, "raw", manifest)
