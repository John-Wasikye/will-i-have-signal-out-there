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
