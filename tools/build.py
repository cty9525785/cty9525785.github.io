"""Render the site's pages from content/*.toml into static HTML."""
import html
import re
import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # lets `python tools/build.py` import the tools package
    sys.path.insert(0, str(ROOT))

from tools.content import (  # noqa: E402
    PLACEHOLDER, OtherPub, Paper, Site, credit_line, home_order, load_papers, load_site, movie_file, poster_file,
)

TEMPLATES = ROOT / "templates"
LINK_LABELS = {"email": "Email", "cv": "CV", "scholar": "Scholar", "linkedin": "LinkedIn", "github": "GitHub"}


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def _template(name: str) -> Template:
    return Template((TEMPLATES / name).read_text(encoding="utf-8"))


def _badge(status: str) -> str:
    return ' <span class="draft">draft</span>' if status == "draft" else ""


def _is_placeholder(value: str) -> bool:
    return value.startswith(PLACEHOLDER)


LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _with_links(text: str) -> str:
    """Escaped text in which [label](https://...) becomes a link."""
    return LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', esc(text))


def _text_or_placeholder(value: str) -> str:
    return f'<span class="placeholder">{esc(value)}</span>' if _is_placeholder(value) else esc(value)


def author_html(authors: list[str], me: int, equal: list[str]) -> str:
    """Comma-separated authors, Tianyu in bold, equal contributors marked with a dagger."""
    parts = []
    for i, name in enumerate(authors, 1):
        label = esc(name) + ("†" if name in equal else "")
        parts.append(f"<strong>{label}</strong>" if i == me else label)
    return ", ".join(parts)


SECTION = re.compile(r'<section id="([^"]+)"[^>]*>\s*<h2[^>]*>(.*?)</h2>', re.S)
VENUE = re.compile(r"^(.*?) (\d.*)$")


def read_body(root: Path, slug: str) -> str:
    """A paper page's own text and figures, written for papers/<slug>/index.html."""
    return (Path(root) / "content" / "pages" / f"{slug}.html").read_text(encoding="utf-8")


def _toc(html_text: str) -> str:
    """One contents entry per section, labeled as its heading reads, "1&nbsp; Working principle"."""
    items = []
    for sid, heading in SECTION.findall(html_text):
        label = re.sub(r'<a class="anchor".*?</a>', "", heading, flags=re.S)
        label = re.sub(r'<span class="num">(\d+)</span>\s*', r"\1&nbsp; ", label)
        label = re.sub(r"<[^>]+>", "", label).strip()
        items.append(f'        <li><a href="#{sid}">{label}</a></li>')
    return "\n".join(items)


def _article_authors(paper: Paper) -> str:
    """Names kept whole on one line; superscripts give affiliation numbers (when there are several), † for equal
    contribution and * for the corresponding author."""
    numbered = len(paper.affiliations) > 1
    parts = []
    for i, name in enumerate(paper.authors):
        label = esc(name).replace(" ", "&nbsp;")
        if i + 1 == paper.me:
            label = f'<span class="me">{label}</span>'
        marks = [str(n) for n in paper.affiliation_of[i]] if numbered else []
        if name in paper.equal_contribution:
            marks.append("†")
        if name in paper.corresponding:
            marks.append("*")
        parts.append(label + (f"<sup>{','.join(marks)}</sup>" if marks else ""))
    return ", ".join(parts)


def _affiliations(paper: Paper) -> str:
    if len(paper.affiliations) == 1:
        return esc(paper.affiliations[0])
    return "<br>\n          ".join(f"<sup>{n}</sup>{esc(a)}" for n, a in enumerate(paper.affiliations, 1))


def _contact(paper: Paper) -> str:
    """The corresponding author's email, the only one a page shows."""
    lines = ["<sup>†</sup>Equal contribution"] if paper.equal_contribution else []
    label = "Corresponding author" if len(paper.corresponding) == 1 else "Corresponding authors"
    emails = ", ".join(f'<a href="mailto:{esc(e)}">{esc(e)}</a>' for e in paper.corresponding.values())
    lines.append(f"<sup>*</sup>{label}: {emails}")
    return "<br>".join(lines)


def venue_html(citation: str) -> str:
    """The journal's name in italics, then volume, pages and year."""
    match = VENUE.match(citation)
    return f"<i>{esc(match.group(1))}</i> {esc(match.group(2))}" if match else esc(citation)


def _movies_section(paper: Paper, body: str) -> str:
    """The paper's published movies that the page's text does not already show, in full."""
    media = f"../../media/{paper.slug}/"
    movies = [m for m in paper.movies if m.publish and f"{media}{movie_file(m)}" not in body]
    if not movies:
        return ""
    head = ('      <section id="movies">\n'
            '        <h2>Movies <a class="anchor" href="#movies" aria-label="Link to this section">#</a></h2>\n')
    if paper.media_mode == "link":
        items = "\n".join(f"          <li>{esc(m.caption)}</li>" for m in movies)
        return (head + f'        <p>The paper’s movies are on <a href="{esc(paper.supplementary_url)}" target="_blank" '
                f'rel="noopener">the journal’s site</a>.</p>\n        <ul>\n{items}\n        </ul>\n      </section>\n')
    figures = "\n".join(
        f'          <figure class="fig">\n'
        f'            <video controls preload="none" playsinline poster="{media}{poster_file(m)}">'
        f'<source src="{media}{movie_file(m)}" type="video/mp4"></video>\n'
        f'            <figcaption>{esc(m.caption)} <span class="credit">{esc(m.credit or credit_line(paper))}</span>'
        f'</figcaption>\n'
        f'          </figure>'
        for m in movies)
    return (head + "        <p>The paper’s movies in full.</p>\n"
            f'        <div class="demo-grid">\n{figures}\n        </div>\n      </section>\n')


def render_paper(paper: Paper, site: Site, body: str) -> str:
    movies = _movies_section(paper, body)
    toc = _toc(body + movies) + '\n        <li><a href="#bibtex">BibTeX</a></li>'
    description = paper.title if _is_placeholder(paper.one_line) else paper.one_line
    return _template("article.html").substitute(
        page_title=esc(f"{paper.title} | {site.name}"),
        description=esc(description),
        home_name=esc(site.name),
        page_url=esc(f"{site.url}/papers/{paper.slug}/index.html"),
        image_url=esc(f"{site.url}/media/{paper.slug}/loop-poster.jpg" if paper.tile else
                      f"{site.url}/assets/img/social-card.jpg"),
        short_title=esc(paper.short_title),
        doi_url=esc(f"https://doi.org/{paper.doi}"),
        toc=toc,
        title=esc(paper.title),
        authors=_article_authors(paper),
        affiliations=_affiliations(paper),
        contact=_contact(paper),
        venue=venue_html(paper.citation) + _badge(paper.summary_status),
        body=body.rstrip("\n"),
        movies=movies,
        bibtex=esc(paper.bibtex.strip()),
    )


def _links(site: Site) -> str:
    parts = []
    for key, label in LINK_LABELS.items():
        if key not in site.links:
            continue
        value = site.links[key]
        if _is_placeholder(value):
            parts.append(f'<a class="placeholder" href="#" title="{esc(value)}">{label}</a>')
        else:
            href = f"mailto:{value}" if key == "email" else value
            parts.append(f'<a href="{esc(href)}">{label}</a>')
    return " &nbsp;/&nbsp; ".join(parts)


def _row_media(paper: Paper | OtherPub) -> str:
    """The row's tile, or its figure for a paper without one; Tianyu wants no label on either."""
    media = f"media/{paper.slug}/"
    if paper.tile is None:
        return f'<img src="{media}thumb.jpg" alt="Figure from {esc(paper.title)}" loading="lazy">'
    return (f'<video autoplay muted loop playsinline poster="{media}loop-poster.jpg">'
            f'<source src="{media}loop.mp4" type="video/mp4"></video>')


def _row_authors(paper: Paper | OtherPub) -> str:
    """The row's author list, Tianyu in bold and equal contributors marked, as the paper marks them."""
    authors = author_html(paper.authors, paper.me, paper.equal_contribution)
    return authors + (" (†&nbsp;equal contribution)" if paper.equal_contribution else "")


def _row(paper: Paper) -> str:
    row_class = "paper-row highlight" if paper.highlight else "paper-row"
    page = f"papers/{paper.slug}/index.html"
    authors = _row_authors(paper)
    one_line = _text_or_placeholder(paper.one_line) + _badge(paper.summary_status)
    return (f'      <tr class="{row_class}" data-slug="{paper.slug}">\n'
            f'        <td class="media"><a href="{page}">{_row_media(paper)}</a></td>\n'
            f'        <td class="text">\n'
            f'          <a href="{page}"><span class="papertitle">{esc(paper.title)}</span></a><br>\n'
            f'          {authors}<br>\n'
            f'          <em>{esc(paper.citation)}</em><br>\n'
            f'          <a href="{page}">page</a> / <a href="https://doi.org/{esc(paper.doi)}">paper</a>\n'
            f'          <p>{one_line}</p>\n'
            f'        </td>\n'
            f'      </tr>')


def _other_row(pub: OtherPub) -> str:
    """A co-authored paper's row: like a paper's, but its figure, title and link all go to the publisher."""
    if pub.tile is not None:
        media = _row_media(pub)
    elif _is_placeholder(pub.thumb):
        media = f'<span class="placeholder">{esc(pub.thumb)}</span>'
    else:
        media = f'<img src="media/{pub.slug}/thumb.jpg" alt="Figure from {esc(pub.title)}" loading="lazy">'
    title = f'<span class="papertitle">{esc(pub.title)}</span>'
    if _is_placeholder(pub.doi):
        cell, title, link = media, f'{title} <span class="placeholder">{esc(pub.doi)}</span>', ""
    else:
        doi = f"https://doi.org/{esc(pub.doi)}"
        cell, title, link = f'<a href="{doi}">{media}</a>', f'<a href="{doi}">{title}</a>', f'<a href="{doi}">paper</a>'
    one_line = _text_or_placeholder(pub.one_line) + _badge(pub.summary_status)
    return (f'      <tr class="paper-row" data-slug="{pub.slug}">\n'
            f'        <td class="media">{cell}</td>\n'
            f'        <td class="text">\n'
            f'          {title}<br>\n'
            f'          {_row_authors(pub)}<br>\n'
            f'          <em>{esc(pub.citation)}</em><br>\n'
            f'          {link}\n'
            f'          <p>{one_line}</p>\n'
            f'        </td>\n'
            f'      </tr>')


def render_home(site: Site, papers: list[Paper], others: list[OtherPub]) -> str:
    return _template("home.html").substitute(
        name=esc(site.name),
        site_url=esc(site.url),
        tagline=_text_or_placeholder(site.tagline),
        tagline_text=esc(site.tagline),
        bio=_text_or_placeholder(site.bio) if _is_placeholder(site.bio) else _with_links(site.bio) + _badge(site.bio_status),
        links=_links(site),
        photo=esc(site.photo),
        rows="\n".join(_row(p) for p in home_order(papers)),
        others="\n".join(_other_row(o) for o in others),
    )


def build(root: Path = ROOT) -> list[Path]:
    """Write index.html and papers/<slug>/index.html under root; return the written paths."""
    site = load_site(root / "content" / "site.toml")
    papers, others = load_papers(root / "content" / "papers.toml")
    pages = {root / "index.html": render_home(site, papers, others)}
    for paper in papers:
        pages[root / "papers" / paper.slug / "index.html"] = render_paper(paper, site, read_body(root, paper.slug))
    for path, text in pages.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return list(pages)


if __name__ == "__main__":
    for written in build(ROOT):
        print(written.relative_to(ROOT).as_posix())
