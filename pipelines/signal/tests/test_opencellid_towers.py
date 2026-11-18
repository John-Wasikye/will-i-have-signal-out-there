"""Tests for reading OpenCelliD cell exports (C13 part 3, contract opencellid_towers).

OpenCelliD's country exports are gzip CSV files with the columns radio, mcc, net, area, cell,
unit, lon, lat, range, samples, changeable, created, updated and averageSignal. John downloads
them by hand, because the download needs his personal API token, so the token must never reach a
manifest or the lake. No test calls OpenCelliD or AWS.
"""

import gzip
from datetime import UTC, datetime

import h3
import pytest
from opencellid_towers import (
    WrongOpenCellidFile,
    arizona_cell_rows,
    check_manifest,
    read_cell_lines,
)

HEADER = (
    "radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal"
)
# Estimated cell locations: two in Arizona, one in Colorado.
GRAND_CANYON = "LTE,310,260,12345,678901,77,-112.1129,36.0544,1500,12,1,1609459200,1762300800,0"
PHOENIX = "NR,311,480,2001,90000000001,,-112.074,33.448,800,40,1,1672531200,1762387200,0"
DENVER = "LTE,310,410,7033,17811,12,-104.99,39.74,2000,5,1,1609459200,1762300800,0"
MANIFEST = {
    "source_url": "https://opencellid.org/downloads.php#310.csv.gz",
    "mcc": 310,
    "fetched_at_utc": "2026-11-18T09:00:00Z",
    "size_bytes": 123,
    "content_sha256": "a" * 64,
    "raw_key": "signal/opencellid/mcc=310/fetched_at=2026-11-18T09:00:00Z/310.csv.gz",
}


def test_only_cells_inside_arizonas_box_are_kept():
    rows = arizona_cell_rows([GRAND_CANYON, DENVER, PHOENIX], MANIFEST)

    assert [row["tower_id"] for row in rows] == [
        "LTE-310-260-12345-678901",
        "NR-311-480-2001-90000000001",
    ]


def test_a_row_carries_the_source_fields_under_the_contract_names():
    (row,) = arizona_cell_rows([GRAND_CANYON], MANIFEST)

    assert row == {
        "tower_id": "LTE-310-260-12345-678901",
        "radio": "LTE",
        "mcc": 310,
        "net": 260,
        "area": 12345,
        "cell": 678901,
        "lon": -112.1129,
        "lat": 36.0544,
        "range_m": 1500,
        "samples": 12,
        "created_utc": datetime(2021, 1, 1, tzinfo=UTC),
        "updated_utc": datetime(2025, 11, 5, tzinfo=UTC),
        "h3_cell_res9": h3.latlng_to_cell(36.0544, -112.1129, 9),
        "source_url": MANIFEST["source_url"],
        "fetched_at_utc": datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
        "content_sha256": MANIFEST["content_sha256"],
    }


def test_a_header_line_is_skipped():
    rows = arizona_cell_rows([HEADER, GRAND_CANYON], MANIFEST)

    assert [row["tower_id"] for row in rows] == ["LTE-310-260-12345-678901"]


def test_a_line_with_the_wrong_number_of_columns_stops_the_read():
    with pytest.raises(WrongOpenCellidFile, match="14 columns"):
        arizona_cell_rows([GRAND_CANYON, "LTE,310,260,1,2,,-112.1,36.0"], MANIFEST)


def test_the_same_cell_twice_stops_the_read():
    with pytest.raises(WrongOpenCellidFile, match="LTE-310-260-12345-678901"):
        arizona_cell_rows([GRAND_CANYON, GRAND_CANYON], MANIFEST)


def test_a_manifest_with_the_token_in_its_url_is_refused():
    """The download link carries John's API token, which must never be stored."""
    manifest = MANIFEST | {"source_url": "https://opencellid.org/ocid/downloads?token=pk.fake"}

    with pytest.raises(WrongOpenCellidFile, match="token"):
        check_manifest(manifest)


def test_a_manifest_without_a_query_passes_the_check():
    check_manifest(MANIFEST)


def test_the_rows_are_not_read_from_a_manifest_with_the_token():
    manifest = MANIFEST | {"source_url": "https://opencellid.org/ocid/downloads?token=pk.fake"}

    with pytest.raises(WrongOpenCellidFile, match="token"):
        arizona_cell_rows([GRAND_CANYON], manifest)


def test_a_gzip_export_is_read_as_text_lines():
    body = gzip.compress(f"{HEADER}\n{GRAND_CANYON}\n{DENVER}\n".encode())

    assert read_cell_lines(body) == [HEADER, GRAND_CANYON, DENVER]
