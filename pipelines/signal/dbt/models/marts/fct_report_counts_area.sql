-- Hiker reports per area, carrier and answer over the 7 days the copy step selected (C23).
-- An area is the H3 resolution 6 parent of the report cell, and an area with fewer than
-- 5 reports is left out here, so a small count never reaches the published file (ADR 0030).
with reports as (
    select
        {{ h3_parent('h3_cell_res9', 6) }} as area_id,
        carrier,
        had_signal,
        report_hour_utc
    from {{ source('lake', 'signal_report') }}
),

areas as (
    select
        area_id,
        max(report_hour_utc) as counted_through_utc
    from reports
    group by area_id
    having count(*) >= 5
)

select
    reports.area_id,
    reports.carrier,
    reports.had_signal,
    cast(count(*) as integer) as report_count,
    areas.counted_through_utc
from reports
inner join areas on reports.area_id = areas.area_id
group by reports.area_id, reports.carrier, reports.had_signal, areas.counted_through_utc
