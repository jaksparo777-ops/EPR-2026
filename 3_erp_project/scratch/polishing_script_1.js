
    {
        {% for key, value in piece_stock.items %}
        "{{ key }}": {{ value }}{% if not forloop.last %},{% endif %}
        {% endfor %}
    }
