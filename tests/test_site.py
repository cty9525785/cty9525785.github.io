import re
import subprocess
import unittest
from pathlib import Path

from tests.htmlutil import tags
from tools.check_publish import LICENSE_NAMES, public_allowances
from tools.content import load_papers, load_site

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".html", ".css", ".js", ".py", ".toml", ".md", ".svg", ".txt", ""}
# Built without writing the words out, so this file does not trip its own scan.
SYNCED_FOLDER = "One" + "Drive"
DRIVE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
FONT_SUFFIXES = {".woff2", ".woff", ".ttf", ".otf"}
GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"}
OS_FONTS = {"-apple-system", "sf mono"}  # Apple's system fonts, which the paper pages' stacks start with
FONT_FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
FONT_STACK = re.compile(r"(?:font-family|--font)\s*:\s*([^;}]+)")


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def pages() -> list[Path]:
    return [ROOT / "index.html", ROOT / "publications.html", ROOT / "experience.html",
            *sorted((ROOT / "papers").glob("*/index.html"))]


class SiteTest(unittest.TestCase):
    def test_all_local_links_open_from_disk(self):
        # A page opened from disk gets no index.html for a folder link (only a web
        # server adds it), so every local link must name an existing file; a link
        # into another page's section must find that section there.
        for page in pages():
            html = page.read_text(encoding="utf-8")
            refs = [t.get(attr) for name, attr in (("a", "href"), ("link", "href"), ("img", "src"),
                                                    ("source", "src"), ("video", "poster"), ("script", "src"))
                    for t in tags(html, name)]
            for ref in refs:
                if not ref or ref.startswith(("http:", "https:", "mailto:", "#", "data:")):
                    continue
                path, _, anchor = ref.partition("#")
                path = path.split("?")[0]  # a stylesheet's or script's version tag
                target = (page.parent / path).resolve()
                self.assertTrue(target.is_file(), f"{page.relative_to(ROOT)}: {ref}")
                if anchor:
                    self.assertIn(f'id="{anchor}"', target.read_text(encoding="utf-8"), f"{page.relative_to(ROOT)}: {ref}")

    def test_every_media_file_is_used(self):
        # Whatever git tracks under media/ gets published, so a file no page uses is dead weight.
        used = set()
        for page in pages():
            html = page.read_text(encoding="utf-8")
            for name, attr in (("img", "src"), ("source", "src"), ("video", "poster")):
                used |= {(page.parent / t.get(attr)).resolve() for t in tags(html, name) if t.get(attr)}
        unused = [p.relative_to(ROOT).as_posix() for p in tracked_files()
                  if p.relative_to(ROOT).parts[0] == "media" and p.resolve() not in used]
        self.assertEqual(unused, [])

    def test_no_leftover_paper_folders(self):
        # A paper dropped from content/papers.toml must not leave its page or movies behind to be published.
        papers, others = load_papers(ROOT / "content" / "papers.toml")
        pages = {p.slug for p in papers}
        for folder, slugs in (("papers", pages), ("media", pages | {o.slug for o in others})):
            leftovers = {p.name for p in (ROOT / folder).iterdir() if p.is_dir()} - slugs
            self.assertEqual(leftovers, set(), folder)

    def test_preferred_fonts_ship_with_the_site(self):
        # The font a stack asks for first must come with the site or the operating system,
        # or every visitor sees the fallback (Lato fell back to Verdana).
        for css in sorted((ROOT / "assets" / "css").glob("*.css")):
            text = css.read_text(encoding="utf-8")
            shipped = set()
            for face in FONT_FACE.findall(text):
                shipped.add(re.search(r"font-family\s*:\s*['\"]?([^'\";]+)", face).group(1).lower())
                for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", face):
                    self.assertTrue((css.parent / url).resolve().is_file(), f"{css.name}: {url}")
            for stack in FONT_STACK.findall(FONT_FACE.sub("", text)):
                first = stack.replace("!important", "").split(",")[0].strip().strip("'\"").lower()
                if not first.startswith("var("):
                    self.assertIn(first, GENERIC_FAMILIES | OS_FONTS | shipped, f"{css.name}: {stack.strip()}")

    def test_custom_domain(self):
        # GitHub Pages serves the site at the domain named in CNAME; Tianyu registered tianyuchen.com (2026-10-29).
        self.assertEqual((ROOT / "CNAME").read_text(encoding="utf-8"), "tianyuchen.com\n")

    def test_fonts_do_not_swap_in_late(self):
        # "swap" draws the page in a fallback font and switches when the font arrives, which Tianyu saw;
        # "fallback" still switches when the font is over ~0.1 s late, and Tianyu saw it again (2026-10-31).
        # "optional" kept whole pages in the fallback (Segoe UI) when the font missed its 0.1 s, even from disk in a
        # freshly started browser, and Tianyu saw fonts "still not the same". "block" holds the text back until the
        # preloaded font arrives (up to 3 s), so pages draw in their own fonts and never switch while read.
        for css in sorted((ROOT / "assets" / "css").glob("*.css")):
            for face in FONT_FACE.findall(css.read_text(encoding="utf-8")):
                self.assertIn("font-display: block", face, css.name)

    def test_pages_wait_for_their_fonts(self):
        # Tianyu (2026-11-01): "why still some text change font after. can we make all the font load before
        # appearing?" "block" holds text back only 3 s; after that a browser draws it in a stand-in and swaps when the
        # font comes, and the serif italic of the paper pages' symbols was not fetched until the text needed it. Each
        # page now fetches the fonts it uses first and stays hidden until they are in, a script after its stylesheet
        # (whose fonts it asks for) adding .fonts-wait; after 5 s it shows whatever happens, by the script's timer
        # and by the stylesheet's own animation, should the script never run.
        faces = {"inter/inter-latin-wght-normal.woff2": "16px Inter",
                 "inter/inter-latin-wght-italic.woff2": "italic 16px Inter",
                 "source-serif-4/source-serif-4-latin-normal.woff2": "16px 'Source Serif 4'",
                 "source-serif-4/source-serif-4-latin-italic.woff2": "italic 16px 'Source Serif 4'"}
        pages = [ROOT / "index.html", ROOT / "publications.html", ROOT / "experience.html",
                 *sorted((ROOT / "papers").glob("*/index.html"))]
        for path in pages:
            page = path.read_text(encoding="utf-8")
            head = page[:page.index("</head>")]
            name = path.relative_to(ROOT).as_posix()
            wait = re.search(r"<script>\(function \(d\) \{(.*?)\}\)\(document\);</script>", head, re.S)
            self.assertTrue(wait, name)
            self.assertLess(head.index('rel="stylesheet"'), wait.start(), name)
            asked = re.findall(r'"([^"]+)"', re.search(r"Promise\.all\(\[(.*?)\]", wait.group(1)).group(1))
            preloaded = [re.search(r"assets/fonts/(.+)$", href).group(1) for href in re.findall(
                r'<link rel="preload" href="([^"]+)" as="font"', head)]
            self.assertEqual(sorted(asked), sorted(faces[f] for f in preloaded), name)
            self.assertIn('h.classList.add("fonts-wait")', wait.group(1))
            self.assertIn("setTimeout(show, 5000)", wait.group(1))
            self.assertIn(".then(show, show)", wait.group(1))  # a font that fails to come shows the page too
            # Text in the serif's italic (symbols in the paragraphs, not captions, which are Inter) is fetched first.
            if name.startswith("papers/"):
                main = re.sub(r"<figcaption.*?</figcaption>", "", page[page.index("<main"):page.index("</main>")],
                              flags=re.S)
                self.assertEqual("italic 16px 'Source Serif 4'" in asked, "<em>" in main, name)
        for css in ("home.css", "article.css"):
            text = (ROOT / "assets" / "css" / css).read_text(encoding="utf-8")
            hold = re.search(r"\.fonts-wait body \{([^}]*)\}", text).group(1)
            self.assertIn("opacity: 0", hold, css)
            self.assertIn("animation: fonts-in 0s 5s forwards", hold, css)
            self.assertRegex(text, r"@keyframes fonts-in \{\s*to \{\s*opacity: 1;?\s*\}\s*\}", css)

    def test_pages_name_their_own_address(self):
        # Tianyu (2026-11-01): "how can i count click of my website from different source, like google scholar and
        # linkedin". A tagged link (?campaign=linkedin) tells GoatCounter the source, but its count.js records the
        # address it finds, tag included, unless the page names its own with a canonical link: then the tagged visit,
        # and /index.html too, count toward the one page.
        pages = [ROOT / "index.html", ROOT / "publications.html", ROOT / "experience.html",
                 *sorted((ROOT / "papers").glob("*/index.html"))]
        for path in pages:
            page = path.read_text(encoding="utf-8")
            name = path.relative_to(ROOT).as_posix()
            canonical = [t.get("href") for t in tags(page, "link") if t.get("rel") == "canonical"]
            self.assertEqual(len(canonical), 1, name)
            self.assertEqual(canonical[0], re.search(r'property="og:url" content="([^"]+)"', page).group(1), name)
        self.assertEqual([t.get("href") for t in tags((ROOT / "index.html").read_text(encoding="utf-8"), "link")
                          if t.get("rel") == "canonical"], ["https://tianyuchen.com/"])

    def test_shipped_fonts_carry_their_license(self):
        # The SIL Open Font License asks that its text travel with every copy of the font.
        for font in (ROOT / "assets").rglob("*"):
            if font.suffix.lower() in FONT_SUFFIXES:
                self.assertTrue((font.parent / "OFL.txt").is_file(), font.relative_to(ROOT).as_posix())

    def test_no_private_traces(self):
        papers, _ = load_papers(ROOT / "content" / "papers.toml")
        public_emails, _ = public_allowances(load_site(ROOT / "content" / "site.toml"), papers)
        for path in tracked_files():
            if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            name = path.relative_to(ROOT).as_posix()
            self.assertNotIn(SYNCED_FOLDER, text, name)
            self.assertIsNone(DRIVE_PATH.search(text), name)
            for email in [] if path.name in LICENSE_NAMES else EMAIL.findall(text):
                self.assertTrue(email.endswith("@example.invalid") or email in public_emails, f"{name}: {email}")


if __name__ == "__main__":
    unittest.main()
