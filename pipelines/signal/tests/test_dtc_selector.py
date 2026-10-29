"""Tests for the Direct-to-Cell selector (C2, ADR 0002, FR-3, FR-4, AC-1A.1).

Satellites are selected by the [DTC] tag in their names. Each selected satellite is
cross-checked: its perigee and apogee must lie between 330 and 370 km, and its inclination
within 0.5 degrees of 43 or 53. The sources say "about" for both; these tests fix the exact
rule, as ADR 0002 asks. A disagreement is logged and listed, and the satellite stays selected.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dtc_selector import (
    OrbitCheckResult,
    altitude_km_from_elements,
    check_orbit,
    disagreement_rows,
    has_dtc_tag,
    satellite_rows,
    select_dtc_satellites,
)
from lake_write import contract_columns


def _row(norad: int, name: str, mean_motion: float, inclination: float, ecc: float = 0.0001):
    return {
        "norad_cat_id": norad,
        "object_name": name,
        "mean_motion_rev_per_day": mean_motion,
        "eccentricity": ecc,
        "inclination_deg": inclination,
    }


# Mean motions from the CelesTrak file of Oct 28, 2026: STARLINK-11072 [DTC] at about 359 km,
# inside the band, and STARLINK-11075 [DTC] at about 296 km, below it.
IN_BAND = 15.69828588
LOW = 15.92141426


@pytest.mark.parametrize(
    ("name", "tagged"),
    [
        ("STARLINK-11072 [DTC]", True),
        ("STARLINK-1008", False),
        ("STARLINK-11072 [dtc]", False),
        ("STARLINK-11072 DTC", False),
        ("[DTC] STARLINK-1", True),
    ],
)
def test_has_dtc_tag_matches_the_exact_bracketed_tag(name, tagged):
    assert has_dtc_tag(name) is tagged


def test_altitude_from_elements_gives_perigee_and_apogee_in_km():
    perigee, apogee = altitude_km_from_elements(_row(1, "S", IN_BAND, 53, ecc=0.0))
    assert perigee == pytest.approx(359.4, abs=0.5)
    assert apogee == pytest.approx(perigee)


def test_eccentricity_spreads_perigee_and_apogee_around_the_mean():
    perigee, apogee = altitude_km_from_elements(_row(1, "S", IN_BAND, 53, ecc=0.001))
    assert apogee - perigee == pytest.approx(2 * 0.001 * (359.4 + 6378.137), abs=0.5)


def test_an_orbit_in_the_band_at_53_degrees_has_no_problem():
    assert check_orbit(_row(1, "S [DTC]", IN_BAND, 53.05)).problems == ()


def test_an_orbit_at_43_degrees_has_no_problem():
    assert check_orbit(_row(1, "S [DTC]", IN_BAND, 42.6)).problems == ()


def test_a_low_orbit_is_an_altitude_problem():
    result = check_orbit(_row(58706, "STARLINK-11075 [DTC]", LOW, 53.14))
    assert result.problems == ("altitude",)
    assert result.norad_cat_id == 58706
    assert result.perigee_km == pytest.approx(296.3, abs=3.0)


def test_an_inclination_away_from_43_and_53_is_an_inclination_problem():
    assert check_orbit(_row(1, "S [DTC]", IN_BAND, 97.6)).problems == ("inclination",)


def test_inclination_more_than_half_a_degree_off_is_a_problem():
    assert check_orbit(_row(1, "S [DTC]", IN_BAND, 53.51)).problems == ("inclination",)


def test_both_problems_are_listed():
    assert check_orbit(_row(1, "S [DTC]", LOW, 70.0)).problems == ("altitude", "inclination")


def test_select_keeps_tagged_satellites_and_lists_disagreements(caplog):
    rows = [
        _row(1, "STARLINK-1 [DTC]", IN_BAND, 53.0),
        _row(2, "STARLINK-2", IN_BAND, 53.0),
        _row(58706, "STARLINK-11075 [DTC]", LOW, 53.14),
    ]
    with caplog.at_level(logging.WARNING, logger="dtc_selector"):
        selected, disagreements = select_dtc_satellites(rows)
    assert [row["norad_cat_id"] for row in selected] == [1, 58706]
    assert [(d.norad_cat_id, d.problems) for d in disagreements] == [(58706, ("altitude",))]
    assert isinstance(disagreements[0], OrbitCheckResult)
    assert "STARLINK-11075 [DTC]" in caplog.text
    assert "altitude" in caplog.text


def test_untagged_satellites_in_the_band_are_not_selected_or_listed():
    rows = [_row(1, "STARLINK-1 [DTC]", IN_BAND, 53.0), _row(2, "STARLINK-2", IN_BAND, 53.0)]
    selected, disagreements = select_dtc_satellites(rows)
    assert [row["norad_cat_id"] for row in selected] == [1]
    assert disagreements == []


def test_select_stops_when_no_satellite_is_tagged():
    # CelesTrak dropping or renaming the tag must fail loudly, not publish an empty sky.
    with pytest.raises(ValueError, match=r"no satellite carries the \[DTC\] tag"):
        select_dtc_satellites([_row(2, "STARLINK-2", IN_BAND, 53.0)])


CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
FETCHED_AT = datetime(2026, 10, 29, 10, 1, tzinfo=UTC)


def _lake_row(norad: int, name: str, mean_motion: float, inclination: float) -> dict:
    """A celestrak_gp row as the orbit loader writes it."""
    return _row(norad, name, mean_motion, inclination) | {
        "epoch_utc": datetime(2026, 10, 29, 6, 0, tzinfo=UTC),
        "ra_of_asc_node_deg": 120.5,
        "arg_of_pericenter_deg": 90.1,
        "mean_anomaly_deg": 270.2,
        "bstar": 0.00012,
        "source_url": "https://celestrak.org/x",
        "fetched_at_utc": FETCHED_AT,
        "content_sha256": "a" * 64,
    }


def _names(contract: str) -> list[str]:
    return [column.name for column in contract_columns(CONTRACTS / f"{contract}.yaml", contract)]


def test_satellite_rows_have_exactly_the_contract_columns_with_the_altitude():
    selected, _ = select_dtc_satellites([_lake_row(1, "STARLINK-1 [DTC]", IN_BAND, 53.0)])

    rows = satellite_rows(selected)

    assert list(rows[0]) == _names("dtc_satellite")
    assert 330 < rows[0]["perigee_km"] < rows[0]["apogee_km"] < 370
    assert rows[0]["content_sha256"] == "a" * 64


def test_disagreement_rows_name_the_problems_and_carry_the_pull():
    _, disagreements = select_dtc_satellites([_lake_row(2, "STARLINK-2 [DTC]", LOW, 70.0)])

    rows = disagreement_rows(disagreements, {"fetched_at_utc": FETCHED_AT, "content_sha256": "b"})

    assert list(rows[0]) == _names("dtc_disagreement")
    assert rows[0]["problems"] == "altitude, inclination"
    assert rows[0]["fetched_at_utc"] == FETCHED_AT
