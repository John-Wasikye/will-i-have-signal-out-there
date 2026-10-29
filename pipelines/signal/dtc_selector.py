"""Direct-to-Cell selector (C2): pick the satellites that can carry a satellite text.

Satellites are selected by the ``[DTC]`` tag in their CelesTrak names (ADR 0002, FR-3). Each
selected satellite is cross-checked against the Direct-to-Cell shells (FR-4). The sources say
"about 330 to 370 km" and "43 or 53 degrees"; the exact rule, fixed here and in the tests:

- altitude: perigee and apogee both between 330 and 370 km, computed from mean motion and
  eccentricity above the equatorial radius;
- inclination: within 0.5 degrees of 43 or 53.

A disagreement is logged and listed, and the satellite stays selected: the tag is the selector
and the cross-check only reports. If no satellite carries the tag, the run stops, because
CelesTrak renaming or dropping the tag must not publish an empty sky.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

DTC_TAG = "[DTC]"
EARTH_MU_KM3_S2 = 398600.4418
EARTH_EQUATORIAL_RADIUS_KM = 6378.137
ALTITUDE_BAND_KM = (330.0, 370.0)
DTC_INCLINATIONS_DEG = (43.0, 53.0)
INCLINATION_TOLERANCE_DEG = 0.5

log = logging.getLogger("dtc_selector")


@dataclass(frozen=True)
class OrbitCheckResult:
    """One satellite's cross-check. ``problems`` names each check it failed, or is empty."""

    norad_cat_id: int
    object_name: str
    perigee_km: float
    apogee_km: float
    inclination_deg: float
    problems: tuple[str, ...]


def has_dtc_tag(name: str) -> bool:
    """Return True when the name carries the exact ``[DTC]`` tag."""
    return DTC_TAG in name


def altitude_km_from_elements(row: Mapping) -> tuple[float, float]:
    """Return perigee and apogee altitude in km from mean motion and eccentricity."""
    radians_per_second = row["mean_motion_rev_per_day"] * 2 * math.pi / 86400
    semi_major_axis_km = (EARTH_MU_KM3_S2 / radians_per_second**2) ** (1 / 3)
    eccentricity = row["eccentricity"]
    perigee = semi_major_axis_km * (1 - eccentricity) - EARTH_EQUATORIAL_RADIUS_KM
    apogee = semi_major_axis_km * (1 + eccentricity) - EARTH_EQUATORIAL_RADIUS_KM
    return perigee, apogee


def check_orbit(row: Mapping) -> OrbitCheckResult:
    """Cross-check one satellite's altitude and inclination against the Direct-to-Cell shells."""
    perigee, apogee = altitude_km_from_elements(row)
    inclination = row["inclination_deg"]
    low, high = ALTITUDE_BAND_KM
    problems = []
    if not (low <= perigee and apogee <= high):
        problems.append("altitude")
    if all(abs(inclination - shell) > INCLINATION_TOLERANCE_DEG for shell in DTC_INCLINATIONS_DEG):
        problems.append("inclination")
    return OrbitCheckResult(
        norad_cat_id=row["norad_cat_id"],
        object_name=row["object_name"],
        perigee_km=perigee,
        apogee_km=apogee,
        inclination_deg=inclination,
        problems=tuple(problems),
    )


def select_dtc_satellites(rows: Iterable[Mapping]) -> tuple[list[Mapping], list[OrbitCheckResult]]:
    """Return the tagged satellites and the cross-check disagreements among them."""
    selected = [row for row in rows if has_dtc_tag(row["object_name"])]
    if not selected:
        raise ValueError(f"no satellite carries the {DTC_TAG} tag; the source may have changed")
    disagreements = [result for result in map(check_orbit, selected) if result.problems]
    for result in disagreements:
        log.warning(
            "%s (%s) disagrees with the Direct-to-Cell shells: %s; perigee %.0f km, "
            "apogee %.0f km, inclination %.2f degrees",
            result.object_name,
            result.norad_cat_id,
            ", ".join(result.problems),
            result.perigee_km,
            result.apogee_km,
            result.inclination_deg,
        )
    return selected, disagreements


_ELEMENT_COLUMNS = (
    "norad_cat_id",
    "object_name",
    "epoch_utc",
    "inclination_deg",
    "mean_motion_rev_per_day",
    "eccentricity",
    "ra_of_asc_node_deg",
    "arg_of_pericenter_deg",
    "mean_anomaly_deg",
    "bstar",
)


def satellite_rows(selected: Iterable[Mapping]) -> list[dict]:
    """Shape the selected ``celestrak_gp`` rows for ``dtc_satellite``, with their altitude."""
    rows = []
    for row in selected:
        perigee, apogee = altitude_km_from_elements(row)
        rows.append(
            {column: row[column] for column in _ELEMENT_COLUMNS}
            | {
                "perigee_km": perigee,
                "apogee_km": apogee,
                "fetched_at_utc": row["fetched_at_utc"],
                "content_sha256": row["content_sha256"],
            }
        )
    return rows


def disagreement_rows(disagreements: Iterable[OrbitCheckResult], pull: Mapping) -> list[dict]:
    """Shape the cross-check disagreements for ``dtc_disagreement``.

    ``pull`` gives the ``fetched_at_utc`` and ``content_sha256`` of the CelesTrak file checked.
    """
    return [
        {
            "norad_cat_id": result.norad_cat_id,
            "object_name": result.object_name,
            "problems": ", ".join(result.problems),
            "perigee_km": result.perigee_km,
            "apogee_km": result.apogee_km,
            "inclination_deg": result.inclination_deg,
            "fetched_at_utc": pull["fetched_at_utc"],
            "content_sha256": pull["content_sha256"],
        }
        for result in disagreements
    ]
