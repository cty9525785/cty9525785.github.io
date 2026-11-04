"""Small HTML helpers for the tests (stdlib html.parser and regex)."""
import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _Collector(HTMLParser):
    def __init__(self, name):
        super().__init__(convert_charrefs=True)
        self.name = name
        self.found = []

    def handle_starttag(self, tag, attrs):
        if tag == self.name:
            self.found.append(dict(attrs))

    handle_startendtag = handle_starttag


def tags(html: str, name: str) -> list[dict]:
    """Attributes of every <name> start tag, in document order. Bare attributes map to None."""
    collector = _Collector(name)
    collector.feed(html)
    return collector.found


def section(html: str, id: str) -> str:
    """The <section id="..."> element with that id, or "" if there is none."""
    match = re.search(rf'<section id="{re.escape(id)}"[^>]*>.*?</section>', html, re.S)
    return match.group(0) if match else ""


def versioned(path: str) -> str:
    """A stylesheet's or script's address as the pages give it: its path (from the site's root) and the first 8 hex
    digits of the file's hash, line endings as committed."""
    data = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    return f"{path}?v={hashlib.sha256(data).hexdigest()[:8]}"
