select
    trail_point_id,
    carrier,
    technology,
    h3_cell_res9,
    covered,
    release as fcc_release
from {{ source('lake', 'trail_point_coverage') }}
