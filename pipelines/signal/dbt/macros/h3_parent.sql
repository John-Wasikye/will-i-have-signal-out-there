{#
  The H3 cell that contains `cell` at `resolution` (H3's cell_to_parent), in plain SQL, because
  DuckDB here has no H3 extension. An H3 index is 64 bits: the resolution sits in bits 52 to 55,
  and each finer level is a 3-bit digit below the base cell. A parent has its own resolution and
  every finer digit set to 7. The tests check the result against the h3 library.
#}
{% macro h3_parent(cell, resolution) %}
lower(hex(
    ((('0x' || {{ cell }})::ubigint & ~(15::ubigint << 52)) | ({{ resolution }}::ubigint << 52))
    | ((1::ubigint << (3 * (15 - {{ resolution }}))) - 1)
))
{% endmacro %}
