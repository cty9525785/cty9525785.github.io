import re
import unittest
from pathlib import Path

from tools.build import read_body
from tools.content import PLACEHOLDER, load_papers, load_site

ROOT = Path(__file__).resolve().parents[1]

# British spellings and wording to avoid, as word patterns (so "programmed"
# does not trip "programme"). Paper titles are exempt.
BANNED = (r"\bmodelling\b", r"\bbehaviour", r"\bcolour", r"\banalyse", r"\butilise", r"\boptimise", r"\bcentre\b",
          r"\bfibre", r"\bfavour", r"\bprogramme\b", r"\bcampaign", r"\bbottoming", r"\bfe-to-experiment",
          r"\bpython-scripted", r"\bcorrelat")


def page_text(slug: str, title: str) -> str:
    """What a reader sees of a page's own text: tags dropped, whitespace collapsed, the paper's title exempt."""
    html = read_body(ROOT, slug)
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    alts = " ".join(re.findall(r'alt="([^"]*)"', html))
    return f"{text} {alts}".replace(title, "")


class CopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.papers, cls.others = load_papers(ROOT / "content" / "papers.toml")

    def copy_fields(self):
        for p in self.papers:
            yield f"{p.slug}.page", page_text(p.slug, p.title)
            yield f"{p.slug}.one_line", p.one_line
            for m in p.movies:
                yield f"{p.slug}.{m.id}", m.caption
        site = load_site(ROOT / "content" / "site.toml")
        yield "site.role", site.role
        for t in site.topics:
            yield f"site.topic.{t.id}", f"{t.label}. {t.heading}"
        for r in site.experience:
            yield f"site.experience.{r.years}", f"{r.role}. {r.org}. {r.text}"
        for d in site.education:
            yield f"site.education.{d.year}", f"{d.degree}. {d.school}"
        for g in site.skills:
            yield f"site.skills.{g.name}", f"{g.name}: {', '.join(g.items)}"
        for o in self.others:
            yield f"{o.slug}.one_line", o.one_line

    def test_no_placeholders_in_papers(self):
        for p in self.papers:
            for name in ("short_title", "one_line", "bibtex"):
                self.assertFalse(getattr(p, name).startswith(PLACEHOLDER), f"{p.slug}.{name}")
            for m in p.movies:
                self.assertFalse(m.caption.startswith(PLACEHOLDER), f"{p.slug}.{m.id}")
        for o in self.others:
            self.assertFalse(o.doi.startswith(PLACEHOLDER), o.title)

    def test_style(self):
        for name, text in self.copy_fields():
            for pattern in BANNED:
                self.assertIsNone(re.search(pattern, text.lower()), f"{name}: {pattern}")
            self.assertNotIn("  ", text, name)

    def test_style_patterns_catch_british_spelling(self):
        caught = [p for p in BANNED if re.search(p, "modelling the behaviour of a fibre programme")]
        self.assertEqual(len(caught), 4)
        self.assertFalse(any(re.search(p, "the programmed shape of the fibers") for p in BANNED))

    def test_lengths(self):
        for p in self.papers + self.others:
            self.assertLessEqual(len(p.one_line.split()), 30, p.slug)
        for p in self.papers:
            self.assertIn('<section id="summary"', read_body(ROOT, p.slug), p.slug)  # each page opens with a summary

    def test_bibtex(self):
        for p in self.papers:
            year = re.search(r"\((\d{4})\)$", p.citation).group(1)
            self.assertIn(f"doi = {{{p.doi}}}", p.bibtex, p.slug)
            self.assertIn(f"year = {{{year}}}", p.bibtex, p.slug)
            self.assertTrue(p.bibtex.startswith("@article{"), p.slug)

    def test_full_journal_names(self):
        for p in self.papers:
            journal = re.search(r"journal = \{([^}]*)\}", p.bibtex).group(1)
            self.assertTrue(p.citation.startswith(journal + " "), f"{p.slug}: {p.citation}")
        for citation in [p.citation for p in self.papers] + [o.citation for o in self.others]:
            self.assertIsNone(re.search(r"[A-Za-z]\.", citation), f"abbreviated: {citation}")

    def test_other_dois(self):
        for o in self.others:
            self.assertRegex(o.doi, r"^10\.\d{4,9}/\S+$", o.title)


if __name__ == "__main__":
    unittest.main()
