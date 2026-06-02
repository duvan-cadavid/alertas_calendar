import re

_MEETING_RE = re.compile(
    r'https?://(?:'
    r'meet\.google\.com'
    r'|(?:[\w-]+\.)?zoom\.us'
    r'|teams\.microsoft\.com'
    r'|teams\.live\.com'
    r'|meeting\.zoho\.(?:com|eu)'
    r'|go\.zoho\.com'
    r')/[^\s<>"\']*',
    re.IGNORECASE,
)


def extract_meeting_url(text: str, observations: str = '') -> str | None:
    """Return the first meeting URL found in text or observations, or None."""
    for source in (text or '', observations or ''):
        m = _MEETING_RE.search(source)
        if m:
            return m.group(0).rstrip('.,;)')
    return None
