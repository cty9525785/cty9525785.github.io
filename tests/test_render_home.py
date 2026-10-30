import hashlib
import html
import re
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from tests.htmlutil import section, tags
from tools.build import build, render_experience, render_home, render_publications
from tools.content import Segment, Tile, TileInput, load_news, load_papers, load_site

ROOT = Path(__file__).resolve().parents[1]
PUB =re.compile(r'<li class="pub" data-slug="([a-z0-9-]+)">(.*?)</li>', re.S)
CO_LABEL = '<li class="co-label">Co-authored</li>'
CREDIT = ("Movies and figures are from, or adapted from, the papers credited on each paper’s page "
          "or linked from each entry.")
DEEDS = {"CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
         "CC BY-NC 4.0": "https://creativecommons.org/licenses/by-nc/4.0/"}
# The approved design's topic table (2026-10-30): Tianyu's own papers first, then the co-authored ones in file order.
GROUPS = {
    "morphing": ["scale-inspired-robotic-structures", "programmable-morphing-structure", "suture-interlocking-metamaterials",
                 "thermally-responsive-actuators", "negative-pressure-actuators", "multistable-soft-robots",
                 "active-fabrics", "hierarchical-tessellation", "architectured-composites", "self-sensing-structures"],
    "control": ["stiffness-driven-control", "muscle-impedance-sensors", "droplet-energy-harvester",
                "dual-responsive-skin"],
    "metals": ["shear-banding-gradient-metals", "amorphous-thin-films", "graded-substrate-thin-films", "bimodal-friction",
               "gradient-friction", "gradient-nanolayers"],
}


def groups(page):
    """Topic id -> the slugs its list shows, in order."""
    found = {}
    for part in section(page, "publications").split('<div class="topic"')[1:]:
        topic = re.match(r' id="topic-([a-z0-9-]+)" data-topic="\1"', part).group(1)
        found[topic] = [slug for slug, _ in PUB.findall(part)]
    return found


def entries(page):
    return dict(PUB.findall(section(page, "publications")))


def hero_links(page):
    return re.search(r'<p class="links">(.*?)</p>', section(page, "hero"), re.S).group(1)


def css_rules(css):
    """(selectors, declarations) of each innermost CSS rule, in file order."""
    return [([s.strip() for s in selectors.split(",")], body)
            for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S))]


def last_rule(rules, selector):
    """The declarations of the last rule naming this selector: the one that wins at equal specificity."""
    found = [body for selectors, body in rules if selector in selectors]
    return found[-1] if found else ""


def contrast(fg, bg):
    """WCAG contrast ratio of two #rrggbb colors."""
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def anchors(fragment):
    """(attributes, visible text) of each <a> in the fragment; icons carry no text."""
    return [(attrs, re.sub(r"<[^>]+>", "", body).strip())
            for attrs, body in re.findall(r"<a ([^>]*)>(.*?)</a>", fragment, re.S)]


class RenderHomeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = load_site(ROOT / "content" / "site.toml")
        cls.papers, cls.others = load_papers(ROOT / "content" / "papers.toml")
        cls.news = load_news(ROOT / "content" / "news.toml")
        cls.page = render_home(cls.site, cls.papers, cls.others, cls.news)
        cls.pubs = render_publications(cls.site, cls.papers, cls.others)
        cls.xp = render_experience(cls.site)

    def with_paper(self, slug, **changes):
        return [replace(p, **changes) if p.slug == slug else p for p in self.papers]

    def with_other(self, slug, **changes):
        return [replace(o, **changes) if o.slug == slug else o for o in self.others]

    def test_nav(self):
        # Tianyu (2026-10-30): "i would expect all the tabs has their own page", and chose Home, Publications,
        # Experience and CV, each its own page, the one shown marked; the name leads home too.
        for page, here in ((self.page, "Home"), (self.pubs, "Publications"), (self.xp, "Experience")):
            bar = re.search(r'<header class="nav">(.*?)</header>', page, re.S).group(1)
            self.assertEqual([(t.get("href"), text) for t, (_, text) in zip(tags(bar, "a"), anchors(bar))],
                             [("index.html", "Tianyu Chen"), ("index.html", "Home"), ("publications.html", "Publications"),
                              ("experience.html", "Experience"), ("files/Tianyu-Chen-CV.pdf", "CV")])
            self.assertEqual([text for t, (_, text) in zip(tags(bar, "a"), anchors(bar)) if t.get("aria-current")],
                             [here])
            self.assertEqual(tags(bar, "a")[-1].get("class"), "cv")
            tabs = re.search(r'<nav aria-label="Main">(.*?)</nav>', bar, re.S).group(1)
            self.assertEqual([text for _, text in anchors(tabs)], ["Home", "Publications", "Experience"])
        # On a phone every tab stays: the tabs take a row of their own under the name and the CV, which a 320 px
        # screen cut off when it ended the tabs' row.
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        phone = re.search(r"@media \(max-width: 860px\) \{(.*?)\n\}", css, re.S).group(1)
        self.assertRegex(phone, r"\.nav \.wrap \{[^}]*flex-wrap: wrap")
        self.assertRegex(phone, r"\.nav nav \{[^}]*order: 1;[^}]*flex-basis: 100%")
        self.assertNotRegex(phone, r"\.nav nav a[^{]*\{[^}]*display: none")

    def test_hero(self):
        hero = section(self.page, "hero")
        # Tianyu chose this tagline (2026-10-30).
        self.assertIn("<h1>I design robotic structures, <span>from simulation to working hardware.</span></h1>", hero)
        # Tianyu chose intro A (2026-10-30): the photo large on the left with the three links under it, and name,
        # role, headline and bio on the right.
        side = re.search(r'<div class="side">(.*?)</div>', hero, re.S).group(1)
        self.assertEqual([(t.get("class"), t.get("src"), t.get("alt")) for t in tags(side, "img")],
                         [("portrait", "assets/img/photo.jpg", "Photo of Tianyu Chen")])
        self.assertIn('<p class="links">', side)
        about = re.search(r'<div class="about">(.*?)</div>', hero, re.S).group(1)
        self.assertIn('<p class="who"><b>Tianyu Chen</b><span class="role">Research Associate, Bristol Robotics '
                      'Laboratory</span></p>', about)
        self.assertIn("<h1>", about)
        self.assertIn('<div class="bio" id="bio">', about)
        # Tianyu (2026-10-30): the bio in two paragraphs, Bristol now and the PhD before, the second starting
        # "Previously, I did my PhD at ...".
        bio = re.search(r'<div class="bio" id="bio">(.*?)</div>', hero, re.S).group(1)
        paragraphs = re.findall(r"<p>(.*?)</p>", bio, re.S)
        self.assertEqual(len(paragraphs), 2)
        self.assertTrue(paragraphs[0].startswith("At the Bristol Robotics Laboratory, University of Bristol, I work in"))
        self.assertTrue(paragraphs[1].startswith("Previously, I did my PhD at Nanyang Technological University in"))
        links = hero_links(self.page)
        self.assertEqual([text for _, text in anchors(links)], ["Email", "Google Scholar", "LinkedIn"])
        self.assertEqual([t.get("href") for t in tags(links, "a")],
                         ["mailto:" + self.site.links["email"], self.site.links["scholar"], self.site.links["linkedin"]])
        self.assertEqual([t.get("class") for t in tags(links, "a")], ["btn primary", "btn", "btn"])

    def test_hero_layout(self):
        # Tianyu: the intro was "not balanced", with the big headline and a small headshot in a half it did not fill,
        # and "i don't want the big font text to be so big": a 240 px photo column beside the text, headline 32 px.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        h1 = [int(re.search(r"font-size: (\d+)px", body).group(1)) for selectors, body in rules if "h1" in selectors]
        self.assertLessEqual(h1[0], 32)  # the base rule; the phone rule follows it
        self.assertIn("grid-template-columns: 240px minmax(0, 1fr)",
                      [body for selectors, body in rules if ".hero" in selectors][0])
        # Tianyu, circling the space right of the bio: "why it feels a bit blank on this side". The bio's 36em sat in
        # an 800 px column; on a wide screen the photo grows and the bio fills the column, at 19 px to keep its lines
        # near 75 characters.
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        wide = re.search(r"@media \(min-width: 1080px\) \{(.*?)\n\}", css, re.S).group(1)
        self.assertRegex(wide, r"\.hero \{[^}]*grid-template-columns: 264px minmax\(0, 1fr\)")
        self.assertRegex(wide, r"\.portrait \{[^}]*width: 264px;[^}]*height: 264px")
        self.assertRegex(wide, r"\.bio \{[^}]*max-width: none")
        self.assertRegex(wide, r"\.bio \{[^}]*font-size: 19px")
        self.assertRegex(wide, r"\.who b \{[^}]*font-size: 22px")
        # Tianyu: the LinkedIn button and the bio's last line "should align. maybe make my headshot smaller a bit?"
        # The photo column (264 px photo, buttons) is shorter than the text and stretches to its height, with the
        # photo at the top and the buttons at the foot, 4 px up to meet the letters rather than the line's bottom.
        side = [body for selectors, body in rules if ".hero .side" in selectors][0]
        for needed in ("display: flex", "flex-direction: column", "justify-content: space-between",
                       "align-self: stretch", "padding-bottom: 4px"):
            self.assertIn(needed, side)
        # These rules are the intro's alone: the Experience page's columns share the class name "side".
        self.assertFalse([s for selectors, _ in rules for s in selectors if s.startswith((".side", ".about"))])
        self.assertIn("margin: 0;", [body for selectors, body in rules if ".bio" in selectors][0])
        self.assertNotIn("<video", section(self.page, "hero"))

    def test_home_page(self):
        # Tianyu chose (2026-10-30) Home, Publications, Experience and CV as pages of their own: Home keeps the intro,
        # the research highlights and the news. Publications and Experience left it, and Selected work, whose cards
        # repeated the slideshow, is gone.
        main = re.search(r"<main>(.*?)</main>", self.page, re.S).group(1)
        self.assertEqual(re.findall(r'<section id="([a-z-]+)"', main), ["hero", "highlights", "news"])
        for gone in ('class="card"', '<li class="pub"', 'class="xp"', "Selected work"):
            self.assertNotIn(gone, self.page)

    def test_photo_is_recognizable(self):
        # Tianyu: "do you think my photo should be a bit larger" (at 34 px no face showed), then "make my headshot
        # cropped by the circular shape". The photo file is 600 px square, sharp at twice this size.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        portrait = [body for selectors, body in rules if ".portrait" in selectors]
        widths = [int(re.search(r"width: (\d+)px", body).group(1)) for body in portrait if "width:" in body]
        self.assertGreaterEqual(widths[0], 240)  # the base rule; the phone rule follows it
        self.assertGreaterEqual(min(widths), 112)
        self.assertIn("border-radius: 50%", portrait[0])

    def test_hero_placeholders(self):
        pending = replace(self.site, photo="assets/img/photo-placeholder.svg",
                          links={k: "TODO: later" for k in self.site.links})
        page = render_home(pending, self.papers, self.others)
        for attrs, label in anchors(hero_links(page)):
            self.assertIn("placeholder", attrs, label)
        self.assertIn("placeholder", tags(re.search(r'<header class="nav">(.*?)</header>', page, re.S).group(1),
                                          "a")[-1].get("class"))
        self.assertEqual([t.get("src") for t in tags(section(page, "hero"), "img")
                          if t.get("alt") == "Photo of Tianyu Chen"], ["assets/img/photo-placeholder.svg"])

    def test_bio_links(self):
        # Tianyu: "add the url for vivohub and my previous professor's lab website in the bio".
        bio = "I work in [the lab](https://example.invalid/lab?a=1&b=2) <here>."
        page = render_home(replace(self.site, bio=bio), self.papers, self.others)
        self.assertIn('I work in <a href="https://example.invalid/lab?a=1&amp;b=2" target="_blank" rel="noopener">the lab</a>'
                      ' &lt;here&gt;.', page)

    def test_bio_paragraphs(self):
        # A blank line in the bio starts a new paragraph; a draft bio carries its badge at the end.
        page = render_home(replace(self.site, bio="Now here.\n\nBefore\nthere.", bio_status="draft"),
                           self.papers, self.others)
        self.assertIn('<div class="bio" id="bio"><p>Now here.</p><p>Before\nthere. <span class="draft">draft</span>'
                      '</p></div>', page)

    def test_external_links_open_in_new_tabs(self):
        # Tianyu: "for link outside my own site, open in new tab". Links within the site, and mailto, stay put.
        checked = 0
        for attrs, _ in anchors(self.page) + anchors(self.pubs) + anchors(self.xp):
            href = re.search(r'href="([^"]*)"', attrs).group(1)
            external = href.startswith(("http://", "https://")) and not href.startswith(self.site.url)
            self.assertEqual('target="_blank"' in attrs, external, href)
            if external:
                self.assertIn('rel="noopener"', attrs)
                checked += 1
        self.assertGreater(checked, 50)

    def test_draft_bio_is_marked(self):
        draft = render_home(replace(self.site, bio="I study robots.", bio_status="draft"), self.papers, self.others)
        self.assertIn('I study robots. <span class="draft">draft</span>', draft)
        confirmed = render_home(replace(self.site, bio="I study robots.", bio_status="confirmed"), self.papers, self.others)
        self.assertIn("I study robots.", confirmed)
        self.assertNotIn('I study robots. <span class="draft">', confirmed)

    def test_highlights(self):
        # Tianyu (2026-10-30) chose a "camera roll" like hyunwooyuk.com's research highlights over the turning tiles:
        # one big captioned slide at a time with numbered tabs, each slide linking to its paper page ("add link of each
        # slide to its paper page"), and key co-authored papers added, each marked as such.
        hl = section(self.page, "highlights")
        slides = re.findall(r'<article class="slide( on)?" id="hl-(\d+)" data-slug="([a-z0-9-]+)">(.*?)</article>', hl,
                            re.S)
        self.assertEqual([slug for _, _, slug, _ in slides], self.site.highlights)
        self.assertEqual([n for _, n, _, _ in slides], [str(i) for i in range(1, len(slides) + 1)])
        self.assertEqual([bool(on) for on, *_ in slides], [True] + [False] * (len(slides) - 1))
        own = {p.slug: p for p in self.papers}
        others = {o.slug: o for o in self.others}
        for i, (_, _, slug, body) in enumerate(slides):
            pub = own.get(slug) or others[slug]
            link = f"papers/{slug}/index.html" if slug in own else f"https://doi.org/{pub.doi}"
            media = re.search(r'<a class="hl-media[^"]*" href="([^"]+)"(?: target="_blank" rel="noopener")? '
                              r'(tabindex="-1" aria-hidden="true")>(.*?)</a>', body, re.S)
            self.assertEqual(media.group(1), link, slug)
            new_tab = ' target="_blank" rel="noopener"' if link.startswith("https://") else ""  # the publisher's
            self.assertIn(f'<h3><a href="{link}"{new_tab}>', body)
            self.assertIn(html.escape(pub.one_line), body)
            self.assertIn(html.escape(pub.citation), body)
            self.assertEqual(body.count("<strong>Tianyu Chen"), 1, slug)
            self.assertEqual('<p class="label">Co-authored</p>' in body, slug not in own, slug)
            if pub.tile is None:
                self.assertEqual([t.get("src") for t in tags(media.group(3), "img")], [f"media/{slug}/thumb.jpg"])
                continue
            self.assertEqual([t.get("src") for t in tags(media.group(3), "source")], [f"media/{slug}/loop.mp4"])
            video = tags(media.group(3), "video")[0]
            self.assertEqual(video.get("poster"), f"media/{slug}/loop-poster.jpg")
            for attr in ("muted", "loop", "playsinline"):
                self.assertIn(attr, video)
            self.assertEqual("autoplay" in video, i == 0, slug)  # the script plays each other clip as its slide shows
            if i:
                self.assertEqual(video.get("preload"), "none", slug)
        tabs = tags(re.search(r'<nav class="hl-tabs" aria-label="Highlights">(.*?)</nav>', hl, re.S).group(1), "a")
        self.assertEqual([t.get("href") for t in tabs], [f"#hl-{i}" for i in range(1, len(slides) + 1)])
        for tab, slug in zip(tabs, self.site.highlights):
            pub = own.get(slug) or others[slug]
            self.assertIn(html.escape(pub.short_title or pub.title), tab.get("aria-label"))
        self.assertIn('<button type="button" class="hl-pause" aria-pressed="false">Pause</button>', hl)

    def test_news(self):
        # Tianyu: "also include any news section about my work, both first author and coauthor"; all confirmed
        # coverage, newest first, Chinese posts with their headlines in English. Each story names the paper it covers,
        # co-authored ones marked, so no story reads as Tianyu's own when it is not.
        news = section(self.page, "news")
        order = [self.page.index(f'<section id="{name}"') for name in ("hero", "highlights", "news")]
        self.assertEqual(order, sorted(order))
        items = re.findall(r'<li class="news-item">(.*?)</li>', news, re.S)
        newest = sorted(self.news, key=lambda n: n.date, reverse=True)
        self.assertEqual(len(items), len(newest))
        own = {p.slug: p for p in self.papers}
        others = {o.slug: o for o in self.others}
        for body, item in zip(items, newest):
            link = tags(body, "a")[0]
            self.assertEqual(link.get("href"), item.url)
            self.assertIn(html.escape(item.headline), body)
            self.assertIn(html.escape(item.outlet), body)
            if item.lang:
                self.assertEqual(link.get("lang"), item.lang)
                self.assertIn(html.escape(item.translation), body)
            # The same story on other sites is one item: "Also on" links to each of them.
            also = re.search(r'<p class="also">Also on (.*?)</p>', body)
            self.assertEqual(bool(also), bool(item.also), item.headline)
            if item.also:
                self.assertEqual([(a.get("href"), text) for a, (_, text) in zip(tags(also.group(1), "a"), anchors(also.group(1)))],
                                 [(p.url, p.outlet) for p in item.also])
            for slug in item.papers:
                if slug in own:  # Tianyu: "my own paper on the news section also link to publisher directly"
                    self.assertIn(f'<a href="https://doi.org/{own[slug].doi}" target="_blank" rel="noopener">'
                                  f'{html.escape(own[slug].short_title)}</a>', body)
                    self.assertNotIn(f"{html.escape(own[slug].short_title)}</a> (co-authored)", body)
                else:  # Tianyu: "add the url also for coauthor papers": the publisher's page, as elsewhere
                    o = others[slug]
                    self.assertIn(f'<a href="https://doi.org/{o.doi}" target="_blank" rel="noopener">'
                                  f'{html.escape(o.short_title or o.title)}</a> (co-authored)', body)
        # The six newest show; the rest wait under All coverage, which opens without scripts.
        self.assertEqual(news.count("<details"), 1)
        self.assertEqual(news.split("<details")[0].count('class="news-item"'), 6)
        self.assertIn(f"<summary>All coverage ({len(newest)})</summary>", news)

    def test_highlights_motion(self):
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        rules = css_rules(css)
        # Without scripts every slide shows, one under another, and the tabs jump to them. With them, a one-line script
        # in the head marks the page before it draws, so the slides stack in one grid cell from the first paint.
        self.assertNotIn("visibility: hidden", last_rule(rules, ".slide"))
        self.assertIn("grid-area: 1 / 1", last_rule(rules, ".js .slide"))
        self.assertIn("visibility: hidden", last_rule(rules, ".js .slide"))
        self.assertIn("visibility: visible", last_rule(rules, ".js .slide.on"))
        self.assertIn("display: none", last_rule(rules, "html:not(.js) .hl-pause"))
        head = self.page[:self.page.index("</head>")]
        self.assertIn('<script>document.documentElement.className += " js";</script>', head)
        # A grid column's minimum is its content's width unless set to 0: plain 1fr let a slide's clip widen the column
        # past a phone's screen and cut the text. On a phone the clip stays on top and the text takes the rest.
        slide_rules = [body for selectors, body in rules if ".slide" in selectors]
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)", slide_rules[0])
        self.assertIn("grid-template-columns: minmax(0, 1fr)", slide_rules[-1])
        self.assertIn("grid-template-rows: auto 1fr", slide_rules[-1])
        self.assertIn("grid-template-columns: minmax(0, 1fr)", last_rule(rules, ".js .hl-slides"))
        # Like the clips, the slideshow moves whatever the reduced-motion setting, and it can be paused.
        reduced = css.split("@media (prefers-reduced-motion: reduce) {")[1].split("\n}")[0]
        self.assertNotIn(".slide", reduced)
        js = (ROOT / "assets" / "js" / "home.js").read_text(encoding="utf-8")
        for needed in (".hl-tab", ".hl-pause", "aria-pressed", "aria-current", "visibilitychange"):
            self.assertIn(needed, js)
        # Tianyu: "does the research highlight switch between 1 2 3 4 ...? ... i mean auto roll". Picking a number
        # stopped the roll for good while the button still read "Pause": the roll goes on from the picked slide, and
        # only Pause, a hidden page or a slideshow scrolled away stops it.
        self.assertNotIn("advancing", js)
        tab_click = re.search(r'tab\.addEventListener\("click", function \(event\) \{(.*?)\}\);', js, re.S).group(1)
        self.assertNotIn("paused", tab_click)
        # A shown slide's clip rewinds and waits for "canplay": "loadeddata" fires once per clip, never after a rewind,
        # so slides 2 onward stood still (seen in a real-time run).
        self.assertIn('addEventListener("canplay"', js)
        self.assertNotIn('"loadeddata"', js)
        self.assertNotIn(".mosaic", js)

    def test_visit_counter(self):
        # Tianyu chose GoatCounter (2026-10-30) and made the site cty9525785. Every page loads the site's own reviewed
        # copy of count.js (nothing loads from another site); with no count address, nothing. The footer says nothing
        # of it: Tianyu asked to delete the line that did.
        tag = '<script data-goatcounter="https://cty9525785.goatcounter.com/count" async src="assets/js/count.js"></script>'
        for page in (self.page, self.pubs, self.xp):
            self.assertEqual(page.count("data-goatcounter"), 1)
            self.assertIn(tag, page)
            self.assertNotIn("GoatCounter", re.search(r"<footer>(.*?)</footer>", page, re.S).group(1))
        off = replace(self.site, goatcounter="")
        for page in (render_home(off, self.papers, self.others), render_publications(off, self.papers, self.others),
                     render_experience(off)):
            self.assertNotIn("goatcounter", page.lower())
        # The copy is the one read through on 2026-10-30: ISC license, from https://gc.zgo.at/count.js.
        script = (ROOT / "assets" / "js" / "count.js").read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(script).hexdigest(),
                         "792b7abd26c1fb6ae62906833e09a301251e2641816e69e4f95aba518f3fe3f0")

    def test_experience_page(self):
        # The roles, degrees and skills under the shared menu, styles and footer; with no clips or filters, no script
        # but the visit counter.
        meta = {t.get("property") or t.get("name"): t.get("content") for t in tags(self.xp, "meta")}
        self.assertIn("<title>Experience | Tianyu Chen</title>", self.xp)
        self.assertEqual(meta["description"], "Tianyu Chen’s roles, education and skills.")
        self.assertEqual(meta["og:url"], "https://tianyuchen.com/experience.html")
        self.assertEqual([t.get("href") for t in tags(self.xp, "link") if t.get("rel") == "stylesheet"],
                         ["assets/css/home.css"])
        self.assertEqual([t.get("src") for t in tags(self.xp, "script")], ["assets/js/count.js"])
        main = re.search(r"<main>(.*?)</main>", self.xp, re.S).group(1)
        self.assertEqual(re.findall(r'<section id="([a-z-]+)"', main), ["experience"])
        self.assertIn("<h1>Experience", main)
        self.assertEqual(self.xp.count("<h1>"), 1)
        self.assertNotIn("Background", main)  # the label above the heading, a kicker, said what the heading says
        self.assertEqual(re.search(r"<footer>(.*?)</footer>", self.xp, re.S).group(1),
                         re.search(r"<footer>(.*?)</footer>", self.page, re.S).group(1))

    def test_publications_page(self):
        # The full list under the home page's menu, styles, script and footer.
        meta = {t.get("property") or t.get("name"): t.get("content") for t in tags(self.pubs, "meta")}
        self.assertIn("<title>Publications | Tianyu Chen</title>", self.pubs)
        self.assertEqual(meta["description"], "Papers by Tianyu Chen, grouped by topic.")
        self.assertEqual(meta["og:url"], "https://tianyuchen.com/publications.html")
        self.assertEqual(meta["og:image"], "https://tianyuchen.com/assets/img/social-card.jpg")
        self.assertEqual([t.get("href") for t in tags(self.pubs, "link") if t.get("rel") == "stylesheet"],
                         ["assets/css/home.css"])
        self.assertEqual([t.get("src") for t in tags(self.pubs, "script")], ["assets/js/home.js", "assets/js/count.js"])
        main = re.search(r"<main>(.*?)</main>", self.pubs, re.S).group(1)
        self.assertEqual(re.findall(r'<section id="([a-z-]+)"', main), ["publications"])
        self.assertIn("<h1>Publications</h1>", main)
        self.assertEqual(self.pubs.count("<h1>"), 1)
        self.assertEqual(re.search(r"<footer>(.*?)</footer>", self.pubs, re.S).group(1),
                         re.search(r"<footer>(.*?)</footer>", self.page, re.S).group(1))
        # Tianyu: "why the shade below menu bar seems darker in the publication page". The gray band the list sits on
        # started with its own 1 px line right under the bar's hairline, a dark double line in the bar's shadow: the
        # bar's edge is the band's top now.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        self.assertFalse([body for selectors, body in rules if ".band" in selectors and "border-top" in body])
        self.assertIn('<main>\n<section id="publications" class="band">', self.pubs)

    def test_entry_clip_attributes(self):
        found = entries(self.pubs)
        body = found["scale-inspired-robotic-structures"]
        video = tags(body, "video")[0]
        for attr in ("muted", "loop", "playsinline"):
            self.assertIn(attr, video)
        self.assertEqual(video.get("poster"), "media/scale-inspired-robotic-structures/loop-poster.jpg")
        self.assertEqual(tags(body, "source")[0].get("src"), "media/scale-inspired-robotic-structures/loop.mp4")
        # Tianyu is co-first author of the Science Advances paper; its entry must say so.
        self.assertIn("Jie Pan†, <strong>Tianyu Chen†</strong>", found["stiffness-driven-control"])
        self.assertIn("(†&nbsp;equal contribution)", found["stiffness-driven-control"])

    def test_entry_without_tile_shows_figure(self):
        slug = "graded-substrate-thin-films"
        body = entries(render_publications(self.site, self.with_paper(slug, tile=None), self.others))[slug]
        self.assertEqual(tags(body, "video"), [])
        img = tags(body, "img")[0]
        self.assertEqual((img.get("src"), img.get("loading")), (f"media/{slug}/thumb.jpg", "lazy"))
        self.assertTrue(img.get("alt"))

    def test_thumbnails_carry_no_labels(self):
        # Tianyu: "no need to add illustration or paper figure for the thumbnails, even the x times can be removed".
        slug = "scale-inspired-robotic-structures"
        tile = next(p for p in self.papers if p.slug == slug).tile
        for changed in (tile, Tile("drawing", drawing="films"), None):
            papers = self.with_paper(slug, tile=changed)
            for page in (render_home(self.site, papers, self.others), render_publications(self.site, papers, self.others)):
                self.assertNotIn("clip-label", page)
                for text in ("Illustration", "Paper figure", "× speed", "Real time"):
                    self.assertNotIn(text, page)
        # The page's own script file and the visit counter, plus the one-line class setter in the head that the
        # slideshow's layout needs.
        self.assertEqual([t.get("src") for t in tags(self.page, "script")], [None, "assets/js/home.js", "assets/js/count.js"])
        self.assertEqual(self.page.count("<script>"), 1)

    def test_experience(self):
        xp = section(self.xp, "experience")
        roles = re.findall(r"<li>(.*?)</li>", re.search(r'<ol class="xp">(.*?)</ol>', xp, re.S).group(1), re.S)
        self.assertEqual(len(roles), len(self.site.experience))
        for li, r in zip(roles, self.site.experience):
            for value in (r.years, r.role, r.org, r.text):
                self.assertIn(html.escape(value), li)
        degrees = re.findall(r"<li>(.*?)</li>", re.search(r'<ul class="edu">(.*?)</ul>', xp, re.S).group(1), re.S)
        self.assertEqual(len(degrees), len(self.site.education))
        for li, d in zip(degrees, self.site.education):
            for value in (d.year, d.degree, d.school):
                self.assertIn(html.escape(value), li)
        for g in self.site.skills:
            self.assertIn(html.escape(g.name), xp)
            for item in g.items:
                self.assertIn(f"<span>{html.escape(item)}</span>", xp)
        # Drafted from the CV, the text is marked until Tianyu confirms it; Tianyu confirmed it on 2026-10-30.
        self.assertNotIn('class="draft"', xp)
        draft = render_experience(replace(self.site, cv_status="draft"))
        self.assertEqual(section(draft, "experience").count('<span class="draft">draft</span>'), 1)

    def test_timeline_dots_sit_on_the_line(self):
        # Tianyu: "why the circles don't align with the line". "*" does not match ::before and ::after, so the dot kept
        # content-box sizing and its border pushed its center 2px right of the line's.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        for selector in ("*", "*::before", "*::after"):
            self.assertIn("box-sizing: border-box", last_rule(rules, selector), selector)

        def px(rule, prop):
            return float(re.search(rf"(?<![-\w]){prop}:\s*(-?[\d.]+)(?:px)?;", rule).group(1))

        line, dot = last_rule(rules, ".xp li::before"), last_rule(rules, ".xp li::after")
        self.assertEqual(px(line, "left") + px(line, "width") / 2, px(dot, "left") + px(dot, "width") / 2)
        self.assertEqual(px(dot, "width"), 16)  # the size it showed before the fix

    def test_publication_groups(self):
        found = groups(self.pubs)
        self.assertEqual(list(found), ["morphing", "control", "metals"])
        self.assertEqual(found, GROUPS)
        shown = [slug for slugs in found.values() for slug in slugs]
        self.assertEqual(sorted(shown), sorted([p.slug for p in self.papers] + [o.slug for o in self.others]))
        headings = re.findall(r"<h3>([^<]*)</h3>", section(self.pubs, "publications"))
        self.assertEqual(headings, [t.heading for t in self.site.topics])
        # Tianyu asked why "All papers" sat above "Publications": it only repeated the heading.
        self.assertNotIn("All papers", section(self.pubs, "publications"))

    def test_filters_work_without_js(self):
        pubs = section(self.pubs, "publications")
        nav = re.search(r'<nav class="filters" aria-label="Topics">(.*?)</nav>', pubs, re.S).group(1)
        chips = tags(nav, "a")
        self.assertEqual([text for _, text in anchors(nav)],
                         ["All", "Morphing structures", "Control and sensing", "Gradient metals and thin films"])
        self.assertEqual([c.get("href") for c in chips], ["#publications", "#topic-morphing", "#topic-control", "#topic-metals"])
        self.assertEqual([c.get("data-topic") for c in chips], ["all", "morphing", "control", "metals"])
        self.assertEqual(chips[0].get("class"), "chip on")
        for c in chips[1:]:
            self.assertIn(f'<div class="topic" id="{c.get("href")[1:]}"', pubs)
        for page in (self.page, self.pubs):
            self.assertIsNone(re.search(r"<[a-z][^>]*\shidden[\s>=]", page))  # nothing starts hidden

    def test_coauthored_entries(self):
        others = {o.slug: o for o in self.others}
        own = {p.slug: p for p in self.papers}
        self.assertEqual(len(entries(self.pubs)), len(own) + len(others))
        for part in section(self.pubs, "publications").split('<div class="topic"')[1:]:
            label = part.index(CO_LABEL)
            for m in PUB.finditer(part):
                self.assertEqual(m.start() > label, m.group(1) in others, m.group(1))
        for slug, body in entries(self.pubs).items():
            hrefs = [t.get("href") for t in tags(body, "a")]
            if slug in others:
                o = others[slug]
                hosted = {o.pdf, o.supplement_pdf, DEEDS.get(o.license)} - {"", None}
                self.assertEqual(set(hrefs) - hosted, {f"https://doi.org/{o.doi}"}, slug)  # thumbnail, title and "Paper"
                self.assertGreaterEqual(len(hrefs), 3, slug)
                self.assertEqual(body.count("<strong>Tianyu Chen</strong>"), 1, slug)
                self.assertIn(f"<em>{html.escape(o.citation)}</em>", body)
                self.assertIn(html.escape(o.title), body)
            else:
                self.assertIn(f"papers/{slug}/index.html", hrefs)
                self.assertIn(f"https://doi.org/{own[slug].doi}", hrefs)

    def test_open_access_pdfs(self):
        # Tianyu, 2026-10-30, "yes for 1": each open-access paper links its PDF and supplement and names its license.
        hosted = {p.slug: p for p in [*self.papers, *self.others] if p.pdf}
        self.assertEqual(len(hosted), 7)
        for slug, body in entries(self.pubs).items():
            links = {text: attrs for attrs, text in anchors(re.search(r'<p class="more">(.*?)</p>', body, re.S).group(1))}
            if slug not in hosted:
                self.assertFalse({"PDF", "Supplementary"} & set(links), slug)
                continue
            p = hosted[slug]
            self.assertIn(f'href="{p.pdf}"', links["PDF"], slug)
            if p.supplement_pdf:
                self.assertIn(f'href="{p.supplement_pdf}"', links["Supplementary"], slug)
            else:
                self.assertNotIn("Supplementary", links, slug)
            self.assertIn(f'href="{DEEDS[p.license]}"', links[p.license], slug)

    def test_coauthored_entry_media(self):
        slug = self.others[0].slug  # an entry without a clip shows its figure, or what is missing
        page = render_publications(self.site, self.papers, self.with_other(slug, tile=None, thumb=""))
        img = tags(entries(page)[slug], "img")[0]
        self.assertEqual((img.get("src"), img.get("loading")), (f"media/{slug}/thumb.jpg", "lazy"))
        self.assertTrue(img.get("alt"))
        page = render_publications(self.site, self.papers, self.with_other(slug, tile=None, thumb="TODO: needs the PDF"))
        self.assertEqual(tags(entries(page)[slug], "img"), [])
        self.assertIn('<span class="placeholder">TODO: needs the PDF</span>', entries(page)[slug])

    def test_coauthored_entry_plays_its_clip(self):
        slug = self.others[0].slug
        tile = Tile("clip", "b.graph", [TileInput("S2", 1.0, 6.0)], [Segment(0.0, 2.0)])
        body = entries(render_publications(self.site, self.papers, self.with_other(slug, thumb="", tile=tile)))[slug]
        self.assertEqual(tags(body, "video")[0].get("poster"), f"media/{slug}/loop-poster.jpg")
        self.assertIn(f'<source src="media/{slug}/loop.mp4"', body)
        self.assertEqual(tags(body, "img"), [])

    def test_active_fabrics_shows_its_schematic(self):
        # Tianyu: "for the am paper this figure maybe better as thumbnail": Figure 1a's schematic, not a clip.
        body = entries(self.pubs)["active-fabrics"]
        self.assertEqual(tags(body, "video"), [])
        self.assertEqual([t.get("src") for t in tags(body, "img")], ["media/active-fabrics/thumb.jpg"])

    def test_coauthored_entry_marks_equal_contributors(self):
        found = entries(self.pubs)
        self.assertIn("Xudong Yang†, Yu Chen†, <strong>Tianyu Chen</strong>, Junwei Li, Yifan Wang "
                      "(†&nbsp;equal contribution)", found["active-fabrics"])
        self.assertNotIn("†", found["thermally-responsive-actuators"])

    def test_coauthored_entry_text(self):
        slug = self.others[0].slug
        draft = entries(render_publications(self.site, self.papers, self.with_other(
            slug, one_line="What the paper shows.", summary_status="draft")))[slug]
        self.assertIn('<p class="one">What the paper shows. <span class="draft">draft</span></p>', draft)
        confirmed = entries(render_publications(self.site, self.papers, self.with_other(
            slug, one_line="What the paper shows.", summary_status="confirmed")))[slug]
        self.assertIn('<p class="one">What the paper shows.</p>', confirmed)
        pending = entries(render_publications(self.site, self.papers, self.with_other(
            slug, doi="TODO: look up by title")))[slug]
        self.assertNotIn("doi.org", pending)
        self.assertIn('<span class="placeholder">TODO: look up by title</span>', pending)

    def test_footer(self):
        footer = re.search(r"<footer>(.*?)</footer>", self.page, re.S).group(1)
        self.assertIn(f"© {date.today().year} Tianyu Chen", footer)
        self.assertIn(CREDIT, footer)
        # impeccable critique (Tianyu chose "Phone first screen + contact"): the address itself shows, so a reader
        # without a mail app can copy it, and the page ends with an invitation to write.
        email = self.site.links["email"]
        self.assertIn(f'<p class="contact">Get in touch: <a href="mailto:{email}">{email}</a></p>', footer)
        self.assertEqual([text for _, text in anchors(footer)], [email, "Google Scholar", "LinkedIn"])
        self.assertNotIn("jonbarron", self.page)  # the home page no longer uses his design

    def test_text_contrast(self):
        # impeccable critique (Tianyu: "Darker gray"): the headline's gray half was 2.42:1, under the 3:1 that large
        # text needs; the role line and the Co-authored labels were 4.44:1 on the gray pill, under 4.5:1.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))

        def color(selector):
            found = [re.search(r"(?<![-\w])color: (#[0-9a-f]{6})", body) for selectors, body in rules if selector in selectors]
            return [m.group(1) for m in found if m][-1]

        self.assertGreaterEqual(contrast(color("h1 span"), "#ffffff"), 3.0)
        for selector in (".co-label",):
            self.assertGreaterEqual(contrast(color(selector), "#f6f7f9"), 4.5, selector)
        # The menu bar is ground glass (Tianyu: "add some glass feeling on this banner", "like the ground glass"): a
        # thin white wash over a strong blur, with a faint grain. Even over the darkest clip, the white wash with the
        # grain on it, its tabs keep 4.5:1; the gray they had (3.27:1 at 0.84 white) is darker for it.
        nav = last_rule(rules, ".nav")
        alpha = float(re.search(r"background-color: rgba\(255, 255, 255, ([\d.]+)\)", nav).group(1))
        self.assertLessEqual(alpha, 0.8)
        self.assertRegex(nav, r"(?<!-)backdrop-filter: blur\((\d+)px\)")
        self.assertGreaterEqual(int(re.search(r"(?<!-)backdrop-filter: blur\((\d+)px\)", nav).group(1)), 20)
        self.assertIn("feTurbulence", nav)  # the grain: black specks at most as opaque as its alpha row says
        grain = float(re.search(r"values='([^']*)'", nav).group(1).split()[18])
        darkest = round(255 * alpha * (1 - grain))
        self.assertGreaterEqual(contrast(color(".nav nav"), f"#{darkest:02x}{darkest:02x}{darkest:02x}"), 4.5)

    def test_link_names(self):
        # A link wrapping only a clip had no name, and each entry put two or three tab stops on one page: the clips
        # stay clickable but leave the tab order. "Paper", "PDF" and the like name their paper for screen readers.
        for page, name in ((self.page, "hl-media"), (self.pubs, "thumb")):  # a slide's title names its clip's page
            found = re.findall(rf'<a class="{name}(?: [a-z]+)?"([^>]*)>', page)
            self.assertTrue(found, name)
            for attrs in found:
                self.assertIn('tabindex="-1"', attrs)
                self.assertIn('aria-hidden="true"', attrs)
        named = 0
        for page, part in ((self.page, "highlights"), (self.pubs, "publications")):
            for attrs, text in anchors(section(page, part)):
                if text in ("Read the explainer", "Explainer", "Paper", "PDF", "Supplementary"):
                    label = re.search(r'aria-label="([^"]+)"', attrs)
                    self.assertIsNotNone(label, (part, text, attrs))
                    self.assertTrue(label.group(1).startswith(text + ": "), label.group(1))  # the visible words first
                    named += 1
        self.assertGreaterEqual(named, 60)  # 21 in the slideshow, 39 in the list

    def test_keyboard(self):
        # The topic chips act as buttons, so Space works as well as Enter; focus keeps the pill buttons round.
        js = (ROOT / "assets" / "js" / "home.js").read_text(encoding="utf-8")
        self.assertIn('event.key === " "', js)
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        rounded = [s for selectors, body in rules for s in selectors if ":focus-visible" in s and "border-radius" in body]
        self.assertTrue(rounded)
        for selector in rounded:
            self.assertIn(":not(.btn):not(.chip)", selector)

    def test_tab_icon(self):
        icons = [t for t in tags(self.page, "link") if t.get("rel") == "icon"]
        self.assertEqual([t.get("href") for t in icons], ["assets/img/favicon.svg"])
        self.assertTrue((ROOT / "assets" / "img" / "favicon.svg").is_file())

    def test_phone_first_screen(self):
        # On a phone the bio filled the first screen and pushed the contact buttons and the slideshow below it: the
        # buttons now come right under the headline, and with scripts the bio shows four lines and "Read more".
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        phone = re.search(r"@media \(max-width: 860px\) \{(.*?)\n\}", css, re.S).group(1)
        # The photo, the name, the headline, the buttons, then the bio (the intro's two columns open into one).
        self.assertRegex(phone, r"\.hero \.side,\s*\.hero \.about \{[^}]*display: contents")
        self.assertRegex(phone, r"\.hero \.links \{[^}]*order: 3")
        # The clamp sits on the first paragraph alone and the second waits for "Read more": browsers differ in how
        # a line clamp cuts across several paragraphs.
        self.assertRegex(phone, r"\.js \.bio:not\(\.open\) p:first-child \{[^}]*-webkit-line-clamp: 4")
        self.assertRegex(phone, r"\.js \.bio:not\(\.open\) p \+ p \{[^}]*display: none")
        self.assertNotRegex(phone, r"\.js \.bio:not\(\.open\) \{[^}]*line-clamp")
        self.assertRegex(phone, r"\.js \.bio-more \{[^}]*display: inline-block")
        self.assertIn("display: none", last_rule(css_rules(css), ".bio-more"))
        # The three buttons share one row (LinkedIn wrapped onto a row of its own): on a phone a button shows only
        # its last word, "Scholar", and screen readers still read "Google Scholar". On a phone too narrow for the
        # three, they wrap rather than spill their words.
        self.assertRegex(phone, r"\.hero \.btn \{[^}]*flex: 1 1 0")
        self.assertRegex(phone, r"\.hero \.btn \{[^}]*min-width: max-content")
        self.assertRegex(phone, r"\.hero \.first-words \{[^}]*clip: rect\(0 0 0 0\)")
        links = hero_links(self.page)
        self.assertIn('<span><span class="first-words">Google </span>Scholar</span>', links)
        self.assertEqual(links.count("first-words"), 1)
        hero = section(self.page, "hero")
        self.assertIn('<div class="bio" id="bio">', hero)
        self.assertIn('<button type="button" class="bio-more" aria-expanded="false" aria-controls="bio">Read more</button>',
                      hero)
        self.assertIn(".bio-more", (ROOT / "assets" / "js" / "home.js").read_text(encoding="utf-8"))

    def test_clips_load_near_the_screen(self):
        # The page fetched all 20 clips at load (3.4 MB by the load event, one loop up to three times): the
        # publication clips now wait until they near the screen; the slideshow loads only its current and next clip.
        found = 0
        for slug, body in entries(self.pubs).items():
            for video in tags(body, "video"):
                self.assertNotIn("autoplay", video, slug)
                self.assertEqual(video.get("preload"), "none", slug)
                found += 1
        self.assertGreaterEqual(found, 10)
        self.assertEqual(len(tags(self.page, "video")), len(tags(section(self.page, "highlights"), "video")))
        js = (ROOT / "assets" / "js" / "home.js").read_text(encoding="utf-8")
        self.assertIn('rootMargin: "300px 0px"', js)

    def test_link_preview(self):
        # LinkedIn, Slack and Teams build a link's preview card from these tags (Tianyu asked for a thumbnail).
        meta = {t.get("property") or t.get("name"): t.get("content") for t in tags(self.page, "meta")}
        self.assertEqual(meta["og:title"], "Tianyu Chen")
        self.assertEqual(meta["og:description"], self.site.tagline)
        self.assertEqual(meta["og:url"], "https://tianyuchen.com/")
        self.assertEqual(meta["og:image"], "https://tianyuchen.com/assets/img/social-card.jpg")
        self.assertEqual((meta["og:image:width"], meta["og:image:height"]), ("1200", "630"))
        self.assertEqual(meta["twitter:card"], "summary_large_image")
        from PIL import Image
        with Image.open(ROOT / "assets" / "img" / "social-card.jpg") as card:
            self.assertEqual(card.size, (1200, 630))

    def test_fonts_preloaded(self):
        # Tianyu saw the text change font a moment after opening: preloaded fonts are ready before the first paint.
        preloads = [t for t in tags(self.page, "link") if t.get("rel") == "preload"]
        self.assertEqual({t.get("href") for t in preloads}, {"assets/fonts/inter/inter-latin-wght-normal.woff2"})
        for t in preloads:
            self.assertEqual((t.get("as"), t.get("type")), ("font", "font/woff2"))
            self.assertIn("crossorigin", t)  # fonts load in CORS mode; without it the preload is fetched twice

    def test_responsive_css(self):
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        block = re.search(r"@media \(max-width: 860px\) \{(.*?)\n\}", css, re.S)
        self.assertIsNotNone(block)
        self.assertIn("grid-template-columns: 1fr;", block.group(1))  # one column on a phone
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        faces = re.findall(r"@font-face\s*\{(.*?)\}", css, re.S)
        self.assertTrue(faces and all("'Inter'" in f and "font-display: fallback" in f for f in faces))
        self.assertNotIn("Lato", css)
        # An entry's links (Explainer, Paper, PDF, Supplementary, license) wrap on a phone; a row that could not wrap
        # set the whole list's width and pushed every entry past the screen's edge.
        self.assertIn("flex-wrap: wrap", last_rule(css_rules(css), ".more"))

    def test_home_js_is_plain(self):
        # Topic filters and clip playback in plain JavaScript: nothing fetched, nothing imported.
        js = (ROOT / "assets" / "js" / "home.js").read_text(encoding="utf-8")
        for needed in ("data-topic", "IntersectionObserver"):
            self.assertIn(needed, js)
        for banned in ("import ", "require(", "http", "fetch("):
            self.assertNotIn(banned, js)
        # Tianyu saw the clips stand still: Windows asks for reduced motion whenever its animation effects are off,
        # and the clips are the page's evidence, so they play regardless (2026-10-30).
        self.assertNotIn("prefers-reduced-motion", js)

    def test_figures_show_whole(self):
        # 2026-10-28: a paper's figure is shown whole, since cropping it cuts through its labels; clips still fill.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        self.assertIn("object-fit: contain", last_rule(rules, ".pub .thumb img"))
        self.assertIn("object-fit: cover", last_rule(rules, ".pub .thumb video"))
        self.assertFalse([s for selectors, _ in rules for s in selectors if ".card" in s or s == ".grid"])

    def test_clips_show_their_whole_frame(self):
        # Tianyu: "is this thumbnail zoomed in too much?" The loops are square; a 4:3 frame cut their top and bottom.
        from tools.mp4meta import probe
        for loop in sorted((ROOT / "media").glob("*/loop.mp4")):
            info = probe(loop)
            self.assertEqual(info.width, info.height, loop.parent.name)
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        self.assertIn("aspect-ratio: 1 / 1", last_rule(rules, ".pub .thumb"))

    def test_pending_pills_look_unfinished(self):
        # A TODO: CV, email or profile link must look unfinished, not like a finished dark or outlined pill.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        for pill in (".btn.placeholder", ".btn.primary.placeholder", ".nav a.cv.placeholder"):
            self.assertIn("background: #fef3c7", last_rule(rules, pill), pill)
        self.assertIn("border-radius: 999px", last_rule(rules, ".btn.placeholder"))

    def test_draft_and_placeholder_styles(self):
        # Tianyu must see the DRAFT tag on text still to confirm, and placeholders must look unfinished.
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"(?m)^\.draft \{")
        self.assertRegex(css, r"(?m)^\.placeholder \{")

    def test_relative_paths_only(self):
        for page in (self.page, self.pubs, self.xp):
            self.assertIsNone(re.search(r'(src|href)="/[^/]', page))

    def test_no_third_party_assets(self):
        for page in (self.page, self.pubs, self.xp):
            assets = [t.get("href") for t in tags(page, "link")] + [t.get("src") for t in tags(page, "script")]
            for url in assets:
                self.assertFalse(url and url.startswith(("http:", "https:", "//")), url)

    def test_build_writes_pages(self):
        written = build(ROOT)
        self.assertEqual(len(written), 9)
        self.assertTrue(all(path.exists() for path in written))
        self.assertIn(ROOT / "index.html", written)
        self.assertIn(ROOT / "publications.html", written)
        self.assertIn(ROOT / "experience.html", written)
        self.assertIn(ROOT / "papers" / "graded-substrate-thin-films" / "index.html", written)


if __name__ == "__main__":
    unittest.main()
