select
    trail_point_id,
    trail_id,
    trail_name,
    unit_code,
    seq,
    lon,
    lat
from {{ source('lake', 'trail_point') }}
