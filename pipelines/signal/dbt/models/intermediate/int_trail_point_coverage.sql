-- A point counts as covered for a carrier when any of that carrier's technologies lists its cell.
select
    trail_point_id,
    carrier,
    any_value(h3_cell_res9) as h3_cell_res9,
    bool_or(covered) as covered,
    max(fcc_release) as fcc_release
from {{ ref('stg_fcc_coverage') }}
group by trail_point_id, carrier
