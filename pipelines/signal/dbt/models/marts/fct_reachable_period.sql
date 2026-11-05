-- Merges each point's overlapping and touching satellite windows into reachable periods. A window
-- starts a new period when it begins more than one minute after every earlier window has ended.
with ordered as (
    select
        *,
        max(window_end_utc) over (
            partition by trail_point_id
            order by window_start_utc, window_end_utc
            rows between unbounded preceding and 1 preceding
        ) as latest_end_so_far
    from {{ ref('stg_satellite_window') }}
),

numbered as (
    select
        *,
        sum(
            case
                when latest_end_so_far is null then 1
                when window_start_utc > latest_end_so_far + interval 1 minute then 1
                else 0
            end
        ) over (
            partition by trail_point_id
            order by window_start_utc, window_end_utc
            rows unbounded preceding
        ) as period_number
    from ordered
)

select
    trail_point_id,
    min(window_start_utc) as period_start_utc,
    max(window_end_utc) as period_end_utc,
    any_value(min_elevation_deg) as min_elevation_deg,
    any_value(run_logical_date) as run_logical_date,
    any_value(valid_until_utc) as valid_until_utc,
    any_value(run_started_utc) as run_started_utc,
    any_value(loaded_at_utc) as loaded_at_utc
from numbered
group by trail_point_id, period_number
