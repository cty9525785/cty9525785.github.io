"""Render the site's pages from content/*.toml into static HTML."""
import hashlib
import html
import re
import sys
from datetime import date
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # lets `python tools/build.py` import the tools package
    sys.path.insert(0, str(ROOT))

from tools.content import (  # noqa: E402
    LICENSES, PLACEHOLDER, NewsItem, OtherPub, Paper, Site, check_news, check_topics, credit_line, home_order,
    load_news, load_papers, load_site, movie_file, poster_file,
)

TEMPLATES = ROOT / "templates"
# The hero's buttons and the footer's links, in order; the CV opens from the menu bar.
CONTACTS = (("email", "Email"), ("scholar", "Google Scholar"), ("linkedin", "LinkedIn"))
ICONS = {
    "email": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/>'
             '<path d="m3 7 9 6 9-6"/></svg>',
    "scholar": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 9.5 12 5l10 4.5L12 14z"/>'
               '<path d="M6 11.5V16c0 1.4 2.7 3 6 3s6-1.6 6-3v-4.5"/></svg>',
    "linkedin": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/>'
                '<path d="M8 10.5V17M8 7.5v.01M12 17v-6.5M12 13.5a2.5 2.5 0 0 1 5 0V17"/></svg>',
}
MEDIA_CREDIT = ("Movies and figures are from, or adapted from, the papers credited on each paper’s page "
                "or linked from each entry.")


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def _template(name: str) -> Template:
    return Template((TEMPLATES / name).read_text(encoding="utf-8"))


def _versioned(path: str) -> str:
    """A stylesheet's or script's address (from the site's root) with its file's hash. GitHub Pages lets a browser
    keep a file ten minutes, so a changed file needs a new address to arrive with the page that needs it (Tianyu saw
    the new page in the old stylesheet)."""
    data = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")  # the hash of the file as committed
    return f"{path}?v={hashlib.sha256(data).hexdigest()[:8]}"


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


EXTERNAL_LINK = re.compile(r'<a\b([^>]*?)\bhref="(https?://[^"]*)"([^>]*)>')


def _new_tabs(text: str, own: str = "") -> str:
    """Links that leave the site open in a new tab (Tianyu: "for link outside my own site, open in new tab");
    noopener keeps the opened page from reaching back into this one. Links already given a target stay as they are."""
    def tab(m: re.Match) -> str:
        if "target=" in m.group(0) or (own and m.group(2).startswith(own)):
            return m.group(0)
        return f'<a{m.group(1)}href="{m.group(2)}" target="_blank" rel="noopener"{m.group(3)}>'
    return EXTERNAL_LINK.sub(tab, text)


def read_body(root: Path, slug: str) -> str:
    """A paper page's own text and figures, written for papers/<slug>/index.html."""
    return _new_tabs((Path(root) / "content" / "pages" / f"{slug}.html").read_text(encoding="utf-8"))


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


def _pdf_button(paper: Paper) -> str:
    """The top bar's button to the hosted PDF of an open-access paper."""
    if not paper.pdf:
        return ""
    return f'\n        <a class="btn" href="../../{esc(paper.pdf)}" target="_blank" rel="noopener">PDF</a>'


def render_paper(paper: Paper, site: Site, body: str) -> str:
    movies = _movies_section(paper, body)
    toc = _toc(body + movies) + '\n        <li><a href="#bibtex">BibTeX</a></li>'
    description = paper.title if _is_placeholder(paper.one_line) else paper.one_line
    return _new_tabs(_template("article.html").substitute(
        page_title=esc(f"{paper.title} | {site.name}"),
        description=esc(description),
        home_name=esc(site.name),
        page_url=esc(f"{site.url}/papers/{paper.slug}/index.html"),
        image_url=esc(f"{site.url}/media/{paper.slug}/loop-poster.jpg" if paper.tile else
                      f"{site.url}/assets/img/social-card.jpg"),
        short_title=esc(paper.short_title),
        doi_url=esc(f"https://doi.org/{paper.doi}"),
        pdf_button=_pdf_button(paper),
        toc=toc,
        title=esc(paper.title),
        authors=_article_authors(paper),
        affiliations=_affiliations(paper),
        contact=_contact(paper),
        venue=venue_html(paper.citation) + _badge(paper.summary_status),
        body=body.rstrip("\n"),
        movies=movies,
        bibtex=esc(paper.bibtex.strip()),
        counter=_counter(site, "../../"),
        article_css="../../" + _versioned("assets/css/article.css"),
        article_js="../../" + _versioned("assets/js/article.js"),
    ), site.url)


def _counter(site: Site, root: str = "") -> str:
    """GoatCounter's script, the site's own reviewed copy, once its count address is set (Tianyu chose it)."""
    if not site.goatcounter:
        return ""
    return (f'<script data-goatcounter="{esc(site.goatcounter)}" async '
            f'src="{root}{_versioned("assets/js/count.js")}"></script>')


def _link(key: str, value: str, label: str, cls: str = "") -> str:
    """An anchor to one of the site's links, or a placeholder that says what is still missing."""
    if _is_placeholder(value):
        return f'<a class="{(cls + " placeholder").strip()}" href="#" title="{esc(value)}">{label}</a>'
    href = f"mailto:{value}" if key == "email" else value
    attr = f' class="{cls}"' if cls else ""
    return f'<a{attr} href="{esc(href)}">{label}</a>'


def _row_media(paper: Paper | OtherPub) -> str:
    """The row's tile, or its figure for a paper without one; Tianyu wants no label on either."""
    media = f"media/{paper.slug}/"
    if paper.tile is None:
        return f'<img src="{media}thumb.jpg" alt="Figure from {esc(paper.title)}" loading="lazy">'
    # Loaded only as it nears the screen (home.js), not all 20 clips at once.
    return (f'<video muted loop playsinline preload="none" poster="{media}loop-poster.jpg">'
            f'<source src="{media}loop.mp4" type="video/mp4"></video>')


def _title_of(pub: Paper | OtherPub) -> str:
    return pub.short_title or pub.title


def _named(href: str, text: str, title: str) -> str:
    """A link whose visible words stay short ("Paper", "PDF") while a screen reader also hears which paper."""
    return f'<a href="{href}" aria-label="{esc(text)}: {esc(title)}">{text}</a>'


def _hosted(pub: Paper | OtherPub) -> str:
    """An open-access paper's hosted PDF, supplement and license, as links after its others."""
    if not pub.pdf:
        return ""
    links = _named(esc(pub.pdf), "PDF", _title_of(pub))
    if pub.supplement_pdf:
        links += _named(esc(pub.supplement_pdf), "Supplementary", _title_of(pub))
    return links + f'<a class="license" href="{LICENSES[pub.license]}">{esc(pub.license)}</a>'


def _row_authors(paper: Paper | OtherPub) -> str:
    """The row's author list, Tianyu in bold and equal contributors marked, as the paper marks them."""
    authors = author_html(paper.authors, paper.me, paper.equal_contribution)
    return authors + (" (†&nbsp;equal contribution)" if paper.equal_contribution else "")


def _headline(tagline: str) -> str:
    """The tagline, its part after the first comma set lighter: "I design and build robots, <span>guided by ...</span>"."""
    if _is_placeholder(tagline):
        return _text_or_placeholder(tagline)
    head, comma, rest = tagline.partition(", ")
    return f"{esc(head)}{comma}<span>{esc(rest)}</span>" if comma else esc(tagline)


# The menu's tabs, each a page of its own (Tianyu: "i would expect all the tabs has their own page"); the CV follows.
PAGES = (("index.html", "Home"), ("publications.html", "Publications"), ("experience.html", "Experience"))


def _nav(site: Site, here: str = "index.html") -> str:
    """The menu bar, its tab for the page shown marked."""
    cv = _link("cv", site.links["cv"], "CV", "cv") if "cv" in site.links else ""
    current = ' aria-current="page"'
    tabs = "".join(f'<a href="{page}"{current if page == here else ""}>{label}</a>' for page, label in PAGES)
    return ('<header class="nav">\n'
            '  <div class="wrap">\n'
            f'    <a class="brand" href="index.html">{esc(site.name)}</a>\n'
            f'    <nav aria-label="Main">{tabs}</nav>\n'
            f'    {cv}\n'
            '  </div>\n'
            '</header>')


def _button_label(label: str) -> str:
    """A hero button's words. On a phone the three buttons share one row and show only their last word ("Scholar");
    the first words stay for screen readers."""
    first, _, last = label.rpartition(" ")
    return f'<span><span class="first-words">{esc(first)} </span>{esc(last)}</span>' if first else esc(label)


def _hero(site: Site) -> str:
    """The intro Tianyu chose (2026-10-30, option A): the photo large and round with the contact buttons under it;
    beside them the name, role, headline and bio. A blank line in the bio starts a new paragraph."""
    bio = _text_or_placeholder(site.bio) if _is_placeholder(site.bio) else _with_links(site.bio) + _badge(site.bio_status)
    paragraphs = "".join(f"<p>{text}</p>" for text in re.split(r"\n\s*\n", bio.strip()))
    role = f'<span class="role">{esc(site.role)}</span>' if site.role else ""
    buttons = "".join(_link(key, site.links[key], ICONS[key] + _button_label(label),
                            "btn primary" if key == "email" else "btn")
                      for key, label in CONTACTS if key in site.links)
    return ('<section id="hero" class="wrap hero">\n'
            '  <div class="side">\n'
            f'    <img class="portrait" src="{esc(site.photo)}" alt="Photo of {esc(site.name)}">\n'
            f'    <p class="links">{buttons}</p>\n'
            '  </div>\n'
            '  <div class="about">\n'
            f'    <p class="who"><b>{esc(site.name)}</b>{role}</p>\n'
            f'    <h1>{_headline(site.tagline)}</h1>\n'
            f'    <div class="bio" id="bio">{paragraphs}</div>'
            '<button type="button" class="bio-more" aria-expanded="false" aria-controls="bio">Read more</button>\n'
            '  </div>\n'
            '</section>')


def _slide(n: int, pub: Paper | OtherPub, own: bool) -> str:
    """One highlight: its clip or figure and its title link to the paper's page (the explainer for Tianyu's own
    papers, the publisher's for co-authored ones), then the summary, the authors and the paper."""
    title = pub.short_title or pub.title
    link = f"papers/{pub.slug}/index.html" if own else f"https://doi.org/{esc(pub.doi)}"
    media_dir = f"media/{pub.slug}/"
    if pub.tile is None:
        media = f'<img src="{media_dir}thumb.jpg" alt="" loading="lazy">'
        kind = "hl-media still"
    else:  # only the first slide's clip plays at once; the script plays each other one as its slide shows
        play = "autoplay" if n == 1 else 'preload="none"'
        # The poster again as an image over the clip, which the script lifts once the clip plays: a phone that has not
        # loaded the clip yet, or will not play it, shows the still rather than a black frame.
        media = (f'<video {play} muted loop playsinline poster="{media_dir}loop-poster.jpg">'
                 f'<source src="{media_dir}loop.mp4" type="video/mp4"></video>'
                 f'<img class="hl-poster" src="{media_dir}loop-poster.jpg" alt="">')
        kind = "hl-media"
    label = '<p class="label">Co-authored</p>' if not own else ""
    more = ((_named(link, "Read the explainer", title) if own else "")
            + _named(f"https://doi.org/{esc(pub.doi)}", "Paper", title))
    return (f'      <article class="slide{" on" if n == 1 else ""}" id="hl-{n}" data-slug="{pub.slug}">'
            f'<a class="{kind}" href="{link}" tabindex="-1" aria-hidden="true">{media}</a>\n'  # the title is the named link
            f'        <div class="hl-text">{label}<h3><a href="{link}">{esc(title)}</a></h3>'
            f'<p class="one">{esc(pub.one_line)}</p>'
            f'<p class="authors">{_row_authors(pub)}</p>'
            f'<p class="venue"><em>{esc(pub.citation)}</em></p>'
            f'<p class="more">{more}{_hosted(pub)}</p></div>\n'
            f'      </article>')


def _highlights(site: Site, papers: list[Paper], others: list[OtherPub]) -> str:
    """Research highlights, like hyunwooyuk.com's (Tianyu, 2026-10-30): one captioned slide at a time with numbered
    tabs and a pause button. Without the script every slide shows, one under another, and the tabs jump to them."""
    if not site.highlights:
        return ""
    own = {p.slug: p for p in papers}
    pubs = {**{o.slug: o for o in others}, **own}
    slides = "\n".join(_slide(n, pubs[slug], slug in own) for n, slug in enumerate(site.highlights, 1))
    tabs = "".join(f'<a class="hl-tab" href="#hl-{n}" aria-label="{n}: {esc(pubs[slug].short_title or pubs[slug].title)}">'
                   f'{n}</a>' for n, slug in enumerate(site.highlights, 1))
    return ('<section id="highlights" class="wrap highlights">\n'
            '  <div class="hl-head"><h2>Research highlights</h2>'
            '<button type="button" class="hl-pause" aria-pressed="false">Pause</button></div>\n'
            '  <div class="hl">\n'
            f'    <div class="hl-slides">\n{slides}\n    </div>\n'
            f'    <nav class="hl-tabs" aria-label="Highlights">{tabs}</nav>\n'
            '  </div>\n'
            '</section>')


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _covers(slugs: list[str], own: dict[str, Paper], others: dict[str, OtherPub]) -> str:
    """The papers a story covers, in its order, each linked to the publisher's page (Tianyu: "add the url also for
    coauthor papers", "my own paper on the news section also link to publisher directly"); co-authored ones say so."""
    def named(slug: str) -> str:
        pub = own.get(slug) or others[slug]
        title = esc(_title_of(pub))
        link = title if _is_placeholder(pub.doi) else f'<a href="https://doi.org/{esc(pub.doi)}">{title}</a>'
        return link if slug in own else f"{link} (co-authored)"
    return " and ".join(named(slug) for slug in slugs)


def _news_item(item: NewsItem, own: dict[str, Paper], others: dict[str, OtherPub]) -> str:
    year, month, _ = item.date.split("-")
    lang = f' lang="{esc(item.lang)}"' if item.lang else ""
    translation = f'<span class="tr">{esc(item.translation)}</span>' if item.translation else ""
    links = [f'<a href="{esc(p.url)}">{esc(p.outlet)}</a>' for p in item.also]
    also = (f'<p class="also">Also on {", ".join(links[:-1]) + " and " + links[-1] if len(links) > 1 else links[0]}</p>'
            if links else "")  # the same story republished: one item, a link per site (Tianyu, 2026-10-30)
    return (f'      <li class="news-item"><p class="when">{MONTHS[int(month) - 1]} {year}</p>'
            f'<div><a class="headline" href="{esc(item.url)}"{lang}>{esc(item.headline)}</a>{translation}'
            f'<p class="where">{esc(item.outlet)} · on {_covers(item.papers, own, others)}</p>{also}</div></li>')


def _news(news: list[NewsItem], papers: list[Paper], others: list[OtherPub]) -> str:
    """Press coverage, newest first (Tianyu, 2026-10-30): the six newest stories, the rest under All coverage."""
    if not news:
        return ""
    own = {p.slug: p for p in papers}
    other = {o.slug: o for o in others}
    items = [_news_item(n, own, other) for n in sorted(news, key=lambda n: n.date, reverse=True)]
    more = ('  <details class="news-more"><summary>All coverage (' + str(len(items)) + ')</summary>\n'
            '    <ol class="news-list">\n' + "\n".join(items[6:]) + '\n    </ol>\n  </details>\n') if items[6:] else ""
    return ('<section id="news" class="wrap news">\n'
            '  <h2>In the news</h2>\n'
            '  <ol class="news-list">\n' + "\n".join(items[:6]) + '\n  </ol>\n'
            + more + '</section>')


def _experience(site: Site) -> str:
    """The Experience page: the roles as a timeline beside the degrees, then the skills."""
    if not (site.experience or site.education or site.skills):
        return ""
    roles = "\n".join(f'      <li><p class="when">{esc(r.years)}</p><h3>{esc(r.role)} <span class="org">· {esc(r.org)}</span>'
                      f'</h3><p>{esc(r.text)}</p></li>' for r in site.experience)
    degrees = "\n".join(f'        <li><b>{esc(d.degree)}</b><span>{esc(d.school)}, {esc(d.year)}</span></li>'
                        for d in site.education)
    skills = "\n".join(f'    <div class="skill"><h4>{esc(g.name)}</h4>'
                       + "".join(f"<span>{esc(item)}</span>" for item in g.items) + "</div>" for g in site.skills)
    return ('<section id="experience" class="wrap">\n'
            '  <div class="split">\n'
            '    <div class="side">\n'
            f'      <h1>Experience{_badge(site.cv_status)}</h1>\n'
            f'      <h3 class="edu-h">Education</h3>\n      <ul class="edu">\n{degrees}\n      </ul>\n'
            '    </div>\n'
            f'    <ol class="xp">\n{roles}\n    </ol>\n'
            '  </div>\n'
            f'  <div class="skills">\n{skills}\n  </div>\n'
            '</section>')


def _pub_entry(paper: Paper) -> str:
    """One of Tianyu's own papers in the Publications list; it links to its explainer page and the paper."""
    page = f"papers/{paper.slug}/index.html"
    one_line = _text_or_placeholder(paper.one_line) + _badge(paper.summary_status)
    return (f'      <li class="pub" data-slug="{paper.slug}">\n'
            f'        <a class="thumb" href="{page}" tabindex="-1" aria-hidden="true">{_row_media(paper)}</a>\n'
            f'        <div class="txt">\n'
            f'          <a class="title" href="{page}">{esc(paper.title)}</a>\n'
            f'          <p class="authors">{_row_authors(paper)}</p>\n'
            f'          <p class="venue"><em>{esc(paper.citation)}</em></p>\n'
            f'          <p class="one">{one_line}</p>\n'
            f'          <p class="more">{_named(page, "Explainer", paper.short_title)}'
            f'{_named(f"https://doi.org/{esc(paper.doi)}", "Paper", paper.short_title)}{_hosted(paper)}</p>\n'
            f'        </div>\n'
            f'      </li>')


def _other_entry(pub: OtherPub) -> str:
    """A co-authored paper in the Publications list: its figure, title and link all go to the publisher."""
    if pub.tile is not None:
        media = _row_media(pub)
    elif _is_placeholder(pub.thumb):
        media = f'<span class="placeholder">{esc(pub.thumb)}</span>'
    else:
        media = f'<img src="media/{pub.slug}/thumb.jpg" alt="Figure from {esc(pub.title)}" loading="lazy">'
    if _is_placeholder(pub.doi):
        thumb = f'<span class="thumb">{media}</span>'
        title = f'<span class="title">{esc(pub.title)}</span> <span class="placeholder">{esc(pub.doi)}</span>'
        more = ""
    else:
        doi = f"https://doi.org/{esc(pub.doi)}"
        thumb = f'<a class="thumb" href="{doi}" tabindex="-1" aria-hidden="true">{media}</a>'
        title = f'<a class="title" href="{doi}">{esc(pub.title)}</a>'
        more = f'\n          <p class="more">{_named(doi, "Paper", _title_of(pub))}{_hosted(pub)}</p>'
    one_line = _text_or_placeholder(pub.one_line) + _badge(pub.summary_status)
    return (f'      <li class="pub" data-slug="{pub.slug}">\n'
            f'        {thumb}\n'
            f'        <div class="txt">\n'
            f'          {title}\n'
            f'          <p class="authors">{_row_authors(pub)}</p>\n'
            f'          <p class="venue"><em>{esc(pub.citation)}</em></p>\n'
            f'          <p class="one">{one_line}</p>{more}\n'
            f'        </div>\n'
            f'      </li>')


def _publications(site: Site, papers: list[Paper], others: list[OtherPub]) -> str:
    """The Publications page's list, all papers by topic: Tianyu's own first, then the co-authored ones, under a
    filter that works without JS."""
    chips = ['<a class="chip on" href="#publications" data-topic="all">All</a>'] + [
        f'<a class="chip" href="#topic-{t.id}" data-topic="{t.id}">{esc(t.label)}</a>' for t in site.topics]
    order = home_order(papers)
    groups = []
    for t in site.topics:
        items = [_pub_entry(p) for p in order if p.topic == t.id]
        co = [_other_entry(o) for o in others if o.topic == t.id]
        if co:
            items += ['      <li class="co-label">Co-authored</li>', *co]
        groups.append(f'    <div class="topic" id="topic-{t.id}" data-topic="{t.id}">\n'
                      f'      <h3>{esc(t.heading)}</h3>\n'
                      f'      <ul class="pubs">\n' + "\n".join(items) + '\n      </ul>\n'
                      f'    </div>')
    return ('<section id="publications" class="band">\n'
            '  <div class="wrap">\n'
            '    <div class="head"><div><h1>Publications</h1></div>\n'
            f'      <nav class="filters" aria-label="Topics">{"".join(chips)}</nav></div>\n'
            + "\n".join(groups) + '\n'
            '  </div>\n'
            '</section>')


def _footer(site: Site) -> str:
    """The page ends with an invitation that shows the address itself, which a reader without a mail app can copy."""
    email = site.links.get("email", "")
    shown = email and not _is_placeholder(email)
    contact = f'    <p class="contact">Get in touch: {_link("email", email, esc(email))}</p>\n' if shown else ""
    links = " · ".join(_link(key, site.links[key], label) for key, label in CONTACTS
                       if key in site.links and not (shown and key == "email"))
    return ('<footer>\n'
            '  <div class="wrap">\n'
            + contact +
            f'    <p>© {date.today().year} {esc(site.name)} · {links}</p>\n'
            f'    <p class="credit">{MEDIA_CREDIT}</p>\n'
            '  </div>\n'
            '</footer>')


def render_home(site: Site, papers: list[Paper], others: list[OtherPub], news: list[NewsItem] = ()) -> str:
    check_topics(site, papers, others)
    check_news(list(news), papers, others)
    return _new_tabs(_template("home.html").substitute(
        name=esc(site.name),
        site_url=esc(site.url),
        tagline_text=esc(site.tagline),
        nav=_nav(site),
        hero=_hero(site),
        highlights=_highlights(site, papers, others),
        news=_news(list(news), papers, others),
        footer=_footer(site),
        counter=_counter(site),
        home_css=_versioned("assets/css/home.css"),
        home_js=_versioned("assets/js/home.js"),
    ), site.url)


def _page(site: Site, page: str, title: str, description: str, main: str, script: str = "") -> str:
    """One of the menu's pages besides Home, under the same menu, styles and footer."""
    return _new_tabs(_template("page.html").substitute(
        name=esc(site.name),
        site_url=esc(site.url),
        tagline_text=esc(site.tagline),
        page=page,
        title=esc(title),
        description=esc(description),
        nav=_nav(site, page),
        main=main,
        footer=_footer(site),
        script=f'<script src="{_versioned(script)}" defer></script>' if script else "",
        counter=_counter(site),
        home_css=_versioned("assets/css/home.css"),
    ), site.url)


def render_publications(site: Site, papers: list[Paper], others: list[OtherPub]) -> str:
    """The Publications page: every paper by topic, with the filters and clips home.js runs."""
    check_topics(site, papers, others)
    return _page(site, "publications.html", "Publications", f"Papers by {site.name}, grouped by topic.",
                 _publications(site, papers, others), "assets/js/home.js")


def render_experience(site: Site) -> str:
    """The Experience page: roles, degrees and skills."""
    return _page(site, "experience.html", "Experience", f"{site.name}’s roles, education and skills.",
                 _experience(site))


def build(root: Path = ROOT) -> list[Path]:
    """Write the menu's pages (index.html, publications.html, experience.html) and papers/<slug>/index.html under
    root; return the written paths."""
    site = load_site(root / "content" / "site.toml")
    papers, others = load_papers(root / "content" / "papers.toml")
    news_file = root / "content" / "news.toml"
    news = load_news(news_file) if news_file.exists() else []
    pages = {root / "index.html": render_home(site, papers, others, news),
             root / "publications.html": render_publications(site, papers, others),
             root / "experience.html": render_experience(site)}
    for paper in papers:
        pages[root / "papers" / paper.slug / "index.html"] = render_paper(paper, site, read_body(root, paper.slug))
    for path, text in pages.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return list(pages)


if __name__ == "__main__":
    for written in build(ROOT):
        print(written.relative_to(ROOT).as_posix())
