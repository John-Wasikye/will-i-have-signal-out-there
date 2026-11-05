-- One row per UTC minute of the run's prediction span (OQ-33, ADR 0028). The span is the 26 hours
-- that end at the run's valid until time (ADR 0019); that end minute itself is outside the span.
with span as (
    select max(valid_until_utc) as valid_until_utc
    from {{ ref('stg_satellite_window') }}
),

minutes as (
    select unnest(
        generate_series(
            valid_until_utc - interval 26 hour,
            valid_until_utc - interval 1 minute,
            interval 1 minute
        )
    ) as time_utc
    from span
)

select
    strftime(time_utc, '%Y%m%dT%H%MZ') as time_key,
    time_utc
from minutes
