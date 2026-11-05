select
    trail_point_id,
    carrier,
    covered,
    fcc_release,
    cast('{{ var("loaded_at_utc") }}' as timestamptz) as loaded_at_utc
from {{ ref('int_trail_point_coverage') }}
