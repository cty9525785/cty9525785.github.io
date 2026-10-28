"""Small HTML helpers for the tests (stdlib html.parser and regex)."""
import re
from html.parser import HTMLParser


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
