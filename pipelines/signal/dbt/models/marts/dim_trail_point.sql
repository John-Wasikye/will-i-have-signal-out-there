with cells as (
    select
        trail_point_id,
        any_value(h3_cell_res9) as h3_cell_res9
    from {{ ref('int_trail_point_coverage') }}
    group by trail_point_id
)

select
    points.trail_point_id,
    points.trail_id,
    points.trail_name,
    points.unit_code,
    points.seq,
    points.lon,
    points.lat,
    cells.h3_cell_res9
from {{ ref('stg_trail_point') }} as points
left join cells using (trail_point_id)
