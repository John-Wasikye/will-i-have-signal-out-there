"""compute_horizons on real Spark, in local mode as on the session box.

The fake Spark in test_horizon_nightly.py runs each partition in this process. Real Spark sends
the work to separate Python worker processes, which must be able to import the horizon code and
read the tile files, so this test checks that part. It skips where pyspark is not installed; CI's
"Spark tests" job runs it.
"""

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pyspark", reason="pyspark is not installed here")

from terrain_horizon import compute_horizons  # noqa: E402
from test_geotiff import write_tiff  # noqa: E402
from trail_loader import TrailPoint  # noqa: E402

SIGNAL = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    # Spark's Python workers import modules by name from PYTHONPATH, as the box's image sets it.
    # pytest adds the folders to this process only, so pass them on before Spark starts.
    folders = [SIGNAL, SIGNAL.parent / "platform" / "spark", SIGNAL.parent / "platform" / "publish"]
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(folder) for folder in folders] + [os.environ.get("PYTHONPATH", "")]
    )
    session = SparkSession.builder.master("local[2]").appName("horizon_tests").getOrCreate()
    yield session
    session.stop()


def test_every_point_gets_its_horizon_back_in_order(spark, tmp_path):
    heights = np.full((121, 121), 500.0, dtype=np.float32)
    # A ridge 200 m high starting about 5 km east of the points (column 48), inside the 15 km
    # range, so the east sectors are not zero.
    heights[:, 55:] = 700.0
    path = tmp_path / "tile.tif"
    write_tiff(path, heights, west=-113.0, north=37.0, step_deg=1 / 120, tile=64)
    points = [TrailPoint(f"tp-{n}", "t", "T", "GRCA", n, -112.6, 36.5) for n in range(5)]

    horizons = compute_horizons(spark, points, [path], partitions=2)

    assert [h.trail_point_id for h in horizons] == [f"tp-{n}" for n in range(5)]
    assert all(len(h.angles_deg) == 36 for h in horizons)
    assert horizons[0].angles_deg[9] > 0  # the ridge to the east
    assert horizons[0].angles_deg[27] == 0.0  # flat to the west
