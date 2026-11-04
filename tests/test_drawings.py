import unittest
from pathlib import Path

import numpy as np

from tools.content import load_papers
from tools.drawings import DRAWINGS, SIZE, necking_boundaries, necking_layers, necking_profile

ROOT = Path(__file__).resolve().parents[1]


class DrawingsTest(unittest.TestCase):
    def test_tiles_name_the_drawings(self):
        papers, _ = load_papers(ROOT / "content" / "papers.toml")
        names = {p.tile.drawing for p in papers if p.tile is not None and p.tile.kind == "drawing"}
        self.assertEqual(names, set(DRAWINGS))

    def test_frames(self):
        for name, drawing in DRAWINGS.items():
            for t in (0.0, drawing.hold_end / 2, drawing.hold_end):
                with self.subTest(f"{name} at {t}"):
                    im = drawing.frame(t)
                    self.assertEqual((im.size, im.mode), ((SIZE, SIZE), "RGB"))

    def test_necking_interface_has_no_ripples(self):
        # Tianyu: "why there's wave interface?" The papers' films neck in one place; nothing waves along the length.
        for graded in (False, True):
            for eps in (0.1, 0.25, 0.33):
                with self.subTest(graded=graded, eps=eps):
                    _, _, interface = necking_profile(eps, graded)
                    d = np.diff(interface)
                    turns = np.count_nonzero(np.sign(d[:-1]) * np.sign(d[1:]) < 0)
                    self.assertLessEqual(turns, 1)  # flat, or one dip under the neck

    def test_necking_gradient_is_visible(self):
        # Tianyu: "the gradient is not clearly shown", then preferred the layered drawing to grains. The gradient
        # layer steps from dark at the surface (finest grains) to light, in yellows as in the paper's model drawing.
        def luminance(c):
            return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

        colors = [c for _, c in necking_layers(True)]
        gsl, core = colors[:-1], colors[-1]
        self.assertGreaterEqual(len(gsl), 4)
        steps = [luminance(b) - luminance(a) for a, b in zip(gsl, gsl[1:])]
        self.assertTrue(all(step >= 10 for step in steps), steps)
        self.assertGreaterEqual(luminance(gsl[-1]) - luminance(gsl[0]), 60)
        self.assertTrue(all(c[0] - c[2] > 60 for c in gsl))  # yellow
        self.assertLess(abs(core[0] - core[2]), 20)  # gray
        self.assertEqual([c for _, c in necking_layers(False)], [core])  # the same coarse grains on top

    def test_necking_layers_bend_only_near_the_neck(self):
        # The paper's snapshots: the substrate's surface rises into the neck and the layers below follow it
        # locally, less with depth; nothing moves far from the neck.
        for graded in (False, True):
            with self.subTest(graded=graded):
                xr, curves = necking_boundaries(0.33, graded)
                far = np.abs(xr) > 130
                bends = []
                for y in curves[1:]:  # the interface, then each layer's bottom
                    self.assertLess(np.ptp(y[far]), 0.01)
                    d = np.diff(y)
                    self.assertLessEqual(np.count_nonzero(np.sign(d[:-1]) * np.sign(d[1:]) < 0), 1)
                    bends.append(y[far].mean() - y.min())
                self.assertGreater(bends[0], 0.5)  # the surface visibly rises into the neck
                self.assertTrue(all(deeper <= upper + 1e-9 for upper, deeper in zip(bends, bends[1:])), bends)
                self.assertLess(bends[-1], 1e-6)  # the bottom stays flat

    def test_loops_fit_the_tile_limits(self):
        for name, drawing in DRAWINGS.items():
            with self.subTest(name):
                self.assertLess(drawing.hold_end, drawing.length)
                self.assertTrue(4.0 <= drawing.length <= 12.0)


if __name__ == "__main__":
    unittest.main()
