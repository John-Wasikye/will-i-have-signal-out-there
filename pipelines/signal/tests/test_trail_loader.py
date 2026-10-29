"""Tests for the trail loader (C3): pull Grand Canyon's trails from the NPS service, keep the raw
pages, pick the Phase A trails by exact name, and place a point every 50 meters.

No test calls the NPS service or AWS. Distances use the haversine formula on a sphere of the
Earth's mean radius; that is accurate to a fraction of a percent at this scale.
"""

import json
import math
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from contract_diff import BreakingSchemaChange
from lake_write import contract_columns, spark_schema
from trail_loader import (
    NPS_TRAILS_QUERY_URL,
    PHASE_A_TRAILS,
    TrailLine,
    TrailPoint,
    distance_m,
    fetch_trail_pages,
    load_trail_tables,
    parse_trail_geojson,
    sample_points_along_line,
    select_trails,
    store_trail_pages,
    trail_id_for,
    trail_line_rows,
    trail_point_rows,
    trail_query_url,
)

CONTRACT = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts" / "nps_trails.yaml"
POINT_CONTRACT = CONTRACT.with_name("trail_point.yaml")
FETCHED_AT = datetime(2026, 10, 28, 4, 30, tzinfo=UTC)

# About 50 m of longitude at Grand Canyon's latitude.
STEP = 50 / (111_195 * math.cos(math.radians(36.1)))


def _feature(object_id, name, coordinates, kind="LineString", unit="GRCA"):
    return {
        "type": "Feature",
        "id": object_id,
        "geometry": {"type": kind, "coordinates": coordinates},
        "properties": {"OBJECTID": object_id, "TRLNAME": name, "UNITCODE": unit},
    }


def _page(features, more=False):
    page = {"type": "FeatureCollection", "features": features}
    if more:
        page["exceededTransferLimit"] = True
    return json.dumps(page).encode()


TRAILS = [
    _feature(1, "Bright Angel", [[-112.144, 36.057], [-112.111, 36.099]]),
    _feature(2, "South Kaibab", [[-112.083, 36.053], [-112.090, 36.101]]),
    _feature(3, "North Kaibab", [[[-112.057, 36.217], [-112.090, 36.101]]], "MultiLineString"),
    _feature(4, "Old Bright Angel", [[-112.15, 36.05], [-112.14, 36.06]]),
    _feature(5, None, [[-112.15, 36.05], [-112.14, 36.06]]),
]


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def __call__(self, url, timeout):
        self.urls.append(url)
        status, body = self.responses.pop(0)
        return FakeResponse(status, body)


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        if IfNoneMatch == "*" and (Bucket, Key) in self.objects:
            raise RuntimeError("PreconditionFailed")
        self.objects[(Bucket, Key)] = Body


def _query(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def test_the_service_url_is_the_one_the_first_run_check_confirmed():
    assert NPS_TRAILS_QUERY_URL == (
        "https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/"
        "NPS_Public_Trails/FeatureServer/0/query"
    )


def test_phase_a_trails_are_the_three_john_decided():
    assert PHASE_A_TRAILS == ("Bright Angel", "South Kaibab", "North Kaibab")


def test_query_url_asks_for_one_park_as_geojson_in_a_stable_order():
    query = _query(trail_query_url("GRCA", offset=2000))
    assert query == {
        "where": "UNITCODE='GRCA'",
        "outFields": "*",
        "orderByFields": "OBJECTID",
        "resultOffset": "2000",
        "resultRecordCount": "2000",
        "f": "geojson",
    }


def test_query_url_refuses_a_unit_code_that_is_not_four_letters():
    with pytest.raises(ValueError, match="unit code"):
        trail_query_url("GRCA' OR '1'='1", offset=0)


def test_fetch_reads_one_page_when_the_service_says_there_is_no_more():
    opener = FakeOpener([(200, _page(TRAILS))])
    pages = fetch_trail_pages("GRCA", now_utc=FETCHED_AT, opener=opener)
    assert len(pages) == 1
    assert pages[0].body == _page(TRAILS)
    assert pages[0].fetched_at == FETCHED_AT
    assert _query(opener.urls[0])["resultOffset"] == "0"


def test_fetch_follows_pages_until_the_transfer_limit_is_not_exceeded():
    opener = FakeOpener([(200, _page(TRAILS[:2], more=True)), (200, _page(TRAILS[2:]))])
    pages = fetch_trail_pages("GRCA", now_utc=FETCHED_AT, opener=opener)
    assert len(pages) == 2
    assert [_query(url)["resultOffset"] for url in opener.urls] == ["0", "2"]


def test_fetch_stops_on_any_status_other_than_200():
    with pytest.raises(RuntimeError, match="HTTP 403"):
        fetch_trail_pages("GRCA", now_utc=FETCHED_AT, opener=FakeOpener([(403, b"")]))


def test_fetch_stops_when_the_service_returns_an_error_inside_a_200():
    body = json.dumps({"error": {"code": 400, "message": "Invalid URL"}}).encode()
    with pytest.raises(RuntimeError, match="Invalid URL"):
        fetch_trail_pages("GRCA", now_utc=FETCHED_AT, opener=FakeOpener([(200, body)]))


def test_fetch_stops_after_too_many_pages():
    pages = [(200, _page(TRAILS[:1], more=True))] * 5
    with pytest.raises(RuntimeError, match="more than 3 pages"):
        fetch_trail_pages("GRCA", now_utc=FETCHED_AT, opener=FakeOpener(pages), max_pages=3)


def test_store_trail_pages_keeps_each_page_with_a_manifest():
    opener = FakeOpener([(200, _page(TRAILS[:2], more=True)), (200, _page(TRAILS[2:]))])
    pages = fetch_trail_pages("GRCA", now_utc=FETCHED_AT, opener=opener)
    s3 = FakeS3()
    manifests = store_trail_pages(s3, "raw-bucket", pages)
    prefix = "signal/nps/trails/unitcode=GRCA/fetched_at=2026-10-28T04:30:00Z"
    assert [m["raw_key"] for m in manifests] == [
        f"{prefix}/page-000.json",
        f"{prefix}/page-001.json",
    ]
    assert s3.objects[("raw-bucket", f"{prefix}/page-000.json")] == pages[0].body
    assert ("raw-bucket", f"{prefix}/page-001.manifest.json") in s3.objects


def test_parse_reads_lines_and_multilines_into_trail_lines():
    lines = parse_trail_geojson(_page(TRAILS), CONTRACT)
    assert lines[0] == TrailLine(
        trail_line_id="1",
        trlname="Bright Angel",
        unitcode="GRCA",
        parts=(((-112.144, 36.057), (-112.111, 36.099)),),
    )
    assert lines[2].parts == (((-112.057, 36.217), (-112.090, 36.101)),)


def test_parse_stops_when_a_contract_field_is_missing():
    renamed = [
        {**f, "properties": {"OBJECTID": 1, "TRAILNAME": "x", "UNITCODE": "GRCA"}} for f in TRAILS
    ]
    with pytest.raises(BreakingSchemaChange, match="removed TRLNAME"):
        parse_trail_geojson(_page(renamed), CONTRACT)


def test_select_keeps_only_the_exact_names():
    lines = parse_trail_geojson(_page(TRAILS), CONTRACT)
    selected = select_trails(lines, PHASE_A_TRAILS)
    assert [line.trlname for line in selected] == list(PHASE_A_TRAILS)


def test_select_stops_when_a_trail_is_missing():
    lines = parse_trail_geojson(_page(TRAILS[1:]), CONTRACT)
    with pytest.raises(ValueError, match="Bright Angel: found 0 lines"):
        select_trails(lines, PHASE_A_TRAILS)


def test_select_stops_when_a_trail_has_two_lines():
    extra = _feature(9, "South Kaibab", [[-112.0, 36.0], [-112.0, 36.1]])
    lines = parse_trail_geojson(_page([*TRAILS, extra]), CONTRACT)
    with pytest.raises(ValueError, match="South Kaibab: found 2 lines"):
        select_trails(lines, PHASE_A_TRAILS)


def test_select_stops_when_a_trail_is_split_into_parts():
    split = _feature(
        3,
        "North Kaibab",
        [[[-112.05, 36.2], [-112.06, 36.15]], [[-112.07, 36.14], [-112.09, 36.1]]],
        "MultiLineString",
    )
    lines = parse_trail_geojson(_page([*TRAILS[:2], split]), CONTRACT)
    with pytest.raises(ValueError, match="North Kaibab: the line has 2 parts"):
        select_trails(lines, PHASE_A_TRAILS)


def test_distance_of_one_degree_of_latitude_is_about_111_km():
    assert distance_m((-112.0, 36.0), (-112.0, 37.0)) == pytest.approx(111_195, rel=1e-4)


def test_sampling_puts_a_point_every_50_m_and_keeps_the_end():
    line = ((-112.0, 36.1), (-112.0 + 4.5 * STEP, 36.1))  # about 225 m long
    points = sample_points_along_line(line, 50)
    assert len(points) == 6  # 0, 50, 100, 150, 200 m, and the end at about 225 m
    assert points[0] == line[0]
    assert points[-1] == line[-1]
    gaps = [distance_m(a, b) for a, b in zip(points, points[1:], strict=False)]
    assert gaps[:4] == pytest.approx([50, 50, 50, 50], abs=0.01)
    assert gaps[4] == pytest.approx(25, abs=0.5)


def test_sampling_does_not_repeat_the_end_when_it_falls_on_a_step():
    line = ((-112.0, 36.1), (-112.0 + 2 * STEP, 36.1))
    points = sample_points_along_line(line, 50)
    assert len(points) == 3
    assert distance_m(points[-2], points[-1]) == pytest.approx(50, abs=0.01)


def test_sampling_measures_along_bends_not_straight_across():
    corner = (-112.0 + STEP * 1.5, 36.1)
    line = ((-112.0, 36.1), corner, (corner[0], 36.1 + 75 / 111_195))
    points = sample_points_along_line(line, 50)
    # 75 m east, then 75 m north: points at 0, 50, 100 and the end at 150 m.
    assert len(points) == 4
    assert points[2][0] == pytest.approx(corner[0], abs=1e-9)
    assert distance_m(corner, points[2]) == pytest.approx(25, abs=0.05)


def test_sampling_refuses_a_line_with_fewer_than_two_points():
    with pytest.raises(ValueError, match="two points"):
        sample_points_along_line(((-112.0, 36.1),), 50)


def test_trail_id_is_a_readable_slug():
    assert trail_id_for("GRCA", "Bright Angel") == "grca-bright-angel"
    assert trail_id_for("GRCA", "Rim-to-Rim  Trail") == "grca-rim-to-rim-trail"


def test_trail_point_rows_number_points_from_zero_along_each_trail():
    lines = select_trails(parse_trail_geojson(_page(TRAILS), CONTRACT), PHASE_A_TRAILS)
    points = trail_point_rows(lines, 50)
    bright = [p for p in points if p.trail_id == "grca-bright-angel"]
    assert bright[0] == TrailPoint(
        trail_point_id="grca-bright-angel-00000",
        trail_id="grca-bright-angel",
        trail_name="Bright Angel",
        unit_code="GRCA",
        seq=0,
        lon=-112.144,
        lat=36.057,
    )
    assert [p.seq for p in bright] == list(range(len(bright)))
    assert len({p.trail_point_id for p in points}) == len(points)


def test_the_trail_point_contract_has_one_column_per_trail_point_field():
    columns = contract_columns(POINT_CONTRACT, "trail_point")
    assert [column.name for column in columns] == [field.name for field in fields(TrailPoint)]
    assert {column.name for column in columns if not column.required} == {"trail_name"}


def test_trail_line_rows_carry_the_geometry_as_geojson_text_and_the_manifest():
    lines = select_trails(parse_trail_geojson(_page(TRAILS), CONTRACT), PHASE_A_TRAILS)
    manifest = {
        "source_url": "https://example.test/q",
        "fetched_at_utc": "2026-10-28T04:30:00Z",
        "content_sha256": "0" * 64,
    }
    rows = trail_line_rows(lines, manifest)
    assert rows[0] == {
        "trail_line_id": "1",
        "trlname": "Bright Angel",
        "unitcode": "GRCA",
        "geometry_geojson": json.dumps(
            {"type": "LineString", "coordinates": [[-112.144, 36.057], [-112.111, 36.099]]}
        ),
        "source_url": "https://example.test/q",
        "fetched_at_utc": FETCHED_AT,
        "content_sha256": "0" * 64,
    }


class FakeWriter:
    def __init__(self, calls):
        self.calls = calls

    def partitionedBy(self, column):  # noqa: N802, Spark method name
        self.calls.append(f"partitionedBy:{column}")
        return self

    def create(self):
        self.calls.append("create")

    def overwritePartitions(self):  # noqa: N802, Spark method name
        self.calls.append("overwritePartitions")


class FakeSpark:
    def __init__(self):
        self.calls = []
        self.rows = {}
        self.schemas = {}

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return False

        self.catalog = Catalog()

    def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
        spark = self

        class Frame:
            def writeTo(self, name):  # noqa: N802, Spark method name
                spark.calls.append(f"writeTo:{name}")
                spark.rows[name] = rows
                spark.schemas[name] = schema
                return FakeWriter(spark.calls)

        return Frame()


def test_load_writes_both_tables_for_the_run_date():
    lines = select_trails(parse_trail_geojson(_page(TRAILS), CONTRACT), PHASE_A_TRAILS)
    manifest = {"source_url": "u", "fetched_at_utc": "2026-10-28T04:30:00Z", "content_sha256": "h"}
    spark = FakeSpark()
    counts = load_trail_tables(
        spark,
        trail_line_rows(lines, manifest),
        trail_point_rows(lines, 50),
        date(2026, 10, 28),
        line_contract_path=CONTRACT,
        point_contract_path=POINT_CONTRACT,
        namespace="portfolio_dev",
    )
    assert counts["nps_trail_line"] == 3
    assert counts["trail_point"] == len(spark.rows["portfolio.portfolio_dev.trail_point"])
    assert spark.rows["portfolio.portfolio_dev.trail_point"][0]["run_date"] == date(2026, 10, 28)
    assert spark.calls[0] == "writeTo:portfolio.portfolio_dev.nps_trail_line"
    assert spark.schemas["portfolio.portfolio_dev.trail_point"] == spark_schema(
        contract_columns(POINT_CONTRACT, "trail_point")
    )
