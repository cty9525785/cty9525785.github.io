"""Draw the home page tiles that illustrate a modeling paper, as 480x480 MP4 loops.

tools/media.py calls render() for every tile whose kind is "drawing". Each drawing follows its paper's
figures; what it simplifies or enlarges is listed here, because the tile itself carries no label.

films: a freestanding metallic glass film forms one shear band and breaks; the same film on a metal
substrate forms six bands, in the order and at the positions of Chen et al., IJSS 2020, Fig. 5, and
stretches about twice as far. Strains are drawn 3.2 times larger than in the paper, the same for both.
gradient: a gradient nano-grained Cu specimen (Chen and Li, Nanomaterials 2021, Fig. 1) pulled to 20%;
shear bands appear at the surface in the order and at the positions of Fig. 6. The grain size range is
compressed (3.5 to 48 px instead of tens of nm to tens of um), and the band width and length are schematic.
necking: the same notched film on a coarse-grained substrate (top) and on a gradient substrate (bottom),
pulled together to 33% (Chen et al., IJSS 2019). The gradient layer takes the model drawing's colors (Fig. 1):
five layers from dark at the surface, where the grains are finest, to light, about half the substrate's
depth, over the gray coarse-grained phase. The paper's strong-interface case (Fig. 13a, interface strength
at least 2.5 times the film's yield strength): the top film necks sharply at the notch from 20%, the bottom
one only by 32%, 1.6 times later, in a broad, shallow neck. As in Fig. 7, the film thins from both faces, the
substrate's surface rises into the neck and the layers below follow it locally, less with depth; nothing
waves along the film. At the default interface the gain is smaller (0.22 against 0.19). The film is drawn a
fifth as thick as the substrate (about 1/80 in the paper), the notch is enlarged, and the deepening after
onset is schematic.
"""
import functools
import math
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SIZE, SS, FPS = 480, 4, 30
BG = (244, 245, 247)
BLUE = np.array([61, 111, 196], float)
GRAY = (163, 169, 177)
ORANGE = (240, 138, 36)
INK = (74, 82, 96)


def smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def encode(frames, out: Path, ffmpeg: str) -> None:
    proc = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{SIZE}x{SIZE}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
                             "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                             str(out)], stdin=subprocess.PIPE)
    for im in frames:
        proc.stdin.write(im.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")


# ---------- films ----------

L0 = 300.0
FILM_H, SUB_H = 36.0, 100.0
TOP_Y, BOT_Y = 112.0, 230.0
STRAIN_SCALE = 3.2
# (position along the strip, lean, strain in the paper at which the band shows), IJSS 2020 Fig. 5
BANDS = [(0.31, -1, 0.058), (0.59, -1, 0.0604), (0.95, +1, 0.0604),
         (0.14, -1, 0.0643), (0.72, -1, 0.0643), (0.87, -1, 0.0643)]
FREE_BAND, FREE_BAND_AT, FREE_BREAK_AT = 0.72, 0.0352, 0.0379
END_STRAIN = 0.078


def strain_at(t: float) -> float:
    """Strain as in the paper (0 to END_STRAIN) while the ends are pulled from 0.8 s to 4.4 s."""
    return END_STRAIN * smooth((t - 0.8) / 3.6)


def band_poly(xc: float, y0: float, h: float, lean: int, w: float) -> list[tuple[float, float]]:
    """A band at 45 degrees through a film of thickness h, centered at xc; lean -1 is '\\', +1 is '/'."""
    dx = h / 2 * (-lean)
    return [(xc - dx - w / 2, y0), (xc - dx + w / 2, y0), (xc + dx + w / 2, y0 + h), (xc + dx - w / 2, y0 + h)]


def arrow(draw, x: float, y: float, direction: int, alpha: float) -> None:
    if alpha <= 0:
        return
    col = tuple(int(BG[i] + (INK[i] - BG[i]) * alpha) for i in range(3))
    shaft = 22 * SS
    tip = x + direction * (shaft + 12 * SS)
    draw.line([(x, y), (x + direction * shaft, y)], fill=col, width=int(4 * SS))
    draw.polygon([(tip, y), (x + direction * shaft, y - 8 * SS), (x + direction * shaft, y + 8 * SS)], fill=col)


def films_frame(t: float) -> Image.Image:
    s = SS
    eps = strain_at(t)
    broken = eps >= FREE_BREAK_AT
    im = Image.new("RGB", (SIZE * s, SIZE * s), BG)
    draw = ImageDraw.Draw(im)
    blue = tuple(int(v) for v in BLUE)

    # freestanding film
    e_top = STRAIN_SCALE * min(eps, FREE_BREAK_AT)
    half = L0 / 2 * (1 + e_top)
    x0, x1 = SIZE / 2 - half, SIZE / 2 + half
    xb = x0 + FREE_BAND * (x1 - x0)
    y0, y1 = TOP_Y, TOP_Y + FILM_H
    if not broken:
        draw.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], fill=blue)
        show = smooth((eps - FREE_BAND_AT) / (FREE_BREAK_AT - FREE_BAND_AT))
        if show > 0:
            col = tuple(int(blue[i] + (ORANGE[i] - blue[i]) * show) for i in range(3))
            draw.polygon([(px * s, py * s) for px, py in band_poly(xb, y0, FILM_H, -1, 8)], fill=col)
        arrow(draw, (x0 - 8) * s, (y0 + FILM_H / 2) * s, -1, 1.0)
        arrow(draw, (x1 + 8) * s, (y0 + FILM_H / 2) * s, +1, 1.0)
    else:
        open_ = smooth((eps - FREE_BREAK_AT) / 0.004)
        dx, dy = 9 * open_, 7 * open_  # the right piece slides along the band and lets go
        top_x, bot_x = xb - FILM_H / 2, xb + FILM_H / 2
        left = [(x0, y0), (top_x, y0), (bot_x, y1), (x0, y1)]
        right = [(top_x + dx, y0 + dy), (x1 + dx, y0 + dy), (x1 + dx, y1 + dy), (bot_x + dx, y1 + dy)]
        draw.polygon([(px * s, py * s) for px, py in left], fill=blue)
        draw.polygon([(px * s, py * s) for px, py in right], fill=blue)
        draw.line([(top_x * s, y0 * s), (bot_x * s, y1 * s)], fill=ORANGE, width=int(4 * s))
        draw.line([((top_x + dx) * s, (y0 + dy) * s), ((bot_x + dx) * s, (y1 + dy) * s)], fill=ORANGE, width=int(4 * s))
        fade = 1 - smooth((eps - FREE_BREAK_AT) / 0.003)
        arrow(draw, (x0 - 8) * s, (y0 + FILM_H / 2) * s, -1, fade)
        arrow(draw, (x1 + 8 + dx) * s, (y0 + dy + FILM_H / 2) * s, +1, fade)

    # film on substrate
    e_bot = STRAIN_SCALE * eps
    half = L0 / 2 * (1 + e_bot)
    x0, x1 = SIZE / 2 - half, SIZE / 2 + half
    fy0, fy1, sy1 = BOT_Y, BOT_Y + FILM_H, BOT_Y + FILM_H + SUB_H
    wave = 5 * smooth((eps - 0.04) / 0.04)
    bottom = [(x, sy1 + wave * math.sin(2 * math.pi * (x - x0) / (x1 - x0) * 1.5 + 0.6))
              for x in np.linspace(x1, x0, 60)]
    draw.polygon([(x0 * s, fy1 * s), (x1 * s, fy1 * s)] + [(px * s, py * s) for px, py in bottom], fill=GRAY)
    draw.rectangle([x0 * s, fy0 * s, x1 * s, fy1 * s], fill=blue)
    for pos, lean, at in BANDS:
        show = smooth((eps - (at - 0.0012)) / 0.0012)
        if show > 0:
            col = tuple(int(blue[i] + (ORANGE[i] - blue[i]) * show) for i in range(3))
            xc = x0 + pos * (x1 - x0)
            draw.polygon([(px * s, py * s) for px, py in band_poly(xc, fy0, FILM_H, lean, 8)], fill=col)
    mid = (fy0 + sy1) / 2
    arrow(draw, (x0 - 8) * s, mid * s, -1, 1.0)
    arrow(draw, (x1 + 8) * s, mid * s, +1, 1.0)
    return im.resize((SIZE, SIZE), Image.LANCZOS)


# ---------- gradient ----------

G_W, G_H, G_TOP = 320.0, 290.0, 95.0  # specimen at rest, tile pixels
D_TOP, D_BOT = 3.5, 48.0  # drawn grain size at the surface and at the bottom
G_END = 0.20
# (position along the surface, strain in the paper at which the band shows), Nanomaterials 2021 Fig. 6;
# the first band sits at the model's edge in the paper and is moved in slightly here.
G_BANDS = [(0.03, 0.045), (0.42, 0.07), (0.94, 0.07), (0.32, 0.09), (0.62, 0.09), (0.76, 0.09),
           (0.14, 0.14), (0.52, 0.14), (0.84, 0.14)]


def grain_size(y: float) -> float:
    return D_TOP * (D_BOT / D_TOP) ** (y / G_H)


def grain_mosaic(seed: int = 7) -> Image.Image:
    """Grains (Voronoi cells) that grow from the surface to the interior, drawn once at rest."""
    rng = np.random.default_rng(seed)
    pts, y = [], 0.0
    while y < G_H:
        d = grain_size(y)
        n = max(1, int(round(G_W / d)))
        xs = (np.arange(n) + 0.5 + rng.uniform(-0.4, 0.4, n)) * G_W / n
        ys = np.clip(y + d / 2 + rng.uniform(-0.35, 0.35, n) * d, 0, G_H)
        pts += list(zip(xs, ys))
        y += d
    pts = np.array(pts) * SS
    w, h = int(G_W * SS), int(G_H * SS)
    labels = np.zeros((h, w), np.int32)
    xs = np.arange(w) + 0.5
    for y0 in range(0, h, 16):
        rows = np.arange(y0, min(y0 + 16, h)) + 0.5
        margin = 2.5 * grain_size(min(y0 / SS + 24, G_H)) * SS
        idx = np.nonzero(np.abs(pts[:, 1] - rows.mean()) < margin)[0]
        dx = xs[None, None, :] - pts[idx, 0][:, None, None]
        dy = rows[None, :, None] - pts[idx, 1][:, None, None]
        labels[y0:y0 + len(rows)] = idx[np.argmin(dx * dx + dy * dy, axis=0)]
    tint = rng.uniform(0.10, 0.42, len(pts))
    light = np.array([233, 237, 243], float)
    colors = (light[None, :] * (1 - tint[:, None]) + BLUE[None, :] * tint[:, None]).astype(np.uint8)
    rgb = colors[labels]
    edge = np.zeros((h, w), bool)
    for k in (1, 2):
        edge[:, :-k] |= labels[:, :-k] != labels[:, k:]
        edge[:-k, :] |= labels[:-k, :] != labels[k:, :]
    rgb[edge] = (250, 251, 253)
    return Image.fromarray(rgb)


def gradient_frame(t: float, mosaic: Image.Image) -> Image.Image:
    eps = G_END * smooth((t - 0.8) / 4.2)
    s = SS
    im = Image.new("RGB", (SIZE * s, SIZE * s), BG)
    w, h = G_W * (1 + eps), G_H / math.sqrt(1 + eps)
    x0, y0 = SIZE / 2 - w / 2, G_TOP + (G_H - h) / 2
    im.paste(mosaic.resize((int(w * s), int(h * s)), Image.LANCZOS), (int(x0 * s), int(y0 * s)))
    draw = ImageDraw.Draw(im)
    for pos, at in G_BANDS:
        show = smooth((eps - (at - 0.004)) / 0.004)
        if show <= 0:
            continue
        col = tuple(int(BG[i] + (ORANGE[i] - BG[i]) * show) for i in range(3))
        width = 2.6 + 1.8 * smooth((eps - at) / 0.06)
        length = 22.0
        xc = x0 + pos * w
        draw.polygon([((xc - width / 2) * s, y0 * s), ((xc + width / 2) * s, y0 * s),
                      ((xc + width / 2 + length) * s, (y0 + length) * s), ((xc - width / 2 + length) * s, (y0 + length) * s)],
                     fill=col)
    mid = y0 + h / 2
    arrow(draw, (x0 - 8) * s, mid * s, -1, 1.0)
    arrow(draw, (x0 + w + 8) * s, mid * s, +1, 1.0)
    return im.resize((SIZE, SIZE), Image.LANCZOS)


# ---------- necking ----------

N_L0, N_FILM, N_SUB = 290.0, 24.0, 104.0
N_TOPS = (70.0, 272.0)  # film top edge of each specimen at rest
FILM_BROWN = (181, 116, 60)
GSL = [(144, 112, 1), (201, 151, 2), (246, 186, 2), (255, 208, 17), (255, 229, 119)]  # Fig. 1, surface first
GSL_LAYER = 11.0  # each layer's thickness at rest
INTERFACE = (252, 252, 250)
N_END = 0.33
CG_NECK_AT, GRAD_NECK_AT = 0.20, 0.32  # IJSS 2019 Fig. 13a, interface at least 2.5 times the film's yield strength


def necking_layers(graded: bool) -> list[tuple[float, tuple[int, int, int]]]:
    """The substrate at rest from the interface down: (depth of each layer's bottom, its color)."""
    gsl = [(GSL_LAYER * (i + 1), color) for i, color in enumerate(GSL)] if graded else []
    return gsl + [(N_SUB, GRAY)]


def necking_depth(d: float, eps: float) -> float:
    """Where a point d below the film's top at rest sits at strain eps, as the specimen thins about its middle."""
    q = 1 / (1 + eps)  # plane strain thinning
    return (1 - q) * (N_FILM + N_SUB) / 2 + d * q


def necking_profile(eps: float, graded: bool, n: int = 161):
    """x along the stretched specimen, the film's top surface and the interface, in tile pixels below the film's
    top at rest. The film thins from both faces at the notch, and the substrate's surface rises into the neck."""
    length = N_L0 * (1 + eps)
    xr = np.linspace(-length / 2, length / 2, n)
    notch = np.clip(3.0 - np.abs(xr) * 0.75, 0, None)
    film = N_FILM / (1 + eps)
    if graded:  # broad and shallow
        neck = film * smooth((eps - 0.25) / (GRAD_NECK_AT - 0.25)) * np.exp(-(xr / 42.0) ** 2)
        drop, rise = 0.18 * neck, 0.12 * neck
    else:  # sharp and deep
        neck = film * smooth((eps - CG_NECK_AT) / 0.13) * np.exp(-(xr / 11.0) ** 2)
        drop, rise = 0.40 * neck, 0.25 * neck
    return xr, necking_depth(0.0, eps) + notch + drop, necking_depth(N_FILM, eps) - rise


def necking_boundaries(eps: float, graded: bool):
    """x along the stretched specimen, and the film's top surface and every boundary below it (the interface,
    then each layer's bottom), in tile pixels below the film's top at rest. The layers follow the interface's
    rise into the neck less and less with depth, down to the gradient layer's base."""
    xr, film_top, interface = necking_profile(eps, graded)
    rise = necking_depth(N_FILM, eps) - interface
    reach = GSL_LAYER * len(GSL)
    curves = [film_top, interface]
    for bottom, _ in necking_layers(graded):
        curves.append(necking_depth(N_FILM + bottom, eps) - rise * max(0.0, 1 - bottom / reach))
    return xr, curves


def necking_frame(t: float) -> Image.Image:
    eps = N_END * smooth((t - 0.8) / 4.6)
    s = SS
    im = Image.new("RGB", (SIZE * s, SIZE * s), BG)
    draw = ImageDraw.Draw(im)
    for top, graded in zip(N_TOPS, (False, True)):
        xr, curves = necking_boundaries(eps, graded)
        xs = SIZE / 2 + xr
        colors = [FILM_BROWN] + [color for _, color in necking_layers(graded)]
        for upper, lower, color in zip(curves, curves[1:], colors):
            outline = [(x * s, (top + y) * s) for x, y in zip(xs, upper)]
            outline += [(x * s, (top + y) * s) for x, y in zip(xs[::-1], lower[::-1])]
            draw.polygon(outline, fill=color)
        draw.line([(x * s, (top + y) * s) for x, y in zip(xs, curves[1])], fill=INTERFACE, width=int(1.2 * s))
        mid = top + (curves[0][0] + curves[-1][0]) / 2
        arrow(draw, (xs[0] - 8) * s, mid * s, -1, 1.0)
        arrow(draw, (xs[-1] + 8) * s, mid * s, +1, 1.0)
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def crossfade_loop(frame, hold_end: float, total: float) -> list[Image.Image]:
    """Frames of frame(t) up to hold_end, then a fade back to the first frame so the loop is seamless."""
    first, last = frame(0.0), frame(hold_end)
    return [frame(i / FPS) if i / FPS < hold_end else Image.blend(last, first, smooth((i / FPS - hold_end) / (total - hold_end)))
            for i in range(int(total * FPS))]


@dataclass
class Drawing:
    frame: Callable[[float], Image.Image]
    hold_end: float  # the picture changes until here, then fades back to its first frame
    length: float

    def frames(self) -> list[Image.Image]:
        return crossfade_loop(self.frame, self.hold_end, self.length)


@functools.cache
def _mosaic() -> Image.Image:
    return grain_mosaic()


DRAWINGS = {
    "films": Drawing(films_frame, 6.4, 7.2),
    "gradient": Drawing(lambda t: gradient_frame(t, _mosaic()), 6.4, 7.2),
    "necking": Drawing(necking_frame, 6.6, 7.4),
}


def render(name: str, out: Path, ffmpeg: str) -> None:
    encode(DRAWINGS[name].frames(), out, ffmpeg)
