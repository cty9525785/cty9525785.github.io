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
    return [ROOT / "index.html", *sorted((ROOT / "papers").glob("*/index.html"))]


class SiteTest(unittest.TestCase):
    def test_all_local_links_open_from_disk(self):
        # A page opened from disk gets no index.html for a folder link (only a web
        # server adds it), so every local link must name an existing file.
        for page in pages():
            html = page.read_text(encoding="utf-8")
            refs = [t.get(attr) for name, attr in (("a", "href"), ("link", "href"), ("img", "src"),
                                                    ("source", "src"), ("video", "poster"), ("script", "src"))
                    for t in tags(html, name)]
            for ref in refs:
                if not ref or ref.startswith(("http:", "https:", "mailto:", "#", "data:")):
                    continue
                target = (page.parent / ref).resolve()
                self.assertTrue(target.is_file(), f"{page.relative_to(ROOT)}: {ref}")

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
