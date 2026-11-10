{% test unique_columns(model, columns) %}
select {{ columns | join(', ') }}
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

{% test starts_on_or_before_end(model, start_column, end_column) %}
select *
from {{ model }}
where {{ start_column }} > {{ end_column }}
{% endtest %}

{% test at_least_per_group(model, group_column, count_column, minimum) %}
select {{ group_column }}
from {{ model }}
group by {{ group_column }}
having sum({{ count_column }}) < {{ minimum }}
{% endtest %}
