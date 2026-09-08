"""Small outcome markers, never JSON-encoded file contents or merge authority."""


def outcome(summary: str, allowed: set[str]) -> tuple[str, str]:
    marker, _, body = summary.strip().partition("\n")
    marker = marker.strip()
    if marker not in allowed:
        raise ValueError("Native role returned an unrecognized outcome; inspect its saved artifact")
    return marker, body.strip()[:7500]
