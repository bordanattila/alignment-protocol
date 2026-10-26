"""One canonical display/identity policy for HTTP and direct store callers."""
import unicodedata


def normalize_callsign(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Enter a callsign of 1–24 characters.')
    display = unicodedata.normalize('NFKC', value).strip()
    if not 1 <= len(display) <= 24:
        raise ValueError('Enter a callsign of 1–24 characters.')
    # Format/control characters can produce distinct IDs with identical labels.
    # Preserve international letters, accents, punctuation and visible symbols.
    if any(unicodedata.category(character).startswith('C') for character in display):
        raise ValueError('Callsigns cannot contain invisible formatting or control characters.')
    return display


def callsign_key(value: str) -> str:
    # Collapse whitespace in the comparison key: HTML renders consecutive spaces
    # alike. Display capitalization and ordinary interior spacing are preserved.
    # Older in-memory seats may predate validation. Compare them safely without
    # renaming them or breaking credential-based recovery. New names are already
    # validated before this key is used.
    text = unicodedata.normalize('NFKC', value)
    visible = ''.join(c for c in text if not unicodedata.category(c).startswith('C'))
    return ' '.join(unicodedata.normalize('NFKC', visible.casefold()).split())
