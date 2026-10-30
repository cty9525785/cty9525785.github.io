"""Turn the papers' movies into web-ready files: movies, poster frames and home page tiles.

Usage: python -X utf8 tools/media.py --ffmpeg path/to/ffmpeg --src folder [--src folder ...] [--force]

Each movie's source file is looked up by name in the --src folders, in order. Converted movies are
kept between runs unless --force is given; posters and tiles are always regenerated, since they
depend on the times set in content/papers.toml. A clip tile is cut from the web copies of the
paper's movies by its ffmpeg graph in tools/tiles/; a drawn tile comes from tools/drawings.py. A co-authored
row's clip is cut the same way, straight from the published movies found in the --src folders.
"""
import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # lets `python tools/media.py` import the tools package
    sys.path.insert(0, str(ROOT))

from tools.content import OtherPub, Paper, Tile, load_papers, movie_file, poster_file  # noqa: E402
from tools.mp4meta import probe  # noqa: E402

QUIET = ["-hide_banner", "-loglevel", "error"]
GRAPHS = ROOT / "tools" / "tiles"
# The filters a tile graph may use. Of these only setpts changes speed, and only in the one form
# graph_speeds reads, so a tile's label cannot drift from what it plays.
TILE_FILTERS = {"crop", "pad", "scale", "fps", "format", "settb", "setpts", "drawbox", "color", "colorlevels", "vstack",
                "hstack", "xfade", "fade", "tpad", "concat"}
SETPTS = re.compile(r"setpts=\(PTS-STARTPTS\)/(\d+(?:\.\d+)?)")
LABEL = re.compile(r"\[[^\]]*\]")
INPUT = re.compile(r"\[(\d+):v\]")


@dataclass
class Job:
    src: Path
    dst: Path
    process: str


def _find_source(name: str, src_dirs: list[Path]) -> Path:
    for folder in src_dirs:
        candidate = Path(folder) / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{name} is not in any --src folder")


def plan_jobs(papers: list[Paper], src_dirs: list[Path], root: Path) -> list[Job]:
    """One job per movie of every embedded paper; link-mode papers, process "none" and unpublished movies are
    skipped."""
    jobs = []
    for paper in papers:
        if paper.media_mode != "embed":
            continue
        for movie in paper.movies:
            if movie.process == "none" or not movie.publish:
                continue
            src = _find_source(movie.source, src_dirs)
            jobs.append(Job(src, Path(root) / "media" / paper.slug / movie_file(movie), movie.process))
    return jobs


def ffmpeg_args(job: Job, ffmpeg: str) -> list[str]:
    # -map_metadata -1 drops the editing software's metadata (project paths, clip names, GPS).
    if job.process == "remux":
        return [ffmpeg, *QUIET, "-y", "-i", str(job.src), "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "-1",
                "-c", "copy", "-movflags", "+faststart", str(job.dst)]
    if job.process == "reencode1080":
        return [ffmpeg, *QUIET, "-y", "-i", str(job.src), "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "-1",
                "-vf", "scale=-2:1080", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(job.dst)]
    if job.process == "silent1080":  # raw lab recordings: the sound could catch voices
        return [ffmpeg, *QUIET, "-y", "-i", str(job.src), "-map", "0:v:0", "-map_metadata", "-1",
                "-vf", "scale=-2:1080", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
                "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(job.dst)]
    raise ValueError(f"no ffmpeg command for process {job.process!r}")


def poster_args(movie: Path, at: float, out: Path, ffmpeg: str) -> list[str]:
    return [ffmpeg, *QUIET, "-y", "-ss", f"{at:.2f}", "-i", str(movie), "-frames:v", "1",
            "-vf", "scale=1280:-2", "-q:v", "3", str(out)]


def _split(text: str, sep: str) -> list[str]:
    """Split on sep outside quotes and parentheses, as ffmpeg reads a filtergraph."""
    parts, current, depth, quoted = [], [], 0, False
    for ch in text:
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch in "()":
            depth += 1 if ch == "(" else -1
        if ch == sep and not quoted and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def graph_speeds(text: str) -> dict[int, float]:
    """How many times faster each input's footage plays; raise on anything that could change speed unread."""
    speeds = {}
    for chain in _split(text, ";"):
        first = INPUT.match(chain)
        factor = None
        for f in _split(LABEL.sub("", chain), ","):
            name = f.split("=", 1)[0]
            if name not in TILE_FILTERS:
                raise ValueError(f"tile graph uses {name!r}, which the speed check cannot read")
            if name == "setpts":
                match = SETPTS.fullmatch(f)
                if match is None or first is None or factor is not None:
                    raise ValueError(f"tile graph changes speed in a way the speed check cannot read: {f!r}")
                factor = float(match.group(1))
        if first is not None:
            speeds[int(first.group(1))] = factor or 1.0
    return speeds


def check_tile(paper: Paper | OtherPub, graph: str) -> None:
    """Raise unless the tile's segment speeds are what its graph plays, input by input, in order."""
    speeds = graph_speeds(graph)
    inputs = paper.tile.inputs
    if sorted(speeds) != list(range(len(inputs))):
        raise ValueError(f"{paper.slug}: the graph reads {len(speeds)} inputs, the tile lists {len(inputs)}")
    source = {m.id: m.source_speed for m in paper.movies}
    true = [speeds[i] * source[inp.movie] for i, inp in enumerate(inputs)]
    played = [s for k, s in enumerate(true) if k == 0 or s != true[k - 1]]
    labeled = [s.speed for s in paper.tile.segments]
    if played != labeled:
        raise ValueError(f"{paper.slug}: the label says {labeled}, the graph plays {played}")


def _tile_command(tile: Tile, inputs: list[Path], out: Path, ffmpeg: str) -> list[str]:
    args = [ffmpeg, *QUIET, "-y"]
    for i, path in zip(tile.inputs, inputs):
        args += ["-ss", f"{i.start:.2f}", "-t", f"{i.duration:.2f}", "-i", str(path)]
    return args + ["-/filter_complex", str(GRAPHS / tile.graph), "-map", "[out]", "-map_metadata", "-1", "-an",
                   "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                   str(out)]


def tile_args(paper: Paper, folder: Path, out: Path, ffmpeg: str, src_dirs: list[Path] = ()) -> list[str]:
    """Cut from the web copies, or from the original in src_dirs for a movie the site does not publish."""
    movies = {m.id: m for m in paper.movies}
    paths = [folder / movie_file(m) if m.publish else _find_source(m.source, src_dirs)
             for m in (movies[i.movie] for i in paper.tile.inputs)]
    return _tile_command(paper.tile, paths, out, ffmpeg)


def other_tile_args(pub: OtherPub, src_dirs: list[Path], out: Path, ffmpeg: str) -> list[str]:
    """A co-authored row's loop, cut straight from the published movies (it has no web copies of them)."""
    movies = {m.id: m for m in pub.movies}
    return _tile_command(pub.tile, [_find_source(movies[i.movie].source, src_dirs) for i in pub.tile.inputs],
                         out, ffmpeg)


def _loop_poster(tile: Tile, loop: Path, ffmpeg: str) -> None:
    _run([ffmpeg, *QUIET, "-y", "-ss", f"{tile.poster_at:.2f}", "-i", str(loop), "-frames:v", "1",
          "-q:v", "3", str(loop.parent / "loop-poster.jpg")])


def _run(args: list[str]) -> None:
    result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({result.returncode}): {' '.join(args)}\n{result.stderr}")


def run(papers: list[Paper], src_dirs: list[Path], root: Path, ffmpeg: str, force: bool = False,
        others: list[OtherPub] = ()) -> None:
    root = Path(root)
    for job in plan_jobs(papers, src_dirs, root):
        if job.dst.exists() and not force:
            continue
        job.dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"{job.process:13}{job.dst.relative_to(root).as_posix()}", flush=True)
        if job.process == "copy":
            shutil.copy2(job.src, job.dst)
        else:
            _run(ffmpeg_args(job, ffmpeg))
    for paper in papers:
        if paper.media_mode != "embed":
            continue
        folder = root / "media" / paper.slug
        for movie in paper.movies:
            if not movie.publish:
                continue
            web = folder / movie_file(movie)
            at = movie.poster_at if movie.poster_at is not None else 0.25 * probe(web).duration
            _run(poster_args(web, at, folder / poster_file(movie), ffmpeg))
        if paper.tile is not None:
            loop = folder / "loop.mp4"
            folder.mkdir(parents=True, exist_ok=True)
            if paper.tile.kind == "clip":
                check_tile(paper, (GRAPHS / paper.tile.graph).read_text(encoding="utf-8"))
                _run(tile_args(paper, folder, loop, ffmpeg, src_dirs))
            else:
                from tools import drawings  # needs numpy and Pillow, so only loaded for drawn tiles
                drawings.render(paper.tile.drawing, loop, ffmpeg)
            _loop_poster(paper.tile, loop, ffmpeg)
            print(f"{'tile':13}{loop.relative_to(root).as_posix()}", flush=True)
    for pub in others:
        if pub.tile is None:
            continue
        loop = root / "media" / pub.slug / "loop.mp4"
        loop.parent.mkdir(parents=True, exist_ok=True)
        check_tile(pub, (GRAPHS / pub.tile.graph).read_text(encoding="utf-8"))
        _run(other_tile_args(pub, src_dirs, loop, ffmpeg))
        _loop_poster(pub.tile, loop, ffmpeg)
        print(f"{'tile':13}{loop.relative_to(root).as_posix()}", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Make web-ready movies, posters and loops.")
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--src", action="append", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="convert movies again even if they exist")
    args = parser.parse_args(argv)
    papers, others = load_papers(ROOT / "content" / "papers.toml")
    run(papers, args.src, ROOT, args.ffmpeg, args.force, others)


if __name__ == "__main__":
    main()
