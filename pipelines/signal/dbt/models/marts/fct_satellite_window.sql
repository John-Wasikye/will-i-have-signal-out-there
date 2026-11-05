select
    trail_point_id,
    satellite_id,
    window_start_utc,
    window_end_utc,
    min_elevation_deg,
    run_logical_date,
    valid_until_utc,
    run_started_utc,
    loaded_at_utc
from {{ ref('stg_satellite_window') }}
