
    [
        {% for alloc in allocations %}
        {
            "item_id": "{{ alloc.item_id }}",
            "worker_id": "{% if alloc.job_worker %}jw_{{ alloc.job_worker.id }}{% elif alloc.worker and alloc.worker.worker_type == 'JOB_WORKER' %}jw_{{ alloc.worker.job_worker.id|default:alloc.worker.id }}{% elif alloc.worker %}w_{{ alloc.worker.id }}{% endif %}"
        }{% if not forloop.last %},{% endif %}
        {% endfor %}
    ]
