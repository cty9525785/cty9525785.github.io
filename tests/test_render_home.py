import html
import json
import re
import unittest
from dataclasses import replace
from pathlib import Path

from tests.htmlutil import tags
from tools.build import build, render_home
from tools.content import Segment, Tile, TileInput, load_papers, load_site

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r'<tr class="paper-row( highlight)?" data-slug="([a-z0-9-]+)">(.*?)</tr>', re.S)


def table(page, name):
    return re.search(rf'<table class="papers" id="{name}"><tbody>(.*?)</tbody></table>', page, re.S).group(1)


def rows(page):
    return ROW.findall(table(page, "research"))


def other_rows(page):
    return ROW.findall(table(page, "other-publications"))


def row_body(page, slug):
    return {s: body for _, s, body in rows(page)}[slug]


def link_bar(page):
    return re.search(r'<p class="links">(.*?)</p>', page, re.S).group(1)


class RenderHomeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = load_site(ROOT / "content" / "site.toml")
        cls.papers, cls.others = load_papers(ROOT / "content" / "papers.toml")
        cls.page = render_home(cls.site, cls.papers, cls.others)

    def test_header(self):
        pending = replace(self.site, photo="assets/img/photo-placeholder.svg",
                          links={k: "TODO: later" for k in ("email", "cv", "scholar", "linkedin", "github")})
        page = render_home(pending, self.papers, self.others)
        self.assertIn(f'<p class="name">{html.escape(self.site.name)}</p>', page)
        self.assertIn(html.escape(self.site.tagline), page)
        photos = [t for t in tags(page, "img") if t.get("src") == "assets/img/photo-placeholder.svg"]
        self.assertEqual(len(photos), 1)
        anchors = re.findall(r"<a ([^>]*)>([^<]*)</a>", link_bar(page))
        self.assertEqual([label for _, label in anchors], ["Email", "CV", "Scholar", "LinkedIn", "GitHub"])
        for attrs, label in anchors:
            self.assertIn('class="placeholder"', attrs, label)

    def test_filled_links(self):
        links = {**self.site.links, "email": "someone@example.invalid", "scholar": "https://scholar.example/x",
                 "cv": "TODO: later"}
        bar = link_bar(render_home(replace(self.site, links=links), self.papers, self.others))
        self.assertIn('<a href="mailto:someone@example.invalid">Email</a>', bar)
        self.assertIn('<a href="https://scholar.example/x">Scholar</a>', bar)
        self.assertIn('class="placeholder"', bar)  # the CV is still a placeholder

    def test_bio_links(self):
        # Tianyu: "add the url for vivohub and my previous professor's lab website in the bio".
        bio = "I work in [the lab](https://example.invalid/lab?a=1&b=2) <here>."
        page = render_home(replace(self.site, bio=bio), self.papers, self.others)
        self.assertIn('I work in <a href="https://example.invalid/lab?a=1&amp;b=2">the lab</a> &lt;here&gt;.', page)

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
        self.assertEqual({t.get("href") for t in preloads},
                         {"assets/fonts/lato/lato-latin-400-normal.woff2", "assets/fonts/lato/lato-latin-700-normal.woff2",
                          "assets/fonts/lato/lato-latin-400-italic.woff2"})
        for t in preloads:
            self.assertEqual((t.get("as"), t.get("type")), ("font", "font/woff2"))
            self.assertIn("crossorigin", t)  # fonts load in CORS mode; without it the preload is fetched twice

    def test_cv_link(self):
        bar = link_bar(self.page)
        self.assertIn('<a href="files/Tianyu-Chen-CV.pdf">CV</a>', bar)
        self.assertNotIn("placeholder", bar)

    def test_draft_bio_is_marked(self):
        draft = render_home(replace(self.site, bio="I study robots.", bio_status="draft"), self.papers, self.others)
        self.assertIn('I study robots. <span class="draft">draft</span>', draft)
        confirmed = render_home(replace(self.site, bio="I study robots.", bio_status="confirmed"), self.papers, self.others)
        self.assertIn("I study robots.", confirmed)
        self.assertNotIn('I study robots. <span class="draft">', confirmed)

    def test_rows_order_and_highlight(self):
        found = rows(self.page)
        self.assertEqual([slug for _, slug, _ in found], [
            "scale-inspired-robotic-structures",
            "stiffness-driven-control",
            "programmable-morphing-structure",
            "shear-banding-gradient-metals",
            "amorphous-thin-films",
            "graded-substrate-thin-films",
        ])
        self.assertEqual([bool(h) for h, _, _ in found], [True, True] + [False] * 4)

    def test_row_loop_attributes(self):
        body = row_body(self.page, "scale-inspired-robotic-structures")
        video = tags(body, "video")[0]
        for attr in ("autoplay", "muted", "loop", "playsinline"):
            self.assertIn(attr, video)
        self.assertEqual(video.get("poster"), "media/scale-inspired-robotic-structures/loop-poster.jpg")
        self.assertEqual(tags(body, "source")[0].get("src"), "media/scale-inspired-robotic-structures/loop.mp4")

    def test_thumbnails_carry_no_labels(self):
        # Tianyu: "no need to add illustration or paper figure for the thumbnails, even the x times can be removed".
        paper = next(p for p in self.papers if p.slug == "scale-inspired-robotic-structures")
        for tile in (paper.tile, Tile("drawing", drawing="films"), None):
            page = render_home(self.site, [replace(paper, tile=tile)], self.others)
            self.assertNotIn("clip-label", page)
            for text in ("Illustration", "Paper figure", "× speed", "Real time"):
                self.assertNotIn(text, page)
        self.assertEqual([t.get("src") for t in tags(self.page, "script")], [])

    def test_row_thumb(self):
        paper = next(p for p in self.papers if p.slug == "graded-substrate-thin-films")
        body = row_body(render_home(self.site, [replace(paper, tile=None)], self.others), paper.slug)
        self.assertEqual(tags(body, "video"), [])
        img = tags(body, "img")[0]
        self.assertEqual(img.get("src"), "media/graded-substrate-thin-films/thumb.jpg")
        self.assertEqual(img.get("loading"), "lazy")
        self.assertTrue(img.get("alt"))

    def test_row_links(self):
        dois = {p.slug: p.doi for p in self.papers}
        for _, slug, body in rows(self.page):
            hrefs = [a.get("href") for a in tags(body, "a")]
            self.assertIn(f"papers/{slug}/index.html", hrefs)
            self.assertIn(f"https://doi.org/{dois[slug]}", hrefs)

    def test_other_rows(self):
        # Tianyu's request: the co-authored papers get rows like the others, which point to the publisher.
        found = other_rows(self.page)
        self.assertEqual([slug for _, slug, _ in found], [o.slug for o in self.others])
        self.assertEqual({bool(h) for h, _, _ in found}, {False})
        for (_, slug, body), o in zip(found, self.others):
            hrefs = [a.get("href") for a in tags(body, "a")]
            self.assertEqual(set(hrefs), {f"https://doi.org/{o.doi}"}, slug)  # figure, title and "paper" alike
            self.assertGreaterEqual(len(hrefs), 3, slug)
            self.assertIn(">paper</a>", body)
            self.assertEqual(body.count("<strong>Tianyu Chen</strong>"), 1, slug)
            self.assertIn(f'<span class="papertitle">{html.escape(o.title)}</span>', body)
            self.assertIn(f"<em>{html.escape(o.citation)}</em>", body)

    def test_other_row_media(self):
        o = replace(self.others[0], tile=None)  # a row without a clip shows its figure, or what is missing
        body = other_rows(render_home(self.site, self.papers, [replace(o, thumb="")]))[0][2]
        img = tags(body, "img")[0]
        self.assertEqual((img.get("src"), img.get("loading")), (f"media/{o.slug}/thumb.jpg", "lazy"))
        self.assertTrue(img.get("alt"))
        body = other_rows(render_home(self.site, self.papers, [replace(o, thumb="TODO: needs the PDF")]))[0][2]
        self.assertEqual(tags(body, "img"), [])
        self.assertIn('<span class="placeholder">TODO: needs the PDF</span>', body)

    def test_other_row_plays_its_clip(self):
        # A co-authored row with a tile loops it, as a first-author row does.
        tile = Tile("clip", "b.graph", [TileInput("S2", 1.0, 6.0)], [Segment(0.0, 2.0)])
        o = replace(self.others[0], thumb="", tile=tile)
        body = other_rows(render_home(self.site, self.papers, [o]))[0][2]
        self.assertEqual(tags(body, "video")[0].get("poster"), f"media/{o.slug}/loop-poster.jpg")
        self.assertIn(f'<source src="media/{o.slug}/loop.mp4"', body)
        self.assertEqual(tags(body, "img"), [])

    def test_other_row_marks_equal_contributors(self):
        body = {slug: b for _, slug, b in other_rows(self.page)}["active-fabrics"]
        self.assertIn("Xudong Yang†, Yu Chen†, <strong>Tianyu Chen</strong>, Junwei Li, Yifan Wang "
                      "(†&nbsp;equal contribution)", body)
        self.assertNotIn("†", {slug: b for _, slug, b in other_rows(self.page)}["thermally-responsive-actuators"])

    def test_other_row_text(self):
        o = replace(self.others[0], one_line="What the paper shows.")
        draft = other_rows(render_home(self.site, self.papers, [replace(o, summary_status="draft")]))[0][2]
        self.assertIn('<p>What the paper shows. <span class="draft">draft</span></p>', draft)
        confirmed = other_rows(render_home(self.site, self.papers, [replace(o, summary_status="confirmed")]))[0][2]
        self.assertIn("<p>What the paper shows.</p>", confirmed)
        pending = other_rows(render_home(self.site, self.papers, [replace(o, doi="TODO: look up by title")]))[0][2]
        self.assertNotIn("doi.org", pending)
        self.assertIn('<span class="placeholder">TODO: look up by title</span>', pending)

    def test_footer_credit_barron(self):
        self.assertIn('href="https://github.com/jonbarron/jonbarron.github.io"', self.page)

    def test_responsive_css(self):
        css = (ROOT / "assets" / "css" / "home.css").read_text(encoding="utf-8")
        block = re.search(r"@media \(max-width: 600px\) \{(.*?)\n\}", css, re.S)
        self.assertIsNotNone(block)
        self.assertIn("display: block", block.group(1))

    def test_relative_paths_only(self):
        self.assertIsNone(re.search(r'(src|href)="/[^/]', self.page))

    def test_no_third_party_assets(self):
        assets = [t.get("href") for t in tags(self.page, "link")] + [t.get("src") for t in tags(self.page, "script")]
        for url in assets:
            self.assertFalse(url and url.startswith(("http:", "https:", "//")), url)

    def test_build_writes_pages(self):
        written = build(ROOT)
        self.assertEqual(len(written), 7)
        self.assertTrue(all(path.exists() for path in written))
        self.assertIn(ROOT / "index.html", written)
        self.assertIn(ROOT / "papers" / "graded-substrate-thin-films" / "index.html", written)


if __name__ == "__main__":
    unittest.main()
