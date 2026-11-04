"""Cut each paper's Figure 1 out of its PDF, plus a small thumbnail for a home page row without a tile.

Usage: python -X utf8 tools/figures.py --pdf-dir folder

The figure is the union of the page's images that each cover at least 5% of the page, rendered
together with any vector labels on top and scaled to max_width pixels wide. Papers without a home
page tile also get thumb.jpg.
"""
import argparse
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # lets `python tools/figures.py` import the tools package
    sys.path.insert(0, str(ROOT))

from tools.content import load_papers  # noqa: E402

MIN_SHARE = 0.05
CAPTION = re.compile(r"\s*(Fig\.|Figure|FIGURE)\s*1(?!\d)")


def _caption_top(page: fitz.Page) -> float | None:
    """Top of the text block that starts the Figure 1 caption, if it is on this page."""
    for _, y0, _, _, text, *_ in page.get_text("blocks"):
        if CAPTION.match(text):
            return y0
    return None


def _figure_rect(page: fitz.Page) -> fitz.Rect:
    area = page.rect.width * page.rect.height
    big = [rect for image in page.get_images(full=True) for rect in page.get_image_rects(image[0])
           if rect.width * rect.height >= MIN_SHARE * area]
    if not big:
        raise ValueError(f"page {page.number + 1} has no image covering {MIN_SHARE:.0%} of the page")
    # When Figure 2 shares the page, keep only the images above the Figure 1 caption.
    top = _caption_top(page)
    chosen = [r for r in big if top is not None and r.y1 <= top + 1] or big
    union = fitz.Rect(chosen[0])
    for rect in chosen[1:]:
        union = union | rect
    return union & page.rect


def _scaled(pix: fitz.Pixmap, width: int) -> fitz.Pixmap:
    if pix.width == width:
        return pix
    return fitz.Pixmap(pix, width, round(pix.height * width / pix.width), None)


def _save_jpeg(pix: fitz.Pixmap, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out), jpg_quality=85)


def extract_figure(pdf: Path, page: int, out: Path, max_width: int = 1600) -> tuple[int, int]:
    """Render the figure on the given 1-based page to a JPEG max_width pixels wide."""
    with fitz.open(str(pdf)) as doc:
        source = doc[page - 1]
        rect = _figure_rect(source)
        zoom = max_width / rect.width
        pix = _scaled(source.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False), max_width)
    _save_jpeg(pix, out)
    return pix.width, pix.height


def make_thumb(figure: Path, out: Path, width: int = 480) -> None:
    _save_jpeg(_scaled(fitz.Pixmap(str(figure)), width), out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Cut Figure 1 of each paper out of its PDF.")
    parser.add_argument("--pdf-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    papers, _ = load_papers(ROOT / "content" / "papers.toml")
    for paper in papers:
        if paper.figure is None:
            print(f"skip         {paper.slug} (no figure set)")
            continue
        folder = ROOT / "media" / paper.slug
        width, height = extract_figure(args.pdf_dir / paper.figure.pdf, paper.figure.page, folder / "figure.jpg")
        if paper.tile is None:
            make_thumb(folder / "figure.jpg", folder / "thumb.jpg")
        print(f"figure       media/{paper.slug}/figure.jpg ({width}x{height})")


if __name__ == "__main__":
    main()
