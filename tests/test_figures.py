import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

from tools.content import load_papers
from tools.figures import extract_figure, make_thumb

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media"


def size_of(path: Path) -> tuple[int, int]:
    pix = fitz.Pixmap(str(path))
    return pix.width, pix.height


def synthetic_pdf(path: Path) -> None:
    """A 600x800 pt page with a 300x200 pt figure image, a tiny logo image and some text."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    figure = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), 0)
    figure.set_rect(figure.irect, (200, 30, 30))
    page.insert_image(fitz.Rect(100, 100, 400, 300), pixmap=figure)
    logo = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 0)
    logo.set_rect(logo.irect, (30, 30, 200))
    page.insert_image(fitz.Rect(10, 10, 30, 30), pixmap=logo)
    page.insert_text((100, 330), "Fig. 1. A synthetic figure.")
    doc.save(str(path))


def two_figure_pdf(path: Path) -> None:
    """Figure 1 and Figure 2 stacked on one page, each followed by its caption."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    for top, label in ((100, "Fig. 1. First figure."), (400, "Fig. 2. Second figure.")):
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), 0)
        pix.set_rect(pix.irect, (30, 160, 30))
        page.insert_image(fitz.Rect(100, top, 400, top + 200), pixmap=pix)
        page.insert_text((100, top + 230), label)
    doc.save(str(path))


class ExtractTest(unittest.TestCase):
    def test_extract_stops_at_the_figure_1_caption(self):
        with tempfile.TemporaryDirectory() as d:
            pdf, out = Path(d) / "x.pdf", Path(d) / "figure.jpg"
            two_figure_pdf(pdf)
            self.assertEqual(extract_figure(pdf, 1, out, max_width=900), (900, 600))

    def test_extract_uses_big_images_only(self):
        with tempfile.TemporaryDirectory() as d:
            pdf, out = Path(d) / "x.pdf", Path(d) / "figure.jpg"
            synthetic_pdf(pdf)
            self.assertEqual(extract_figure(pdf, 1, out, max_width=900), (900, 600))
            self.assertEqual(size_of(out), (900, 600))

    def test_make_thumb(self):
        with tempfile.TemporaryDirectory() as d:
            pdf, figure, thumb = Path(d) / "x.pdf", Path(d) / "figure.jpg", Path(d) / "thumb.jpg"
            synthetic_pdf(pdf)
            extract_figure(pdf, 1, figure, max_width=900)
            make_thumb(figure, thumb, width=480)
            self.assertEqual(size_of(thumb), (480, 320))


class FigureOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.papers, _ = load_papers(ROOT / "content" / "papers.toml")

    def test_thumbs(self):
        for paper in self.papers:
            if paper.tile is None:
                with self.subTest(paper.slug):
                    self.assertEqual(size_of(MEDIA / paper.slug / "thumb.jpg")[0], 480)

    def test_other_thumbs(self):
        # A co-authored row without a clip shows media/<slug>/thumb.jpg unless a TODO: says what is missing.
        _, others = load_papers(ROOT / "content" / "papers.toml")
        for o in others:
            if o.tile is None and o.thumb == "":
                with self.subTest(o.slug):
                    self.assertLessEqual(size_of(MEDIA / o.slug / "thumb.jpg")[0], 480)


if __name__ == "__main__":
    unittest.main()
