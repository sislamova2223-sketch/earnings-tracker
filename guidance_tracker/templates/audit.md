# Validation audit · {{ v.ticker }} {{ v.quarter }}

{{ counts.verified }} verified · {{ counts.rejected }} rejected · {{ counts.total }} total

{% for section, pairs in [("Guidance", v.guidance), ("Reported", v.reported), ("Tone", v.tone)] -%}
## {{ section }}

{% for i, c in pairs -%}
- {% if c.status == "verified" %}✅{% else %}❌{% endif %} **{{ i.metric if i.metric is defined else i.topic }}**{% if c.source_doc %} ({{ c.source_doc }}){% endif %}
{%- for r in c.reasons %}
  - {{ r }}
{%- endfor %}
  - quote: "{{ i.source_quote }}"
{% endfor %}
{% endfor %}
