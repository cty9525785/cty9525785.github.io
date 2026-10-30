import re
import unittest
from dataclasses import replace
from pathlib import Path

from tests.htmlutil import section, tags, versioned
from tools.build import author_html, read_body, render_paper, venue_html
from tools.content import load_papers, load_site

ROOT = Path(__file__).resolve().parents[1]
TRACKERS = ("googletagmanager", "google-analytics", "gtag(", "analytics.js", "clarity.ms", "hotjar", "plausible")
SAILS = "scale-inspired-robotic-structures"
SCIADV = "stiffness-driven-control"
IJMS = "programmable-morphing-structure"
IJSS2019 = "graded-substrate-thin-films"


def paper_head(page: str) -> str:
    return re.search(r'<header class="paper-head">.*?</header>', page, re.S).group(0)


class RenderPaperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = load_site(ROOT / "content" / "site.toml")
        papers, _ = load_papers(ROOT / "content" / "papers.toml")
        cls.p = {p.slug: p for p in papers}
        cls.body = {slug: read_body(ROOT, slug) for slug in cls.p}
        cls.html = {slug: render_paper(p, cls.site, cls.body[slug]) for slug, p in cls.p.items()}

    def test_every_paper_has_a_body(self):
        bodies = {p.stem for p in (ROOT / "content" / "pages").glob("*.html")}
        self.assertEqual(bodies, set(self.p))

    def test_body_is_included(self):
        for slug, page in self.html.items():
            self.assertIn(self.body[slug].strip(), page, slug)

    def test_head(self):
        page = self.html[IJSS2019]
        self.assertIn('<meta charset="utf-8">', page)
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', page)
        self.assertIn("<title>Tailoring tensile ductility of thin film by grain size graded substrates | Tianyu Chen</title>",
                      page)
        links = tags(page, "link")
        self.assertEqual([t.get("href") for t in links if t.get("rel") == "stylesheet"],
                         ["../../" + versioned("assets/css/article.css")])
        preloads = [t for t in links if t.get("rel") == "preload"]
        self.assertEqual({t.get("href") for t in preloads},
                         {"../../assets/fonts/source-serif-4/source-serif-4-latin-normal.woff2",
                          "../../assets/fonts/inter/inter-latin-wght-normal.woff2",
                          "../../assets/fonts/inter/inter-latin-wght-italic.woff2"})  # the journal name is italic
        for t in preloads:
            self.assertEqual((t.get("as"), t.get("type")), ("font", "font/woff2"))
            self.assertIn("crossorigin", t)
        self.assertEqual([t.get("src") for t in tags(page, "script")],
                         ["../../" + versioned("assets/js/article.js"),  # the page's own, then the counter
                          "../../" + versioned("assets/js/count.js")])

    def test_link_preview(self):
        for slug, page in self.html.items():
            with self.subTest(slug):
                meta = {t.get("property") or t.get("name"): t.get("content") for t in tags(page, "meta")}
                self.assertEqual(meta["og:title"], self.p[slug].title)
                self.assertEqual(meta["og:url"], f"https://tianyuchen.com/papers/{slug}/index.html")
                image = meta["og:image"]
                self.assertEqual(image, f"https://tianyuchen.com/media/{slug}/loop-poster.jpg")
                self.assertTrue((ROOT / image.removeprefix("https://tianyuchen.com/")).is_file())

    def test_interface_font_and_accent(self):
        # The redesign (2026-10-30): the paper pages' interface text matches the home page's Inter and blue accent;
        # their Source Serif 4 body text stays.
        css = (ROOT / "assets" / "css" / "article.css").read_text(encoding="utf-8")
        self.assertIn("--sans: 'Inter'", css)
        self.assertIn("--accent: #2563eb", css)
        self.assertNotIn("'Lato'", css)

    def test_top_bar(self):
        page = self.html[SAILS]
        bar = re.search(r'<header class="topbar">.*?</header>', page, re.S).group(0)
        self.assertIn('<a class="home" href="../../index.html">Tianyu Chen</a>', bar)
        self.assertIn('<span class="topbar-title">Scale-inspired programmable robotic structures</span>', bar)
        self.assertIn('href="https://doi.org/10.1126/scirobotics.adl0307"', bar)
        self.assertIn('data-copy="bibtex-text"', bar)

    def test_tab_icon(self):
        for slug, page in self.html.items():
            self.assertEqual([t.get("href") for t in tags(page, "link") if t.get("rel") == "icon"],
                             ["../../assets/img/favicon.svg"], slug)

    def test_open_access_pdf_button(self):
        # The hosted PDF opens from the top bar, beside the publisher's page; other papers have only the latter.
        for slug, page in self.html.items():
            bar = re.search(r'<header class="topbar">.*?</header>', page, re.S).group(0)
            pdf = self.p[slug].pdf
            buttons = re.findall(r'<a class="btn" href="([^"]+)"[^>]*>([^<]+)</a>', bar)
            self.assertEqual([text for _, text in buttons], ["Paper", "PDF"] if pdf else ["Paper"], slug)
            if pdf:
                self.assertEqual(buttons[1][0], f"../../{pdf}")
        self.assertTrue(self.p[SCIADV].pdf)

    def test_contents_follow_the_sections(self):
        for slug, page in self.html.items():
            with self.subTest(slug):
                toc = re.search(r'<aside class="toc".*?</aside>', page, re.S).group(0)
                listed = [t.get("href") for t in tags(toc, "a")]
                ids = re.findall(r'<section id="([^"]+)"', page)
                self.assertEqual(listed, [f"#{i}" for i in ids])
                self.assertEqual(listed[0], "#summary")
                self.assertEqual(listed[-1], "#bibtex")
        toc = re.search(r'<aside class="toc".*?</aside>', self.html[IJMS], re.S).group(0)
        self.assertIn('<a href="#how">1&nbsp; Working principle</a>', toc)
        self.assertIn('<a href="#summary">Summary</a>', toc)

    def test_author_html(self):
        self.assertEqual(author_html(["Ann Bo", "Tianyu Chen", "Cy Dee"], 2, ["Ann Bo", "Tianyu Chen"]),
                         "Ann Bo†, <strong>Tianyu Chen†</strong>, Cy Dee")

    def test_author_block_with_one_affiliation(self):
        head = paper_head(self.html[SCIADV])
        self.assertIn('<p class="authors">Jie&nbsp;Pan<sup>†</sup>, <span class="me">Tianyu&nbsp;Chen</span><sup>†</sup>, '
                      'Junwei&nbsp;Li, Yifan&nbsp;Wang<sup>*</sup></p>', head)
        self.assertIn('<p class="affil">School of Mechanical and Aerospace Engineering, Nanyang Technological University, '
                      'Singapore</p>', head)
        self.assertIn('<sup>†</sup>Equal contribution<br><sup>*</sup>Corresponding author: '
                      '<a href="mailto:yifan.wang@ntu.edu.sg">yifan.wang@ntu.edu.sg</a>', head)

    def test_author_block_with_numbered_affiliations(self):
        head = paper_head(self.html[IJSS2019])
        self.assertIn('<span class="me">Tianyu&nbsp;Chen</span><sup>1</sup>, Wenjun&nbsp;Lu<sup>2</sup>, '
                      'Jianjun&nbsp;Li<sup>3,4,*</sup>', head)
        self.assertIn("<sup>6</sup>Department of Mechanical and Aerospace Engineering, Rutgers University", head)
        self.assertNotIn("Equal contribution", head)
        self.assertEqual(re.findall(r"mailto:([^\"]+)", head), ["mejjli@csu.edu.cn"])

    def test_only_corresponding_emails(self):
        # Tianyu's rule: only the corresponding author's email appears (the 2021 paper's old address stays off).
        for slug, page in self.html.items():
            emails = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", page))
            self.assertEqual(emails, set(self.p[slug].corresponding.values()), slug)

    def test_venue(self):
        self.assertEqual(venue_html("International Journal of Solids and Structures 166, 124–134 (2019)"),
                         "<i>International Journal of Solids and Structures</i> 166, 124–134 (2019)")
        self.assertEqual(venue_html("Nanomaterials 11, 2468 (2021)"), "<i>Nanomaterials</i> 11, 2468 (2021)")

    def test_draft_badge(self):
        sails = self.p[SAILS]
        draft = paper_head(render_paper(replace(sails, summary_status="draft"), self.site, self.body[SAILS]))
        confirmed = paper_head(render_paper(replace(sails, summary_status="confirmed"), self.site, self.body[SAILS]))
        self.assertIn('class="draft"', draft)
        self.assertNotIn('class="draft"', confirmed)

    def test_published_movies_the_body_does_not_show_get_a_section(self):
        movies = section(self.html[SCIADV], "movies")
        videos = tags(movies, "video")
        self.assertEqual(len(videos), 4)
        base = "../../media/stiffness-driven-control/"
        for n, video in enumerate(videos, 1):
            self.assertIn("controls", video)
            self.assertEqual(video.get("preload"), "none")
            self.assertEqual(video.get("poster"), f"{base}poster-s{n}.jpg")
        self.assertEqual([s.get("src") for s in tags(movies, "source")], [f"{base}movie-s{n}.mp4" for n in range(1, 5)])
        self.assertEqual(movies.count("From Pan et al., Science Advances 12, eaeg3346 (2026)."), 4)
        self.assertIsNone(re.search(r"Movie S\d", movies))  # no paper numbering on the site

    def test_no_movies_section_when_the_body_shows_them_or_they_stay_unpublished(self):
        self.assertEqual(section(self.html[SAILS], "movies"), "")  # all twelve play in the text
        self.assertEqual(section(self.html[IJMS], "movies"), "")  # camera recordings: only their trimmed clips show
        self.assertEqual(section(self.html[IJSS2019], "movies"), "")

    def test_bibtex(self):
        entry = "@article{chen2024,\n  title = {A & B},\n  doi = {10.1126/scirobotics.adl0307}\n}"
        page = render_paper(replace(self.p[SAILS], bibtex=entry), self.site, self.body[SAILS])
        bibtex = section(page, "bibtex")
        self.assertIn('<pre id="bibtex-text">@article{chen2024,\n  title = {A &amp; B},', bibtex)
        self.assertIn('data-copy="bibtex-text"', bibtex)

    def test_footer_credit(self):
        footer = re.search(r"<footer>.*?</footer>", self.html[SAILS], re.S).group(0)
        self.assertIn('<a href="https://jonbarron.info/" target="_blank" rel="noopener">Jon Barron', footer)
        self.assertIn("Movies and figures are from the papers credited with each one.", footer)

    def test_visit_counter(self):
        # A paper page loads the site's own copy of count.js, its footer silent about it (Tianyu asked to delete that
        # line); with no count address, no script.
        for page in self.html.values():
            self.assertIn('<script data-goatcounter="https://cty9525785.goatcounter.com/count" async '
                          f'src="../../{versioned("assets/js/count.js")}"></script>', page)
            self.assertNotIn("GoatCounter", re.search(r"<footer>.*?</footer>", page, re.S).group(0))
        off = render_paper(self.p[SAILS], replace(self.site, goatcounter=""), self.body[SAILS])
        self.assertNotIn("goatcounter", off.lower())

    def test_external_links_open_in_new_tabs(self):
        # Tianyu: "for link outside my own site, open in new tab", in the pages' own text too.
        checked = 0
        for slug, page in self.html.items():
            for attrs in re.findall(r"<a ([^>]*)>", page):
                href = re.search(r'href="([^"]*)"', attrs)
                if href and href.group(1).startswith(("http://", "https://")):
                    self.assertIn('target="_blank"', attrs, (slug, href.group(1)))
                    self.assertIn('rel="noopener"', attrs, (slug, href.group(1)))
                    checked += 1
        self.assertGreaterEqual(checked, 12)  # the Paper buttons, the footer's credit and the links in the text

    def test_relative_paths_only(self):
        for slug, page in self.html.items():
            self.assertIsNone(re.search(r'(src|href|poster)="/[^/]', page), slug)

    def test_no_third_party_assets(self):
        for slug, page in self.html.items():
            assets = ([t.get("href") for t in tags(page, "link")] + [t.get("src") for t in tags(page, "script")]
                      + [t.get("src") for t in tags(page, "img")] + [t.get("src") for t in tags(page, "source")])
            for url in assets:
                self.assertFalse(url and url.startswith(("http:", "https:", "//")), f"{slug}: {url}")

    def test_no_tracking(self):
        for slug, page in self.html.items():
            for marker in TRACKERS:
                self.assertNotIn(marker, page, slug)

    def test_no_paper_numbering(self):
        # Tianyu's rule for the pages: no "Fig. 2", "Movie S1" or "table S1" anywhere a reader sees.
        numbering = re.compile(r"\b(Fig\.|Figure|Movie|Table|table)\s+S?\d")
        for slug, page in self.html.items():
            text = re.sub(r"<pre.*?</pre>", "", page, flags=re.S)  # the BibTeX entry is the journal's own
            seen = re.sub(r"<[^>]+>", " ", text) + " ".join(t.get("alt") or "" for t in tags(text, "img"))
            self.assertIsNone(numbering.search(seen), f"{slug}: {numbering.search(seen)}")


if __name__ == "__main__":
    unittest.main()
