import hashlib
import html
import json
import re
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from tests.htmlutil import section, tags, versioned
from tools.build import build, render_experience, render_home, render_publications
from tools.content import Segment, Tile, TileInput, load_news, load_papers, load_site

ROOT = Path(__file__).resolve().parents[1]
PUB =re.compile(r'<li class="pub" data-slug="([a-z0-9-]+)">(.*?)</li>', re.S)
CO_LABEL = '<li class="co-label">Co-authored</li>'
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


def outside_media(css):
    """The stylesheet without its @media blocks."""
    return re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", re.sub(r"/\*.*?\*/", "", css, flags=re.S))


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
        for page, here in ((self.page, "Home"), (self.pubs, "Publications"), (self.xp, "About me")):
            bar = re.search(r'<header class="nav">(.*?)</header>', page, re.S).group(1)
            self.assertEqual([(t.get("href"), text) for t, (_, text) in zip(tags(bar, "a"), anchors(bar))],
                             [("index.html", "Tianyu Chen"), ("index.html", "Home"), ("publications.html", "Publications"),
                              ("experience.html", "About me"), ("files/Tianyu-Chen-CV.pdf", "CV")])
            self.assertEqual([text for t, (_, text) in zip(tags(bar, "a"), anchors(bar)) if t.get("aria-current")],
                             [here])
            self.assertEqual(tags(bar, "a")[-1].get("class"), "cv")
            tabs = re.search(r'<nav aria-label="Main">(.*?)</nav>', bar, re.S).group(1)
            self.assertEqual([text for _, text in anchors(tabs)], ["Home", "Publications", "About me"])
        # On a phone every tab stays: the tabs take a row of their own under the name and the CV, which a 320 px
        # screen cut off when it ended the tabs' row.
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        phone = re.search(r"@media \(max-width: 860px\) \{(.*?)\n\}", css, re.S).group(1)
        self.assertRegex(phone, r"\.nav \.wrap \{[^}]*flex-wrap: wrap")
        self.assertRegex(phone, r"\.nav nav \{[^}]*order: 1;[^}]*flex-basis: 100%")
        self.assertNotRegex(phone, r"\.nav nav a[^{]*\{[^}]*display: none")
        # Tianyu (2026-11-01): "Why the header looks weird on the phone". Measured to the letters at 390 px: 25 px
        # above the name, 26.5 px between the rows, 17.5 px under the tabs, so the rows drifted apart and the tabs
        # sat on the bottom edge. Now 21.5 px above the name and under the tabs alike, and 20 px between the rows:
        # the name's 13 px letters sit centered in the CV pill's 40 px row, the tabs' 11 px letters 6.5 px from the
        # top and bottom of their 24 px line, and the bar has a 1 px edge.
        bar = last_rule(css_rules(phone), ".nav .wrap")
        for needed in ("padding-top: 8px", "padding-bottom: 14px", "row-gap: 0"):
            self.assertIn(needed, bar)
        self.assertEqual(8 + (40 - 13) / 2, 6.5 + 14 + 1)
        # Tianyu (2026-11-01): "why the CV button seems to change size every time i click on a tab". Each page lays
        # out with the fallback font's widths until Inter arrives (text held invisible meanwhile), and the pill was as
        # wide as its text: 55 px, then 58 px in Inter ("CV" 21.97 px at 15 px semibold, plus 36 px of padding).
        # It keeps Inter's width whatever the font, and so does Pause, 79.5 px in Inter, which also narrowed to
        # 67 px as "Play".
        anywhere = css_rules(outside_media(css))  # a phone hides Pause, so read the rules for every width
        cv = last_rule(anywhere, ".nav a.cv")
        self.assertIn("min-width: 58px", cv)
        self.assertIn("text-align: center", cv)
        self.assertIn("padding: 8px 18px", cv)
        self.assertIn("min-width: 80px", last_rule(anywhere, ".hl-pause"))

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
        # Tianyu (2026-10-31, on a phone): "Bristol robotic lab in a new line". The role reads as one line on wider
        # screens; on a phone the comma goes and the lab takes the next line (home.css).
        self.assertIn('<p class="who"><b>Tianyu Chen</b><span class="role">Research Associate<span class="at">, </span>'
                      '<span class="place">Bristol Robotics Laboratory</span></span></p>', about)
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        phone = css_rules(css.split("@media (max-width: 860px) {")[1].split("\n}")[0])
        self.assertIn("display: none", last_rule(phone, ".who .at"))
        self.assertIn("display: block", last_rule(phone, ".who .place"))
        self.assertEqual(last_rule(css_rules(outside_media(css)), ".who .at"), "")  # wider screens keep the comma
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
        # Tianyu (2026-10-31): "add https://orcid.org/0000-0002-3670-1824 to the buttons as well".
        self.assertEqual([text for _, text in anchors(links)], ["Email", "Google Scholar", "LinkedIn", "ORCID"])
        self.assertEqual([t.get("href") for t in tags(links, "a")],
                         ["mailto:" + self.site.links["email"], self.site.links["scholar"], self.site.links["linkedin"],
                          "https://orcid.org/0000-0002-3670-1824"])
        self.assertEqual([t.get("class") for t in tags(links, "a")], ["btn primary", "btn", "btn", "btn"])
        # Four buttons stacked under the photo would outgrow the text beside it: they are 36 px tall on a computer,
        # so the last still ends level with the bio's last line.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        self.assertIn("height: 36px", [body for selectors, body in rules if ".hero .btn" in selectors][0])

    def test_hero_layout(self):
        # Tianyu: the intro was "not balanced", with the big headline and a small headshot in a half it did not fill,
        # and "i don't want the big font text to be so big": a 240 px photo column beside the text, headline 32 px, and
        # 40 px on a wide screen, as shown to Tianyu in the design they chose (2026-11-04).
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        h1 = [re.search(r"font-size: (\d+)px", body) for selectors, body in rules if "h1" in selectors]
        self.assertLessEqual(int(h1[0].group(1)), 32)  # the base rule; the wide and phone rules follow it
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

    def test_phone_section_spacing(self):
        # Tianyu (2026-10-31): "On the phone the in the news and the cards above have no gap... Also check gaps between
        # other sections". The phone rule for every .wrap set "padding: 0 20px", which also wiped the top and bottom
        # padding the highlights and news sections take from their own rules: the slideshow met the news heading, and
        # the news met the footer. The phone gutter now sets the sides only, and those sections keep 64 px under them
        # on a phone, as Publications and Experience do.
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        phone = css_rules(css.split("@media (max-width: 860px) {")[1].split("\n}")[0])
        gutter = last_rule(phone, ".wrap")
        self.assertNotRegex(gutter, r"(^|[;\s])padding:")
        self.assertIn("padding-left: 20px", gutter)
        self.assertIn("padding-right: 20px", gutter)
        for selector in (".highlights", ".news"):
            self.assertIn("padding-bottom: 64px", last_rule(phone, selector), selector)
        self.assertIn("padding-bottom: 64px", last_rule(phone, "#experience"))

    def test_photo_is_recognizable(self):
        # Tianyu: "do you think my photo should be a bit larger" (at 34 px no face showed), then "make my headshot
        # cropped by the circular shape". The photo file is 600 px square, sharp at twice this size.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        portrait = [body for selectors, body in rules if ".portrait" in selectors]
        widths = [int(re.search(r"width: (\d+)px", body).group(1)) for body in portrait if "width:" in body]
        self.assertGreaterEqual(widths[0], 240)  # the base rule; the phone rule follows it
        self.assertGreaterEqual(min(widths), 112)
        self.assertIn("border-radius: 50%", portrait[0])
        # Tianyu (2026-10-31): "On the phone view can you put my photo to be centered instead of left aligned".
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        phone = css_rules(css.split("@media (max-width: 860px) {")[1].split("\n}")[0])
        self.assertIn("justify-self: center", last_rule(phone, ".portrait"))
        # Then "i think the two blank areas should be same thickness": above the photo and between it and the name.
        # Measured at 390 px: 24 px from the header to the photo, 26.5 px from the photo to the name's letters (the
        # 18 px name has 2.5 px more above its letters than its 16 px margin). The margin takes the 2.5 px off.
        self.assertIn("padding-top: 24px", last_rule(phone, ".hero"))
        self.assertIn("margin-bottom: 13.5px", last_rule(phone, ".portrait"))
        self.assertIn("text-align: center", last_rule(phone, ".who"))  # then "Also my name and role to be centered"

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
            # Tianyu (2026-11-01) chose the first slide for the hook animation they liked on the explainer page: that
            # paper's slide has a clip of its own, the animation and then the drone, as three co-authored slides have
            # theirs (test_coauthored_slides_play_their_own_clips); the others play their loops.
            clip = pub.highlight_clip or ("loop" if pub.tile else "")
            if not clip:
                self.assertEqual([t.get("src") for t in tags(media.group(3), "img")], [f"media/{slug}/thumb.jpg"])
                continue
            self.assertEqual([t.get("src") for t in tags(media.group(3), "source")], [f"media/{slug}/{clip}.mp4"])
            video = tags(media.group(3), "video")[0]
            self.assertEqual(video.get("poster"), f"media/{slug}/{clip}-poster.jpg")
            for attr in ("muted", "playsinline"):
                self.assertIn(attr, video)
            # Tianyu (2026-11-02): "why the last frame before moving to the second highlight is the hook again?" The
            # first slide's long clip plays once and holds its last frame until the roll moves on; repeating, it would
            # show its first frame. The loops, shorter, repeat until their time is up.
            self.assertEqual("loop" in video, clip == "loop", slug)
            self.assertEqual("autoplay" in video, i == 0, slug)  # the script plays each other clip as its slide shows
            if i:
                self.assertEqual(video.get("preload"), "none", slug)
        tabs = tags(re.search(r'<nav class="hl-tabs" aria-label="Highlights">(.*?)</nav>', hl, re.S).group(1), "a")
        self.assertEqual([t.get("href") for t in tabs], [f"#hl-{i}" for i in range(1, len(slides) + 1)])
        for tab, slug in zip(tabs, self.site.highlights):
            pub = own.get(slug) or others[slug]
            self.assertIn(html.escape(pub.short_title or pub.title), tab.get("aria-label"))
        self.assertIn('<button type="button" class="hl-pause" aria-pressed="false">Pause</button>', hl)
        # Tianyu (2026-10-31, on a phone): "Yes add the buttons", the arrows they drew at the clip's sides. They lie over
        # the strip in a stage of their own; on wider screens and without scripts they are hidden (home.css).
        self.assertIn('<div class="hl-stage">\n    <div class="hl-slides">', hl)
        arrows = re.search(r'<div class="hl-arrows">(.*?)</div>', hl, re.S).group(1)
        self.assertEqual([(b.get("type"), b.get("class"), b.get("aria-label")) for b in tags(arrows, "button")],
                         [("button", "hl-prev", "Previous highlight"), ("button", "hl-next", "Next highlight")])
        self.assertEqual(arrows.count("<svg"), 2)
        self.assertLess(hl.index('<div class="hl-arrows">'), hl.index('<nav class="hl-tabs"'))

    def test_coauthored_slides_play_their_own_clips(self):
        # Tianyu (2026-11-05): "for the matter paper use videos from the paper, for the AM paper as well", "junwei's science
        # advances paper also use video". Those slides play clips cut from the papers' movies, longer and with words, which
        # the Publications rows do not: they loop short clips of their own (test_coauthored_rows_loop_clips).
        hl = section(self.page, "highlights")
        self.assertNotIn("hl-media still", hl)
        # "add hai lu's small paper to the highlight to replace chen yu's afm": the suture paper keeps only its row.
        self.assertNotIn('data-slug="suture-interlocking-metamaterials"', hl)
        self.assertIn('<source src="media/suture-interlocking-metamaterials/loop.mp4"', self.pubs)
        for slug in ("active-fabrics", "hierarchical-tessellation", "dual-responsive-skin", "muscle-impedance-sensors"):
            slide = re.search(rf'data-slug="{slug}">(.*?)</article>', hl, re.S).group(1)
            self.assertIn(f'<source src="media/{slug}/highlight.mp4" type="video/mp4">', slide)
            self.assertNotIn("thumb.jpg", slide)
            self.assertNotIn(f"media/{slug}/highlight", self.pubs)

    def test_home_page_tells_search_engines_who_this_is(self):
        # Tianyu (2026-11-09): "attract more people to visit". A search result read only "Tianyu Chen", a common name, and
        # nothing tied the site to the profiles it links to. The title now gives the role and the place, and the page says
        # the site, Google Scholar, LinkedIn and ORCID are one person, with no contact details.
        self.assertIn("<title>Tianyu Chen | Research Associate, Bristol Robotics Laboratory</title>", self.page)
        found = re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.page, re.S)
        self.assertEqual(len(found), 1)
        person = json.loads(found[0])
        self.assertEqual((person["@context"], person["@type"], person["name"], person["url"], person["image"], person["jobTitle"]),
                         ("https://schema.org", "Person", "Tianyu Chen", "https://tianyuchen.com/",
                          "https://tianyuchen.com/assets/img/photo.jpg", "Research Associate"))
        self.assertEqual(person["worksFor"], {"@type": "Organization", "name": "Bristol Robotics Laboratory"})
        self.assertEqual(person["sameAs"], [self.site.links[key] for key in ("scholar", "linkedin", "orcid")])
        self.assertFalse(set(person) & {"email", "telephone", "address"})
        for page in (self.pubs, self.xp):
            self.assertNotIn("ld+json", page)

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
        # The six newest show, and with them any story marked featured (Tianyu, of Lianhe Zaobao's report: "don't
        # hide it in the all news section"); the rest wait under All coverage, which opens without scripts.
        shown = [n for i, n in enumerate(newest) if i < 6 or n.featured]
        newest = shown + [n for n in newest if n not in shown]  # the page's order
        self.assertTrue([n for n in shown[6:] if "zaobao" in n.url])
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
        self.assertEqual(news.count("<details"), 1)
        self.assertEqual(news.split("<details")[0].count('class="news-item"'), len(shown))
        self.assertIn(f"<summary>All coverage ({len(newest)})</summary>", news)

    def test_highlights_motion(self):
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        rules = css_rules(css)
        anywhere = css_rules(outside_media(css))  # the rules that hold at every width
        # Without scripts every slide shows, one under another, and the tabs jump to them. With them, a one-line script
        # in the head marks the page before it draws, so the slides stack in one grid cell from the first paint.
        self.assertNotIn("visibility: hidden", last_rule(rules, ".slide"))
        self.assertIn("grid-area: 1 / 1", last_rule(anywhere, ".js .slide"))
        self.assertIn("visibility: hidden", last_rule(anywhere, ".js .slide"))
        self.assertIn("visibility: visible", last_rule(rules, ".js .slide.on"))
        self.assertIn("display: none", last_rule(rules, "html:not(.js) .hl-pause"))
        # Tianyu (2026-10-31): "Remove the play pause buttom on the phone page"; wider screens keep it.
        phone_rules = css_rules(css.split("@media (max-width: 860px) {")[1].split("\n}")[0])
        self.assertIn("display: none", last_rule(phone_rules, ".hl-pause"))
        self.assertNotIn("display: none", last_rule(css_rules(outside_media(css)), ".hl-pause"))
        head = self.page[:self.page.index("</head>")]
        self.assertIn('<script>document.documentElement.className += " js";</script>', head)
        # A grid column's minimum is its content's width unless set to 0: plain 1fr let a slide's clip widen the column
        # past a phone's screen and cut the text. On a phone the clip stays on top and the text takes the rest.
        slide_rules = [body for selectors, body in rules if ".slide" in selectors]
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)", slide_rules[0])
        self.assertIn("grid-template-columns: minmax(0, 1fr)", slide_rules[-1])
        self.assertIn("grid-template-rows: auto 1fr", slide_rules[-1])
        self.assertIn("grid-template-columns: minmax(0, 1fr)", last_rule(anywhere, ".js .hl-slides"))
        # Tianyu (2026-10-31, on a phone): "Can we make this slidable on phone view". At phone widths the slides lie
        # side by side in a strip that moves under the finger and stops at one slide at a time. The strip reaches the
        # screen's edges, padded so the cards' shadows show, its neighbors out of sight at rest; no scroll bar shows.
        phone = css_rules(css.split("@media (max-width: 860px) {")[1].split("\n}")[0])
        gutter = int(re.search(r"padding-left: (\d+)px", last_rule(phone, ".wrap")).group(1))
        strip = last_rule(phone, ".js .hl-slides")
        for needed in ("display: flex", "overflow-x: auto", "scroll-snap-type: x mandatory", "scrollbar-width: none",
                       f"margin: -24px -{gutter}px -48px", f"padding: 24px {gutter}px 48px"):
            self.assertIn(needed, strip)
        self.assertGreaterEqual(int(re.search(r"gap: (\d+)px", strip).group(1)), gutter)
        self.assertIn("display: none", last_rule(phone, ".js .hl-slides::-webkit-scrollbar"))
        card = last_rule(phone, ".js .slide")
        for needed in ("flex: 0 0 100%", "scroll-snap-align: center", "scroll-snap-stop: always", "opacity: 1",
                       "visibility: visible"):
            self.assertIn(needed, card)
        self.assertTrue(all(s.startswith(".js ") for selectors, _ in phone for s in selectors if ".hl-slides" in s))
        # Tianyu: "on a phone the labels 1 2 3... for the research highlights are underneath so it's inconvenient to
        # switch". On a phone the numbers sit above the slide in one row, down to a 320 px screen, drawn over the
        # strip's shadow padding so a tap on them reaches them. The arrows lie over the shown clip's square, letting
        # swipes through between them; both stay under the menu bar.
        self.assertIn("display: none", last_rule(anywhere, ".hl-arrows"))
        self.assertIn("position: relative", last_rule(anywhere, ".hl-stage"))
        numbers = last_rule(phone, ".hl-tabs")
        for needed in ("order: -1", "position: relative", "z-index: 1", "flex-flow: row nowrap"):
            self.assertIn(needed, numbers)
        for needed in ("flex: 1 1 0", "height: 36px"):
            self.assertIn(needed, last_rule(phone, ".hl-tab"))
        overlay = last_rule(phone, ".js .hl-arrows")
        for needed in ("display: block", "position: absolute", "inset: 0 0 auto", "aspect-ratio: 1 / 1",
                       "pointer-events: none", "z-index: 1"):
            self.assertIn(needed, overlay)
        for needed in ("pointer-events: auto", "width: 44px", "height: 44px"):
            self.assertIn(needed, last_rule(phone, ".hl-arrows button"))
        self.assertIn("z-index: 10", last_rule(rules, ".nav"))
        # Tianyu: "when sliding the highlight cards, the number label only change after the card finish moving. Please
        # make it moving along with the sliding card". On a phone a dark pill glides over the numbers as the strip
        # moves, holding the numbers again in black, laid out as the row is; it lets taps through to the numbers and
        # has no transition, which would make it trail the finger. There the current number's own chip is plain, and
        # wider screens keep their orange current chip and no pill.
        self.assertIn("display: none", last_rule(anywhere, ".hl-pill"))
        self.assertIn("background: var(--orange)", last_rule(anywhere, '.hl-tab[aria-current="true"]'))
        pill = last_rule(phone, ".js .hl-pill")
        for needed in ("display: block", "position: absolute", "overflow: hidden", "border-radius: 10px",
                       "background: var(--orange)", "pointer-events: none"):
            self.assertIn(needed, pill)
        self.assertNotIn("transition", pill)
        tab, current = last_rule(phone, ".hl-tab"), last_rule(anywhere, ".hl-tab")
        self.assertIn("background: #15181d", last_rule(phone, '.js .hl-tab[aria-current="true"]'))
        self.assertIn("color: #aab2bf", last_rule(phone, '.js .hl-tab[aria-current="true"]'))
        copy_row, copy_number = last_rule(phone, ".hl-pill-numbers"), last_rule(phone, ".hl-pill-numbers span")
        for needed in ("justify-content: center", "gap: 4px"):
            self.assertIn(needed, numbers)
            self.assertIn(needed, copy_row)
        for needed in ("flex: 1 1 0", "max-width: 44px", "height: 36px"):
            self.assertIn(needed, tab)
            self.assertIn(needed, copy_number)
        for needed in ("font-size: 14px", "font-weight: 600"):
            self.assertIn(needed, current)
            self.assertIn(needed, copy_number)
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
        # On a phone the script scrolls the strip for the roll and the tabs, and shows the slide a swipe stops on; it
        # knows a phone by the stylesheet's own query.
        slideshow = js[js.index('var box = document.querySelector(".highlights")'):js.index("// The other clips")]
        self.assertIn('window.matchMedia("(max-width: 860px)")', slideshow)
        for needed in ("scrollTo(", 'addEventListener("scroll"', 'addEventListener("touchstart"'):
            self.assertIn(needed, slideshow)
        # A clip the strip brings into view starts once it is there, never while still off screen.
        self.assertRegex(slideshow, r"if \(arrived\) \{\s*begin\(i\);")
        # The pill is the script's, hidden from screen readers, and follows the strip frame by frame; where the
        # slideshow is, and what plays, still change only once the strip stops.
        self.assertIn('pill.setAttribute("aria-hidden", "true")', slideshow)
        self.assertIn("window.requestAnimationFrame(glide)", slideshow)
        glide = re.search(r"var glide = function \(\) \{(.*?)\n    \};", slideshow, re.S).group(1)
        self.assertNotIn("show(", glide)
        self.assertIn("getBoundingClientRect", glide)
        # The arrows step like the tabs, round from the last slide to the first and back, and the roll goes on.
        for arrow, step in (("prevArrow", r"\(at \+ slides\.length - 1\) % slides\.length"),
                            ("nextArrow", r"\(at \+ 1\) % slides\.length")):
            handler = re.search(arrow + r'\.addEventListener\("click", function \(\) \{(.*?)\}\);', slideshow, re.S)
            self.assertRegex(handler.group(1), r"^\s*show\(" + step + r"\);\s*$")
        # The first slide's clip runs about 19 s. The roll took a clip's length when its slide showed, and 9 s if the
        # clip had not loaded yet, which would cut it off mid-animation on a phone: the time left is taken again once
        # the clip plays, once per showing, since a looping clip may report playing again.
        self.assertIn("(video.duration - video.currentTime) * 1000", slideshow)
        self.assertRegex(slideshow, r"if \(i === at && !timed\) \{\s*timed = true;\s*schedule\(\);")
        self.assertRegex(slideshow, r"var show = function \(i, swiped\) \{[^}]*?timed = false;")
        # Waiting for "loadeddata", which fires once per clip and never after a rewind, once stopped slides 2 onward.
        self.assertNotIn('"loadeddata"', js)
        self.assertNotIn(".mosaic", js)

    def test_highlight_clips_on_phones(self):
        # Tianyu: "Why the research highlight videos is black on my phone". A phone loads a clip only when asked to play
        # it (an iPhone never preloads one), so the slideshow waited for clips that never loaded, and it rewound clips
        # with no frames yet, which on Safari hides the poster over the near-black frame. Each clip's poster now lies
        # over it as an image until the clip plays, a clip plays as soon as its slide shows, and only a clip that has
        # frames rewinds.
        hl = section(self.page, "highlights")
        clips = re.findall(r'data-slug="([a-z0-9-]+)"><a class="hl-media"[^>]*>(.*?)</a>', hl, re.S)
        self.assertEqual(len(clips), 10)
        for slug, body in clips:
            pub = next(p for p in [*self.papers, *self.others] if p.slug == slug)
            clip = pub.highlight_clip or "loop"  # a slide's own clip (test_highlights)
            self.assertIn(f'<img class="hl-poster" src="media/{slug}/{clip}-poster.jpg" alt="">', body)
            self.assertLess(body.index("<video"), body.index('class="hl-poster"'))  # drawn over the clip
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        rules = css_rules(css)
        self.assertIn("position: relative", [body for selectors, body in rules if ".hl-media" in selectors][0])
        # Without scripts nothing hides it, so the image waits for them; the clip's own poster serves until then.
        self.assertIn("display: none", [body for selectors, body in rules if ".hl-media .hl-poster" in selectors][0])
        self.assertRegex(css, r"\.js \.hl-media \.hl-poster \{[^}]*display: block;[^}]*position: absolute")
        self.assertRegex(css, r"\.hl-media\.playing \.hl-poster \{[^}]*opacity: 0")
        js = (ROOT / "assets" / "js" / "home.js").read_text(encoding="utf-8")
        slideshow = js[js.index('var box = document.querySelector(".highlights")'):js.index("// The other clips")]
        self.assertIn('addEventListener("playing"', slideshow)
        self.assertIn('classList.add("playing")', slideshow)
        self.assertIn("video.readyState >= 2", slideshow)
        self.assertNotIn("readyState >= 1", slideshow)
        self.assertNotIn("canplay", slideshow)

    def test_visit_counter(self):
        # Tianyu chose GoatCounter (2026-10-30) and made the site cty9525785. Every page loads the site's own reviewed
        # copy of count.js (nothing loads from another site); with no count address, nothing. The footer says nothing
        # of it: Tianyu asked to delete the line that did.
        tag = (f'<script data-goatcounter="https://cty9525785.goatcounter.com/count" async '
               f'src="{versioned("assets/js/count.js")}"></script>')
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

    def test_assets_carry_their_version(self):
        # Tianyu saw the new page in the old stylesheet: GitHub Pages lets a browser keep a file ten minutes, and the
        # old site's stylesheet had the same name. Each stylesheet and script address carries its file's hash, so a
        # changed file has a new address and arrives with the page that needs it.
        for page in (self.page, self.pubs, self.xp):
            refs = ([t.get("href") for t in tags(page, "link") if t.get("rel") == "stylesheet"]
                    + [t.get("src") for t in tags(page, "script") if t.get("src")])
            self.assertEqual(len(refs), len([r for r in refs if "?v=" in r]))
            for ref in refs:
                self.assertEqual(ref, versioned(ref.split("?")[0]))

    def test_experience_page(self):
        # The roles, degrees and skills under the shared menu, styles and footer; with no clips or filters, no script
        # but the visit counter.
        meta = {t.get("property") or t.get("name"): t.get("content") for t in tags(self.xp, "meta")}
        # The tab is "About me" (Tianyu, 2026-11-04: "shall we use about me as the name of the tab?"), since the page now
        # holds awards, teaching and talks too; its address stays, so links already shared keep working.
        self.assertIn("<title>About me | Tianyu Chen</title>", self.xp)
        self.assertEqual(meta["description"], "Tianyu Chen’s roles, education, skills, awards, teaching and talks.")
        self.assertEqual(meta["og:url"], "https://tianyuchen.com/experience.html")
        self.assertEqual([t.get("href") for t in tags(self.xp, "link") if t.get("rel") == "stylesheet"],
                         [versioned("assets/css/home.css")])
        self.assertEqual([t.get("src") for t in tags(self.xp, "script") if t.get("src")],
                         [versioned("assets/js/count.js")])
        main = re.search(r"<main>(.*?)</main>", self.xp, re.S).group(1)
        self.assertEqual(re.findall(r'<section id="([a-z-]+)"', main), ["experience"])
        self.assertIn("<h1>About me", main)
        self.assertIn('<h3 class="edu-h">Experience</h3>\n      <ol class="xp">', main)  # the roles keep their name
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
                         [versioned("assets/css/home.css")])
        self.assertEqual([t.get("src") for t in tags(self.pubs, "script") if t.get("src")],
                         [versioned("assets/js/home.js"), versioned("assets/js/count.js")])
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
        # The page's own script file and the visit counter, plus two small scripts in the head: the one-line class
        # setter the slideshow's layout needs, and the wait for the page's fonts.
        self.assertEqual([t.get("src") for t in tags(self.page, "script") if t.get("src")],
                         [versioned("assets/js/home.js"), versioned("assets/js/count.js")])
        self.assertEqual(self.page.count("<script>"), 2)

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
        # Drafted from the CV, the text is marked until Tianyu confirms it; Tianyu confirmed it on 2026-10-30 and its
        # awards, teaching and talks on 2026-11-04.
        self.assertNotIn('class="draft"', xp)
        draft = render_experience(replace(self.site, cv_status="draft"))
        self.assertEqual(section(draft, "experience").count('<span class="draft">draft</span>'), 1)

    def test_awards_teaching_and_talks(self):
        # Tianyu (2026-11-03): under the skills, the short lists in the narrow column as Education is above them, and the
        # talks' long titles in the wide one.
        xp = section(self.xp, "experience")
        self.assertGreater(xp.index('<div class="split cv-more">'), xp.index('<div class="skills">'))
        more = xp[xp.index('<div class="split cv-more">'):]
        self.assertEqual(re.findall(r'<h3 class="edu-h">(.*?)</h3>', more), ["Awards", "Teaching", "Talks and posters"])
        lists = re.findall(r'<ul class="edu">(.*?)</ul>', more, re.S)
        items = [re.findall(r"<li>(.*?)</li>", found, re.S) for found in lists]
        self.assertEqual([len(found) for found in items],
                         [len(self.site.awards), len(self.site.teaching), len(self.site.talks)])
        for li, a in zip(items[0], self.site.awards):
            self.assertEqual(li, f'<b>{html.escape(a.name)}</b><span>{html.escape(a.org)}, <span class="nb">{a.year}'
                                 "</span></span>")
        for li, t in zip(items[1], self.site.teaching):
            self.assertEqual(li, f'<b>{t.role}</b><span>{html.escape(t.org)}, <span class="nb">{t.years}</span></span>'
                                 f'<p class="courses">{html.escape("; ".join(t.courses))}</p>')
        for li, t in zip(items[2], self.site.talks):
            self.assertEqual(li, f'<p class="when">{t.year} · {t.kind}</p><b>{html.escape(t.title)}</b>'
                                 f"<span>{'<br>'.join(html.escape(v) for v in t.venues)}</span>")
        self.assertIn("Zhou Peiyuan", self.xp)  # the national prize, which Tianyu asked to add back
        self.assertNotIn("Smartcar", self.xp)  # the other student prizes stay on the CV
        # A range of years does not break at its dash in the narrow column.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        self.assertIn("white-space: nowrap", last_rule(rules, ".edu .nb"))
        # None of it shows until there is something to show.
        bare = render_experience(replace(self.site, awards=[], teaching=[], talks=[]))
        self.assertNotIn('class="split cv-more"', bare)

    def test_highlights_on_a_black_band(self):
        # The design Tianyu chose from the mockups (2026-11-04, "A is better"): the highlights on a full-width black band
        # with no card around the footage, whose own black meets the band's, and the words light on it.
        band = self.page[self.page.index('<div class="hl-band">'):]
        self.assertTrue(band.startswith('<div class="hl-band"><section id="highlights" class="wrap highlights">'))
        self.assertRegex(band[:band.index('<section id="news"')], r"</section></div>\s*$")
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        rules = css_rules(outside_media(css))
        self.assertIn("background: #000", last_rule(rules, ".hl-band"))
        slide = last_rule(rules, ".slide")
        self.assertIn("background: transparent", slide)
        self.assertNotIn("box-shadow", slide)
        for needed in ("background: #000", "border-radius: 14px", "overflow: hidden"):
            self.assertIn(needed, last_rule(rules, ".hl-media"))
        self.assertNotIn("background", last_rule(rules, ".hl-media.still"))  # figures float on the black too

        def words(selector):
            return re.search(r"(?<![-\w])color: (#[0-9a-f]{6}|var\(--orange\))", last_rule(rules, selector)).group(1)

        orange = re.search(r"--orange: (#[0-9a-f]{6})", css).group(1)
        for selector in (".hl-head h2", ".hl-text h3", ".hl-text .one", ".hl-text .authors", ".hl-text .authors strong",
                         ".hl-text .venue", ".hl-text .label", ".hl-text .more a"):
            self.assertGreaterEqual(contrast(words(selector).replace("var(--orange)", orange), "#000000"), 4.5, selector)
        self.assertEqual(words(".hl-text .label"), "var(--orange)")
        self.assertEqual(words(".hl-text .more a"), "var(--orange)")
        self.assertGreaterEqual(contrast(words(".hl-tab"), "#15181d"), 4.5)
        self.assertIn("background: #15181d", last_rule(rules, ".hl-tab"))
        self.assertIn("color: #000000", last_rule(rules, '.hl-tab[aria-current="true"]'))
        self.assertGreaterEqual(contrast(orange, "#000000"), 4.5)
        # A control that lightened on hover would lose its light words on the black.
        self.assertIn("background: #15181d", last_rule(rules, ".hl-pause:hover"))
        self.assertIn("background: transparent", last_rule(rules, ".hl-pause"))
        self.assertIn("outline-color: var(--orange)", last_rule(rules, ".hl-band a:focus-visible"))
        # The news starts with room under the band, on a phone too.
        self.assertIn("padding-top: 72px", last_rule(rules, ".news"))
        phone = css_rules(css.split("@media (max-width: 860px) {")[1].split("\n}")[0])
        self.assertIn("padding-top: 64px", last_rule(phone, ".news"))
        self.assertIn("padding-top: 48px", last_rule(phone, ".highlights"))
        self.assertIn("color: #000000", last_rule(phone, ".hl-pill-numbers span"))

    def test_orange_replaces_blue(self):
        # The hook animation's orange, darkened for words on white, and at full strength on black.
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        accent = re.search(r"--accent: (#[0-9a-f]{6})", css).group(1)
        self.assertEqual(accent, "#c2410c")
        self.assertGreaterEqual(contrast(accent, "#ffffff"), 4.5)
        self.assertNotIn("#2563eb", css)
        # The headline's two clauses on their own lines, the second in the accent, larger on a wide screen.
        rules = css_rules(outside_media(css))
        clause = last_rule(rules, ".hero h1 span")
        self.assertIn("display: block", clause)
        self.assertIn("color: var(--accent)", clause)
        wide = css_rules(css.split("@media (min-width: 1080px) {")[1].split("\n}")[0])
        self.assertIn("font-size: min(40px, 3.6vw)", last_rule(wide, "h1"))
        # The Experience page's draft mark stays inline.
        self.assertEqual(last_rule(rules, "h1 span"), "")
        self.assertIn("text-decoration-color: var(--orange)", last_rule(rules, ".bio a"))

    def test_footer_on_a_black_band(self):
        # The pages close on black. The mockup's address at 44 px was "too big" (Tianyu, 2026-11-04): it keeps its 20 px.
        rules = css_rules(outside_media((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")))
        footer = last_rule(rules, "footer")
        self.assertIn("background: #000", footer)
        self.assertNotIn("border-top", footer)
        self.assertGreaterEqual(contrast(re.search(r"(?<![-\w])color: (#[0-9a-f]{6})", footer).group(1), "#000000"), 4.5)
        self.assertIn("font-size: 20px", last_rule(rules, "footer .contact"))
        self.assertIn("color: #ffffff", last_rule(rules, "footer .contact"))
        self.assertIn("color: var(--orange)", last_rule(rules, "footer .contact a"))
        self.assertIn("color: #ffffff", last_rule(rules, "footer a"))
        self.assertIn("color: var(--orange)", last_rule(rules, "footer a:hover"))
        self.assertNotIn("border-bottom", last_rule(rules, ".band"))  # no hairline between the page and the black

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

    def test_arrows_fade_on_a_phone(self):
        # Tianyu (2026-11-04): "on the phone's view please make the arrows disappear aftera while, otherwise it would cover
        # the content". They show when they come into view and when a finger lifts from the slides, then fade, and one with
        # the keyboard's focus stays seen. A faded arrow lets a swipe that starts where it sits move the slides, so a finger
        # that lands does not bring them back, nor does one that scrolled the page, nor the roll moving on. Coming into
        # view goes by the arrow itself, since a phone held sideways never has most of the square clip on its screen.
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        phone = css_rules(css.split("@media (max-width: 860px) {")[1].split("\n}")[0])
        self.assertIn("transition: opacity 0.3s", last_rule(phone, ".hl-arrows button"))
        faded = last_rule(phone, ".hl-arrows.faded button")
        self.assertIn("opacity: 0", faded)
        self.assertIn("pointer-events: none", faded)
        focused = last_rule(phone, ".hl-arrows.faded button:focus-visible")
        self.assertIn("opacity: 1", focused)
        self.assertIn("pointer-events: auto", focused)
        calm = css_rules(css.split("@media (prefers-reduced-motion: reduce) {")[1])
        self.assertIn("transition: none", last_rule(calm, ".hl-arrows button"))
        script = (ROOT / "assets" / "js" / "home.js").read_text(encoding="utf-8")
        self.assertIn("var ARROWS = 3000;", script)
        show = re.search(r"var showArrows = function \(\) \{(.*?)\n    \};", script, re.S).group(1)
        self.assertIn('arrows.classList.remove("faded")', show)
        self.assertIn("window.clearTimeout(fading)", show)
        self.assertRegex(show, r'window\.setTimeout\(function \(\) \{\s*arrows\.classList\.add\("faded"\);\s*\}, ARROWS\)')
        landed = re.search(r'stage\.addEventListener\("touchstart", function \(\) \{(.*?)\}, \{ passive: true \}\);', script, re.S).group(1)
        self.assertIn("pageAt = window.scrollY;", landed)
        self.assertNotIn("showArrows", landed)
        self.assertRegex(script, r'stage\.addEventListener\("touchend", function \(\) \{\s*if \(window\.scrollY === pageAt\) \{\s*showArrows\(\);')
        self.assertIn('stage.addEventListener("mousemove", showArrows);', script)
        self.assertIn('stage.addEventListener("focusin", showArrows);', script)
        self.assertIn("{ threshold: 0.9 }).observe(nextArrow)", script)
        self.assertNotIn("showArrows", re.search(r"var show = function \(i, swiped\) \{(.*?)\n    \};", script, re.S).group(1))

    def test_filtered_theme_sits_as_the_first_does(self):
        # Tianyu: "why the gap under the different tabs are different": 32 px under the filters with the first theme shown,
        # 52 px with another, because "+" also matched the hidden theme before it. Only a theme shown above earns the space.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))
        self.assertIn("margin-top: 52px", last_rule(rules, ".topic:not([data-off]) ~ .topic:not([data-off])"))
        self.assertEqual(last_rule(rules, ".topic + .topic"), "")

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

    def test_coauthored_rows_loop_clips(self):
        # Tianyu (2026-11-05), once those slides had their videos: "update also the thumbnails in the publication page". For
        # the AM paper this replaces "for the am paper this figure maybe better as thumbnail" (2026-10-30).
        for slug in ("active-fabrics", "hierarchical-tessellation", "dual-responsive-skin", "muscle-impedance-sensors"):
            body = entries(self.pubs)[slug]
            self.assertEqual(tags(body, "img"), [], slug)
            self.assertIn(f'<source src="media/{slug}/loop.mp4"', body)
            self.assertEqual(tags(body, "video")[0].get("poster"), f"media/{slug}/loop-poster.jpg")

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
        # Tianyu (2026-11-04) removed the line about where the movies and figures come from; each entry names its paper.
        self.assertNotIn("Movies and figures", footer)
        # impeccable critique (Tianyu chose "Phone first screen + contact"): the address itself shows, so a reader
        # without a mail app can copy it, and the page ends with an invitation to write.
        email = self.site.links["email"]
        self.assertIn(f'<p class="contact">Get in touch: <a href="mailto:{email}">{email}</a></p>', footer)
        self.assertEqual([text for _, text in anchors(footer)], [email, "Google Scholar", "LinkedIn", "ORCID"])
        self.assertNotIn("jonbarron", self.page)  # the home page no longer uses his design

    def test_text_contrast(self):
        # impeccable critique (Tianyu: "Darker gray"): the headline's gray half was 2.42:1, under the 3:1 that large
        # text needs; the role line and the Co-authored labels were 4.44:1 on the gray pill, under 4.5:1.
        rules = css_rules((ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8"))

        def color(selector):
            found = [re.search(r"(?<![-\w])color: (#[0-9a-f]{6})", body) for selectors, body in rules if selector in selectors]
            return [m.group(1) for m in found if m][-1]

        for selector in (".co-label",):
            self.assertGreaterEqual(contrast(color(selector), "#f6f7f9"), 4.5, selector)
        # The menu bar is ground glass (Tianyu: "add some glass feeling on this banner", "like the ground glass"): a
        # white wash over a strong blur, with a faint grain. Over the black band a 0.72 wash turned a dirty gray, so it
        # is 0.88 (shown to Tianyu in the design they chose, 2026-11-04), still a wash and not a solid bar. Even over
        # black, the white wash with the grain on it, its tabs keep 4.5:1.
        nav = last_rule(rules, ".nav")
        alpha = float(re.search(r"background-color: rgba\(255, 255, 255, ([\d.]+)\)", nav).group(1))
        self.assertEqual(alpha, 0.88)
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
        # The buttons sit in even rows (LinkedIn once wrapped onto a row of its own): two by two since ORCID joined,
        # each showing only its last word, "Scholar", while screen readers still read "Google Scholar".
        self.assertRegex(phone, r"\.hero \.links \{[^}]*display: grid;[^}]*grid-template-columns: 1fr 1fr")
        self.assertRegex(phone, r"\.hero \.btn \{[^}]*height: 44px")  # a finger's size again on a phone
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
        # The italic too where a page uses it (journal names), since it was the one left to arrive late.
        normal = "assets/fonts/inter/inter-latin-wght-normal.woff2"
        italic = "assets/fonts/inter/inter-latin-wght-italic.woff2"
        for page, wanted in ((self.page, {normal, italic}), (self.pubs, {normal, italic}), (self.xp, {normal})):
            preloads = [t for t in tags(page, "link") if t.get("rel") == "preload"]
            self.assertEqual({t.get("href") for t in preloads}, wanted)
            self.assertEqual(italic in {t.get("href") for t in preloads}, "<em>" in page)
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
        self.assertTrue(faces and all("'Inter'" in f and "font-display: block" in f for f in faces))
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
            assets = ([t.get("href") for t in tags(page, "link") if t.get("rel") != "canonical"]  # a label, not a file
                      + [t.get("src") for t in tags(page, "script")])
            for url in assets:
                self.assertFalse(url and url.startswith(("http:", "https:", "//")), url)

    def test_build_writes_pages(self):
        written = build(ROOT)
        self.assertEqual(len(written), 11)  # the nine pages, then the sitemap and robots.txt (test_site)
        self.assertTrue(all(path.exists() for path in written))
        self.assertIn(ROOT / "index.html", written)
        self.assertIn(ROOT / "publications.html", written)
        self.assertIn(ROOT / "experience.html", written)
        self.assertIn(ROOT / "papers" / "graded-substrate-thin-films" / "index.html", written)


if __name__ == "__main__":
    unittest.main()
