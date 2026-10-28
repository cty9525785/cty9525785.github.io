import re
import tempfile
import unittest
from pathlib import Path

from tools.content import OtherPub, Site, credit_line, home_order, load_papers, load_site, placeholders

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "content" / "site.toml"
PAPERS = ROOT / "content" / "papers.toml"

MINIMAL = '''
[[paper]]
slug = "a"
title = "T"
authors = ["Tianyu Chen", "B. Author"]
me = 1
equal_contribution = []
citation = "J. 1, 1 (2024)"
date = "2024-01"
doi = "10.1/x"
highlight = false
media_mode = "embed"
supplementary_url = ""
short_title = "T"
affiliations = ["A University"]
affiliation_of = [[1], [1]]
corresponding = { "B. Author" = "b@example.invalid" }
summary_status = "draft"
one_line = "O"
bibtex = "@article{a}"

[[paper.movie]]
id = "S1"
source = "a.mp4"
process = "copy"
caption = "C"
'''


CLIP_TILE = '''[paper.tile]
kind = "clip"
graph = "a.graph"
inputs = [{ movie = "S1", start = 0.0, duration = 5.0 }]
segments = [{ at = 0.0, speed = 2.0 }]

[[paper.movie]]'''


OTHER = '''
[[other]]
slug = "b"
authors = ["B. Author", "T. Chen"]
me = 2
title = "X"
citation = "Y 1, 1 (2024)"
doi = "10.1/y"
one_line = "O."
summary_status = "draft"
'''


OTHER_TILE = OTHER + '''
[other.tile]
kind = "clip"
graph = "b.graph"
inputs = [{ movie = "S2", start = 1.0, duration = 6.0 }]
segments = [{ at = 0.0, speed = 2.0 }]

[[other.movie]]
id = "S2"
source = "Author 2024 J - Movie S2.mp4"
source_speed = 2.0
'''

def with_tile(tile: str) -> str:
    return MINIMAL.replace("[[paper.movie]]", tile)


def load_text(text):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "papers.toml"
        path.write_text(text, encoding="utf-8")
        return load_papers(path)


class ContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = load_site(SITE)
        cls.papers, cls.others = load_papers(PAPERS)
        cls.by_slug = {p.slug: p for p in cls.papers}

    def test_counts(self):
        self.assertEqual(len(self.papers), 6)
        self.assertEqual(len(self.others), 14)

    def test_pages_are_for_first_author_papers(self):
        # Tianyu's choice: a page for each paper Tianyu wrote as first or co-first author; the rest are listed.
        for p in self.papers:
            co_first = {p.authors[0], p.authors[p.me - 1]} <= set(p.equal_contribution)
            self.assertTrue(p.me == 1 or co_first, p.slug)
        self.assertEqual([o.title for o in self.others if o.me == 1], [])

    def test_co_authored_papers_are_listed(self):
        dois = {o.doi for o in self.others}
        for doi in ("10.1002/adma.202404502", "10.1016/j.matt.2023.11.002", "10.1016/j.eml.2024.102121"):
            self.assertIn(doi, dois)

    def test_slugs(self):
        slugs = [p.slug for p in self.papers]
        self.assertEqual(len(set(slugs)), 6)
        for slug in slugs:
            self.assertRegex(slug, r"^[a-z0-9-]+$")

    def test_other_slugs(self):
        slugs = [o.slug for o in self.others]
        self.assertEqual(len(set(slugs)), 14)
        for slug in slugs:
            self.assertRegex(slug, r"^[a-z0-9-]+$")
        self.assertEqual(set(slugs) & {p.slug for p in self.papers}, set())
        self.assertIn("active-fabrics", slugs)

    def test_other_rows_name_authors_in_full(self):
        # Tianyu: "for the name lists in the main page, use full name for all authors" (as each paper prints them).
        for o in self.others:
            with self.subTest(o.slug):
                self.assertEqual(o.authors[o.me - 1], "Tianyu Chen")
                for name in o.authors:
                    given = name.split()[:-1]
                    self.assertTrue(given and any(not re.fullmatch(r"(?:[A-Z]\.)+", g) for g in given), name)

    def test_other_rows_have_a_line(self):
        for o in self.others:
            self.assertTrue(o.one_line, o.slug)
            self.assertIn(o.summary_status, {"draft", "confirmed"}, o.slug)
            self.assertTrue(o.thumb == "" or o.thumb.startswith("TODO:"), o.slug)

    def test_home_order(self):
        self.assertEqual(
            [p.slug for p in home_order(self.papers)],
            [
                "scale-inspired-robotic-structures",
                "stiffness-driven-control",
                "programmable-morphing-structure",
                "shear-banding-gradient-metals",
                "amorphous-thin-films",
                "graded-substrate-thin-films",
            ],
        )

    def test_me(self):
        for p in self.papers:
            self.assertEqual(p.authors[p.me - 1], "Tianyu Chen", p.slug)
        for o in self.others:
            self.assertEqual(o.authors[o.me - 1], "Tianyu Chen", o.title)

    def test_every_paper_has_a_tile(self):
        kinds = {p.slug: (p.tile.kind, p.tile.drawing) for p in self.papers}
        self.assertEqual(kinds, {
            "scale-inspired-robotic-structures": ("clip", ""),
            "stiffness-driven-control": ("clip", ""),
            "programmable-morphing-structure": ("clip", ""),
            "shear-banding-gradient-metals": ("drawing", "gradient"),
            "amorphous-thin-films": ("drawing", "films"),
            "graded-substrate-thin-films": ("drawing", "necking"),
        })

    def test_clip_tiles(self):
        sails = self.by_slug["scale-inspired-robotic-structures"].tile
        self.assertEqual([i.movie for i in sails.inputs], ["S11", "S11", "S4", "S5", "S6"])
        self.assertEqual([(s.at, s.speed) for s in sails.segments], [(0.0, 4.0), (5.82, 2.0)])
        gripper = self.by_slug["stiffness-driven-control"].tile
        self.assertEqual([(s.at, s.speed) for s in gripper.segments], [(0.0, 50.0)])
        box = self.by_slug["programmable-morphing-structure"].tile
        self.assertEqual([i.movie for i in box.inputs], ["4", "4"])
        self.assertEqual([(s.at, s.speed) for s in box.segments], [(0.0, 1.0)])

    def test_source_speed(self):
        movies = {m.id: m for m in self.by_slug["stiffness-driven-control"].movies}
        self.assertEqual(movies["S2"].source_speed, 10.0)  # S2 is labeled 10x in the movie itself
        self.assertEqual(movies["S1"].source_speed, 1.0)

    def test_ijms_camera_movies(self):
        # Tianyu's own recordings, not published with the paper. The page shows their trimmed clips, so the full
        # recordings stay off the site; the home tile is cut from the original.
        movies = self.by_slug["programmable-morphing-structure"].movies
        self.assertEqual([(m.id, m.source) for m in movies],
                         [("1", "MVI_7784.MP4"), ("2", "MVI_7787.MP4"), ("3", "MVI_7615.MP4"), ("4", "MVI_7208.MP4")])
        for movie in movies:
            self.assertEqual((movie.process, movie.publish, movie.credit), ("silent1080", False, "Recorded for the paper."))

    def test_page_fields(self):
        # Each page's author block: short title for the top bar, affiliations, and the corresponding author's email.
        for paper in self.papers:
            with self.subTest(paper.slug):
                self.assertTrue(paper.short_title)
                self.assertEqual(len(paper.affiliation_of), len(paper.authors))
                used = {n for numbers in paper.affiliation_of for n in numbers}
                self.assertEqual(used, set(range(1, len(paper.affiliations) + 1)))
                self.assertTrue(paper.corresponding)
                self.assertTrue(set(paper.corresponding) <= set(paper.authors))
        self.assertEqual(self.by_slug["shear-banding-gradient-metals"].corresponding, {"Jianjun Li": "mejjli@csu.edu.cn"})

    def test_equal_contribution(self):
        # Tianyu: "please check co first authors in all the papers and add the signs". Every paper's text was
        # searched; these three print an equal-contribution note, and no other does.
        self.assertEqual(self.by_slug["stiffness-driven-control"].equal_contribution, ["Jie Pan", "Tianyu Chen"])
        self.assertEqual(self.by_slug["scale-inspired-robotic-structures"].equal_contribution, [])
        others = {o.slug: o.equal_contribution for o in self.others}
        self.assertEqual(others.pop("active-fabrics"), ["Xudong Yang", "Yu Chen"])
        self.assertEqual(others.pop("suture-interlocking-metamaterials"), ["Yu Chen", "Xudong Yang"])
        self.assertEqual({slug: names for slug, names in others.items() if names}, {})

    def test_credit_line(self):
        self.assertEqual(
            credit_line(self.by_slug["scale-inspired-robotic-structures"]),
            "From Chen et al., Science Robotics 9, eadl0307 (2024).",
        )
        self.assertEqual(
            credit_line(self.by_slug["shear-banding-gradient-metals"]),
            "From Chen and Li, Nanomaterials 11, 2468 (2021).",
        )
        self.assertEqual(
            credit_line(self.by_slug["stiffness-driven-control"]),
            "From Pan et al., Science Advances 12, eaeg3346 (2026).",
        )

    def test_placeholders(self):
        site = Site("Tianyu Chen", "Tagline.", "TODO: bio", "assets/img/x.svg",
                    {"email": "TODO: address", "cv": "files/cv.pdf"})
        self.assertEqual(placeholders(site, [], []), ["site.bio", "site.links.email"])
        other = OtherPub("x", ["T. Chen"], 1, "T", "C", "10.1/z", "TODO: line", "draft", "TODO: PDF")
        self.assertEqual(placeholders(site, [], [other]),
                         ["site.bio", "site.links.email", "other.x.one_line", "other.x.thumb"])


class SiteTest(unittest.TestCase):
    def test_bio_status(self):
        self.assertIn(load_site(SITE).bio_status, {"draft", "confirmed"})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "site.toml"
            path.write_text(SITE.read_text(encoding="utf-8").replace('bio_status = "draft"', 'bio_status = "maybe"')
                            .replace('bio_status = "confirmed"', 'bio_status = "maybe"'), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_site(path)


class ValidationTest(unittest.TestCase):
    def test_minimal_valid_loads(self):
        papers, others = load_text(MINIMAL)
        self.assertEqual([p.slug for p in papers], ["a"])
        self.assertEqual(papers[0].movies[0].process, "copy")
        self.assertEqual(others, [])

    def test_others_load(self):
        _, others = load_text(MINIMAL + OTHER)
        self.assertEqual([(o.slug, o.me, o.one_line, o.summary_status, o.thumb) for o in others],
                         [("b", 2, "O.", "draft", "")])

    def test_other_tiles_load(self):
        # Tianyu: "for thumbnail, better to use video". A co-authored row can loop a clip of the paper's movies.
        _, others = load_text(MINIMAL + OTHER_TILE)
        o = others[0]
        self.assertEqual((o.tile.kind, o.tile.graph, o.tile.inputs[0].movie, o.tile.segments[0].speed),
                         ("clip", "b.graph", "S2", 2.0))
        self.assertEqual((o.movies[0].id, o.movies[0].source, o.movies[0].source_speed),
                         ("S2", "Author 2024 J - Movie S2.mp4", 2.0))
        self.assertIsNone(load_text(MINIMAL + OTHER)[1][0].tile)
        with self.assertRaises(ValueError):  # the tile cuts only from the row's own movies
            load_text(MINIMAL + OTHER_TILE.replace('movie = "S2"', 'movie = "S9"'))

    def test_tiles_load(self):
        papers, _ = load_text(with_tile(CLIP_TILE))
        tile = papers[0].tile
        self.assertEqual((tile.kind, tile.graph, tile.inputs[0].movie, tile.segments[0].speed, tile.poster_at),
                         ("clip", "a.graph", "S1", 2.0, 0.0))
        drawn, _ = load_text(with_tile('[paper.tile]\nkind = "drawing"\ndrawing = "films"\nposter_at = 5.0\n\n[[paper.movie]]'))
        self.assertEqual((drawn[0].tile.kind, drawn[0].tile.drawing, drawn[0].tile.poster_at), ("drawing", "films", 5.0))
        self.assertIsNone(load_text(MINIMAL)[0][0].tile)

    def test_equal_contributors_are_authors(self):
        with self.assertRaises(ValueError):
            load_text(MINIMAL + OTHER.replace('me = 2', 'me = 2\nequal_contribution = ["C. Other"]'))
        with self.assertRaises(ValueError):
            load_text(MINIMAL.replace("equal_contribution = []", 'equal_contribution = ["C. Other"]'))

    def test_invalid_author_blocks_raise(self):
        cases = {
            "an author without affiliations": ('affiliation_of = [[1], [1]]', 'affiliation_of = [[1]]'),
            "a number past the list": ('affiliation_of = [[1], [1]]', 'affiliation_of = [[1], [2]]'),
            "an unused affiliation": ('affiliations = ["A University"]', 'affiliations = ["A University", "B Institute"]'),
            "a corresponding author not in the list": ('corresponding = { "B. Author" = "b@example.invalid" }',
                                                        'corresponding = { "C. Other" = "c@example.invalid" }'),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                load_text(MINIMAL.replace(old, new))

    def test_invalid_inputs_raise(self):
        cases = {
            "media_mode": MINIMAL.replace('media_mode = "embed"', 'media_mode = "stream"'),
            "process": MINIMAL.replace('process = "copy"', 'process = "transcode"'),
            "summary_status": MINIMAL.replace('summary_status = "draft"', 'summary_status = "final"'),
            "me too high": MINIMAL.replace("me = 1", "me = 3"),
            "me zero": MINIMAL.replace("me = 1", "me = 0"),
            "duplicate slug": MINIMAL + MINIMAL,
            "tile kind": with_tile(CLIP_TILE.replace('kind = "clip"', 'kind = "gif"')),
            "tile movie": with_tile(CLIP_TILE.replace('movie = "S1"', 'movie = "S9"')),
            "tile without graph": with_tile(CLIP_TILE.replace('graph = "a.graph"', 'graph = ""')),
            "first segment after 0": with_tile(CLIP_TILE.replace("at = 0.0", "at = 1.0")),
            "segments out of order": with_tile(CLIP_TILE.replace(
                "segments = [{ at = 0.0, speed = 2.0 }]",
                "segments = [{ at = 0.0, speed = 2.0 }, { at = 3.0, speed = 1.0 }, { at = 2.0, speed = 4.0 }]")),
            "zero speed": with_tile(CLIP_TILE.replace("speed = 2.0", "speed = 0.0")),
            "drawing without name": with_tile('[paper.tile]\nkind = "drawing"\n\n[[paper.movie]]'),
            "embed with none": MINIMAL.replace('process = "copy"', 'process = "none"'),
            "other me": MINIMAL + OTHER.replace("me = 2", "me = 3"),
            "other slug taken": MINIMAL + OTHER.replace('slug = "b"', 'slug = "a"'),
            "other summary_status": MINIMAL + OTHER.replace('summary_status = "draft"', 'summary_status = "final"'),
            "other missing field": MINIMAL + OTHER.replace('one_line = "O."\n', ""),
        }
        for name, text in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    load_text(text)

    def test_link_mode_allows_missing_movies(self):
        text = MINIMAL.replace('media_mode = "embed"', 'media_mode = "link"').replace(
            'process = "copy"', 'process = "none"'
        )
        papers, _ = load_text(text)
        self.assertEqual(papers[0].media_mode, "link")


if __name__ == "__main__":
    unittest.main()
