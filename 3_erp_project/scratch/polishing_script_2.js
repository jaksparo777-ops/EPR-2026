
    {
        {% for key, value in set_capacity.items %}
        "{{ key }}": {{ value }}{% if not forloop.last %},{% endif %}
        {% endfor %}
    }
