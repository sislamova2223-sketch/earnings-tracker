# {{ v.company }} ({{ v.ticker }}) · {{ v.quarter }} earnings brief

_Generated {{ today }} · {{ counts.verified }} of {{ counts.total }} items verified against source_

## Forward guidance

| Metric | Period | Outlook | Basis | Mgmt. framing | Src |
|---|---|---:|---|---|---|
{% for i, c in guidance -%}
| {{ i.metric }} | {{ i.period }} | {{ i | fmt_range }} | {{ i.basis or "" }} | {{ i.direction }} | {{ tag(c) }} |
{% endfor %}
## Reported results

| Metric | Period | Value | Y/Y | Src |
|---|---|---:|---:|---|
{% for i, c in reported -%}
| {{ i.metric }} | {{ i.period }} | {{ i.value | fmt(i.unit) }} | {% if i.yoy_change_pct is not none %}{{ "%+g" | format(i.yoy_change_pct) }}%{% endif %} | {{ tag(c) }} |
{% endfor %}
## Management tone

{% for i, c in tone -%}
- **{{ i.signal | upper }} · {{ i.topic }}:** {{ i.summary }} _"{{ i.source_quote | truncate(220) }}"_ [{{ tag(c) }}]
{% endfor %}
---
{{ counts.rejected }} item(s) failed validation and were excluded. See the audit log.
