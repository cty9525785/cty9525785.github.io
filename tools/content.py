"""Content model: load the site and paper TOML files, validate them, and derive what the pages need."""
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PLACEHOLDER = "TODO:"

MEDIA_MODES = {"embed", "link"}
PROCESSES = {"copy", "remux", "reencode1080", "silent1080", "none"}
SUMMARY_STATUSES = {"draft", "confirmed"}
TILE_KINDS = {"clip", "drawing"}
# The licenses under which the site may host a paper's PDF, each with its deed; the publishers keep the other papers.
LICENSES = {"CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
            "CC BY-NC 4.0": "https://creativecommons.org/licenses/by-nc/4.0/"}
HOSTED_FOLDER = "files/papers/"


@dataclass
class Movie:
    id: str
    source: str
    process: str
    caption: str
    poster_at: float | None = None
    source_speed: float = 1.0  # speed-up already in the movie, as its on-screen label says
    credit: str = ""  # replaces the paper's credit line, for recordings not published with the paper
    publish: bool = True  # false: no web copy; the page shows clips cut from it, and a tile reads the original


@dataclass
class SourceMovie:
    """A published movie a co-authored row's loop is cut from; the site shows only the loop."""
    id: str
    source: str
    source_speed: float = 1.0  # speed-up already in the movie, as its on-screen label says


@dataclass
class TileInput:
    movie: str
    start: float
    duration: float


@dataclass
class Segment:
    at: float  # seconds into the loop
    speed: float  # true speed of the footage on screen, counting the movie's own speed-up


@dataclass
class Tile:
    """The home page loop: cut from the paper's movies by an ffmpeg graph, or drawn."""
    kind: str
    graph: str = ""  # clip: filtergraph in tools/tiles/, whose input i is inputs[i]
    inputs: list[TileInput] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)  # clip: when each speed starts
    drawing: str = ""  # drawing: a name in tools/drawings.py
    poster_at: float = 0.0


@dataclass
class Figure:
    pdf: str
    page: int


@dataclass
class Paper:
    slug: str
    title: str
    short_title: str  # for the page's top bar
    authors: list[str]
    me: int
    equal_contribution: list[str]
    affiliations: list[str]  # as printed on the paper's first page
    affiliation_of: list[list[int]]  # each author's affiliation numbers, counting from 1
    corresponding: dict[str, str]  # corresponding author: email, the only emails a page shows
    citation: str
    date: str
    doi: str
    highlight: bool
    media_mode: str
    supplementary_url: str
    summary_status: str  # "draft" until Tianyu confirms the page's text
    one_line: str
    tile: Tile | None
    bibtex: str
    movies: list[Movie]
    figure: Figure | None = None  # tools/figures.py cuts Figure 1 for a paper that has no tile
    topic: str = ""  # one of the site's topic ids
    pdf: str = ""  # an open-access paper's PDF, hosted under files/papers/
    supplement_pdf: str = ""  # its supplementary materials, hosted beside it
    license: str = ""  # the license the paper prints, one of LICENSES; required to host it


@dataclass
class OtherPub:
    """A co-authored paper: a home page row that points to the publisher, with no page of its own."""
    slug: str  # names its folder in media/, which holds thumb.jpg
    authors: list[str]
    me: int
    title: str
    citation: str
    doi: str
    one_line: str
    summary_status: str
    thumb: str = ""  # empty when media/<slug>/thumb.jpg exists or a tile plays; a TODO: placeholder says what is missing
    equal_contribution: list[str] = field(default_factory=list)  # as the paper's note names them
    tile: Tile | None = None  # a clip of the paper's movies, played instead of its figure
    movies: list[SourceMovie] = field(default_factory=list)  # what the tile is cut from
    topic: str = ""  # one of the site's topic ids
    pdf: str = ""  # as for Paper
    supplement_pdf: str = ""
    license: str = ""
    short_title: str = ""  # its slide's title, when it is one of the site's highlights


@dataclass
class Platform:
    outlet: str
    url: str


@dataclass
class NewsItem:
    """A story about one or more of the papers, as its source titled it."""
    date: str  # YYYY-MM-DD
    outlet: str
    headline: str
    url: str
    papers: list[str]  # slugs, in the order the story features them
    lang: str = ""  # the headline's language when it is not English, such as "zh"
    translation: str = ""  # the headline in English, required with lang
    also: list[Platform] = field(default_factory=list)  # other sites that republished the same story


@dataclass
class Topic:
    """A research topic: the home page groups the publications by it and filters them with its label."""
    id: str
    label: str
    heading: str


@dataclass
class Role:
    years: str
    role: str
    org: str
    text: str


@dataclass
class Degree:
    year: str
    degree: str
    school: str


@dataclass
class SkillGroup:
    name: str
    items: list[str]


@dataclass
class Site:
    name: str
    tagline: str
    bio: str
    photo: str
    links: dict[str, str]
    bio_status: str = "draft"  # a drafted bio stays a draft until Tianyu confirms it
    url: str = ""  # the site's own address, for link previews; no trailing slash
    role: str = ""  # the current position, beside the name
    topics: list[Topic] = field(default_factory=list)
    experience: list[Role] = field(default_factory=list)
    education: list[Degree] = field(default_factory=list)
    skills: list[SkillGroup] = field(default_factory=list)
    cv_status: str = "draft"  # experience, education and skills stay a draft until Tianyu confirms them
    highlights: list[str] = field(default_factory=list)  # the slideshow's papers by slug, in order
    goatcounter: str = ""  # GoatCounter's count address, https://CODE.goatcounter.com/count; empty: no counting


def _read(path: Path) -> dict:
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))


def _check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_site(path: Path) -> Site:
    data = _read(path)
    try:
        site = Site(data["name"], data["tagline"], data["bio"], data["photo"], dict(data["links"]),
                    data.get("bio_status", "draft"), data.get("url", ""), data.get("role", ""),
                    [Topic(**t) for t in data.get("topic", [])], [Role(**r) for r in data.get("experience", [])],
                    [Degree(**d) for d in data.get("education", [])], [SkillGroup(**g) for g in data.get("skills", [])],
                    data.get("cv_status", "draft"), list(data.get("highlights", [])), data.get("goatcounter", ""))
    except TypeError as err:
        raise ValueError(f"site: {err}") from err
    _check(site.bio_status in SUMMARY_STATUSES, f"site: unknown bio_status {site.bio_status!r}")
    _check(site.cv_status in SUMMARY_STATUSES, f"site: unknown cv_status {site.cv_status!r}")
    _check(not site.url or (site.url.startswith("https://") and not site.url.endswith("/")),
           f"site: url {site.url!r} must start with https:// and have no trailing slash")
    _check(not site.goatcounter or re.fullmatch(r"https://[a-z0-9-]+\.goatcounter\.com/count", site.goatcounter),
           f"site: goatcounter {site.goatcounter!r} must be https://CODE.goatcounter.com/count")
    return site


def _tile(raw: dict) -> Tile:
    inputs = [TileInput(**i) for i in raw.get("inputs", [])]
    segments = [Segment(**s) for s in raw.get("segments", [])]
    return Tile(**{k: v for k, v in raw.items() if k not in ("inputs", "segments")}, inputs=inputs, segments=segments)


def _check_tile(slug: str, tile: Tile, movie_ids: set[str]) -> None:
    _check(tile.kind in TILE_KINDS, f"{slug}: unknown tile kind {tile.kind!r}")
    if tile.kind == "drawing":
        _check(bool(tile.drawing), f"{slug}: a drawn tile needs a drawing name")
        return
    _check(bool(tile.graph) and bool(tile.inputs), f"{slug}: a clip tile needs a graph and its inputs")
    for i in tile.inputs:
        _check(i.movie in movie_ids, f"{slug}: tile input {i.movie!r} is not one of the paper's movies")
    ats = [s.at for s in tile.segments]
    _check(bool(ats) and ats[0] == 0 and ats == sorted(set(ats)), f"{slug}: tile segments must start at 0, in order")
    _check(all(s.speed > 0 for s in tile.segments), f"{slug}: tile speeds must be positive")


def _check_hosted(pub: Paper | OtherPub) -> None:
    if not (pub.pdf or pub.supplement_pdf):
        return
    _check(pub.license in LICENSES, f"{pub.slug}: a hosted PDF needs an open license, one of {sorted(LICENSES)}")
    _check(bool(pub.pdf), f"{pub.slug}: a supplement is hosted only beside its paper")
    for path in filter(None, (pub.pdf, pub.supplement_pdf)):
        _check(path.startswith(HOSTED_FOLDER) and path.endswith(".pdf"),
               f"{pub.slug}: {path!r} must be a PDF in {HOSTED_FOLDER}")


def _paper(raw: dict) -> Paper:
    slug = raw.get("slug", "?")
    try:
        movies = [Movie(**m) for m in raw.get("movie", [])]
        tile = _tile(raw["tile"]) if "tile" in raw else None
        figure = Figure(**raw["figure"]) if "figure" in raw else None
        fields = {k: v for k, v in raw.items() if k not in ("movie", "tile", "figure")}
        paper = Paper(**fields, figure=figure, tile=tile, movies=movies)
    except TypeError as err:
        raise ValueError(f"{slug}: {err}") from err
    _check(paper.media_mode in MEDIA_MODES, f"{slug}: unknown media_mode {paper.media_mode!r}")
    _check(paper.summary_status in SUMMARY_STATUSES, f"{slug}: unknown summary_status {paper.summary_status!r}")
    _check(1 <= paper.me <= len(paper.authors), f"{slug}: me={paper.me} is outside the author list")
    _check(set(paper.equal_contribution) <= set(paper.authors), f"{slug}: equal contributors must be among the authors")
    _check(len(paper.affiliation_of) == len(paper.authors) and all(paper.affiliation_of),
           f"{slug}: every author needs their affiliation numbers")
    used = {n for numbers in paper.affiliation_of for n in numbers}
    _check(used == set(range(1, len(paper.affiliations) + 1)),
           f"{slug}: affiliation numbers must cover 1 to {len(paper.affiliations)} exactly")
    _check(bool(paper.corresponding) and set(paper.corresponding) <= set(paper.authors),
           f"{slug}: corresponding authors must be among the authors")
    for m in movies:
        _check(m.process in PROCESSES, f"{slug} {m.id}: unknown process {m.process!r}")
        _check(not (paper.media_mode == "embed" and m.process == "none"),
               f"{slug} {m.id}: an embedded paper needs a source for every movie")
    if tile is not None:
        _check_tile(slug, tile, {m.id for m in movies})
    _check_hosted(paper)
    return paper


def load_papers(path: Path) -> tuple[list[Paper], list[OtherPub]]:
    data = _read(path)
    papers = [_paper(raw) for raw in data.get("paper", [])]
    slugs = [p.slug for p in papers]
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    _check(not dupes, f"duplicate slugs: {dupes}")
    others = []
    for raw in data.get("other", []):
        try:
            movies = [SourceMovie(**m) for m in raw.get("movie", [])]
            tile = _tile(raw["tile"]) if "tile" in raw else None
            fields = {k: v for k, v in raw.items() if k not in ("movie", "tile")}
            others.append(OtherPub(**fields, tile=tile, movies=movies))
        except TypeError as err:
            raise ValueError(f"{raw.get('slug', raw.get('title', '?'))}: {err}") from err
    for o in others:
        _check(1 <= o.me <= len(o.authors), f"{o.slug}: me={o.me} is outside the author list")
        _check(set(o.equal_contribution) <= set(o.authors), f"{o.slug}: equal contributors must be among the authors")
        _check(o.summary_status in SUMMARY_STATUSES, f"{o.slug}: unknown summary_status {o.summary_status!r}")
        if o.tile is not None:
            _check_tile(o.slug, o.tile, {m.id for m in o.movies})
        _check_hosted(o)
    slugs += [o.slug for o in others]
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    _check(not dupes, f"duplicate slugs: {dupes}")
    return papers, others


def movie_file(movie: Movie) -> str:
    """File name of a movie's web version inside media/<slug>/."""
    return f"movie-{movie.id.lower()}.mp4"


def poster_file(movie: Movie) -> str:
    """File name of a movie's poster frame inside media/<slug>/."""
    return f"poster-{movie.id.lower()}.jpg"


def check_topics(site: Site, papers: list[Paper], others: list[OtherPub]) -> None:
    """Every paper sits under one of the site's topics, and each highlight is one of the papers, once."""
    ids = [t.id for t in site.topics]
    _check(len(ids) == len(set(ids)), f"site: duplicate topic ids {ids}")
    for p in [*papers, *others]:
        _check(p.topic in ids, f"{p.slug}: topic {p.topic!r} is not one of {ids}")
    slugs = {p.slug for p in [*papers, *others]}
    for slug in site.highlights:
        _check(slug in slugs, f"site: highlight {slug!r} is not one of the papers")
    _check(len(site.highlights) == len(set(site.highlights)), "site: a paper appears twice in the highlights")


def load_news(path: Path) -> list[NewsItem]:
    """The press coverage in content/news.toml, as listed there."""
    items = []
    for raw in _read(path).get("news", []):
        try:
            item = NewsItem(**{**raw, "also": [Platform(**p) for p in raw.get("also", [])]})
        except TypeError as err:
            raise ValueError(f"news {raw.get('headline', '?')!r}: {err}") from err
        name = f"news {item.headline!r}"
        _check(re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.date) is not None, f"{name}: date must be YYYY-MM-DD")
        _check(all(u.startswith("https://") for u in [item.url, *(p.url for p in item.also)]),
               f"{name}: the links must be https")
        _check(bool(item.papers), f"{name}: name the paper it covers")
        _check(bool(item.translation) == bool(item.lang), f"{name}: a headline not in English needs its translation")
        items.append(item)
    return items


def check_news(items: list[NewsItem], papers: list[Paper], others: list[OtherPub]) -> None:
    """Every story covers papers the site lists."""
    slugs = {p.slug for p in [*papers, *others]}
    for item in items:
        for slug in item.papers:
            _check(slug in slugs, f"news {item.headline!r}: {slug!r} is not one of the papers")


def home_order(papers: list[Paper]) -> list[Paper]:
    """Highlights in file order, then the rest newest first."""
    highlights = [p for p in papers if p.highlight]
    rest = sorted((p for p in papers if not p.highlight), key=lambda p: p.date, reverse=True)
    return highlights + rest


def credit_line(paper: Paper) -> str:
    surnames = [a.split()[-1] for a in paper.authors]
    if len(surnames) == 1:
        who = surnames[0]
    elif len(surnames) == 2:
        who = f"{surnames[0]} and {surnames[1]}"
    else:
        who = f"{surnames[0]} et al."
    return f"From {who}, {paper.citation}."


def placeholders(site: Site, papers: list[Paper], others: list[OtherPub]) -> list[str]:
    """Dotted paths of every field still holding a TODO: placeholder."""
    found = []

    def check(path: str, value) -> None:
        if isinstance(value, str) and value.startswith(PLACEHOLDER):
            found.append(path)

    for name in ("name", "tagline", "bio", "photo"):
        check(f"site.{name}", getattr(site, name))
    for key, value in site.links.items():
        check(f"site.links.{key}", value)
    for p in papers:
        for name in ("title", "short_title", "citation", "doi", "supplementary_url", "one_line", "bibtex"):
            check(f"paper.{p.slug}.{name}", getattr(p, name))
        for m in p.movies:
            check(f"paper.{p.slug}.movie.{m.id}.caption", m.caption)
    for o in others:
        for name in ("title", "citation", "doi", "one_line", "thumb"):
            check(f"other.{o.slug}.{name}", getattr(o, name))
    return found
