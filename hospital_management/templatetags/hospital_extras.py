from datetime import datetime

from django import template

register = template.Library()


@register.filter
def humanize_iso(value, fmt='%b %d, %Y %H:%M'):
    """Format an ISO-8601 string from the external API as a readable date."""
    if not value:
        return '—'
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return value
    return dt.strftime(fmt)
