
    [
        {% for item in items %}
        {
            "id": "{{ item.id }}",
            "code": "{{ item.code }}",
            "name": "{{ item.name }}",
            "category": "{{ item.category|default:'OTHER' }}",
            "lot_size": {{ item.lot_size|default:0 }},
            "lot_with_box": {{ item.lot_with_box|default:0 }},
            "weight": {{ item.machining_weight|default:0 }},
            "available": {{ item.available_stock|default:0 }},
            "is_set": {% if item.item_type == 'SET' or item.components.exists %}true{% else %}false{% endif %},
            "components": [
                {% if item.components.exists %}
                    {% for comp in item.components.all %}
                    {
                        "id": "{{ comp.component_item.id }}", 
                        "name": "{{ comp.component_item.name }}", 
                        "qty_per_set": {{ comp.quantity }}
                    }{% if not forloop.last %},{% endif %}
                    {% endfor %}
                {% endif %}
            ]
        }{% if not forloop.last %},{% endif %}
        {% endfor %}
    ]
