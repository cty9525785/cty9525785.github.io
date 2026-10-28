import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.content import OtherPub, Segment, SourceMovie, Tile, TileInput, load_papers, movie_file, poster_file
from tools.media import GRAPHS, Job, check_tile, ffmpeg_args, graph_speeds, other_tile_args, plan_jobs, tile_args
from tools.mp4meta import probe

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media"
MIB = 1024 * 1024
# Decoding frames needs ffmpeg: set FFMPEG to its path, or put it on PATH.
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg")


class PlanJobsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.papers, _ = load_papers(ROOT / "content" / "papers.toml")

    def make_sources(self, folder: Path, skip: str = "") -> None:
        for paper in self.papers:
            for movie in paper.movies:
                if movie.source and movie.source != skip:
                    (folder / movie.source).write_bytes(b"x")

    def test_plan_jobs_names(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as root:
            self.make_sources(Path(src))
            jobs = plan_jobs(self.papers, [Path(src)], Path(root))
            by_dst = {job.dst.relative_to(root).as_posix(): job for job in jobs}
            job = by_dst["media/stiffness-driven-control/movie-s4.mp4"]
            self.assertEqual(job.src.name, "sciadv.aeg3346_movie_s4.mp4")
            self.assertEqual(job.process, "remux")
            self.assertEqual(by_dst["media/scale-inspired-robotic-structures/movie-s2.mp4"].process, "remux")
            # The IJMS camera recordings are not published: the page shows their trimmed clips instead.
            self.assertNotIn("media/programmable-morphing-structure/movie-4.mp4", by_dst)
            self.assertEqual(len(jobs), 12 + 4)
            linked = [replace(p, media_mode="link") if p.slug == "stiffness-driven-control" else p for p in self.papers]
            self.assertEqual(len(plan_jobs(linked, [Path(src)], Path(root))), 12)  # link-mode movies stay on the journal's site

    def test_camera_movies_lose_their_sound(self):
        # Raw lab recordings can catch voices, so their web copies are silent.
        args = ffmpeg_args(Job(Path("in.mp4"), Path("out.mp4"), "silent1080"), "ffmpeg")
        self.assertIn("-an", args)
        self.assertNotIn("0:a?", args)
        self.assertIn("scale=-2:1080", args)
        self.assertIn("-map_metadata", args)

    def test_tile_args(self):
        paper = next(p for p in self.papers if p.slug == "scale-inspired-robotic-structures")
        folder = MEDIA / paper.slug
        args = tile_args(paper, folder, MEDIA / "loop.mp4", "ffmpeg")
        inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
        self.assertEqual([Path(p).name for p in inputs],
                         ["movie-s11.mp4", "movie-s11.mp4", "movie-s4.mp4", "movie-s5.mp4", "movie-s6.mp4"])
        self.assertEqual(args[args.index("-i") - 4:args.index("-i")], ["-ss", "7.00", "-t", "8.00"])
        self.assertEqual(args[args.index("-/filter_complex") + 1], str(GRAPHS / "scale-inspired-robotic-structures.graph"))
        self.assertEqual(args[args.index("-map") + 1], "[out]")
        self.assertIn("-an", args)


    def test_tile_from_an_unpublished_movie_reads_the_original(self):
        paper = next(p for p in self.papers if p.slug == "programmable-morphing-structure")
        with tempfile.TemporaryDirectory() as src:
            self.make_sources(Path(src))
            args = tile_args(paper, MEDIA / paper.slug, MEDIA / "loop.mp4", "ffmpeg", [Path(src)])
            inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
            self.assertEqual(inputs, [str(Path(src) / "MVI_7208.MP4")] * 2)

    def test_other_tile_args_read_the_published_movies(self):
        # Co-authored rows have no page movies, so their loops are cut straight from the published ones.
        pub = OtherPub("b", ["B. Author", "T. Chen"], 2, "X", "Y 1, 1 (2024)", "10.1/y", "O.", "draft", "",
                       tile=Tile("clip", "b.graph", [TileInput("S2", 1.0, 6.0)], [Segment(0.0, 2.0)]),
                       movies=[SourceMovie("S2", "B 2024 J - Movie S2.mp4", 2.0)])
        with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as src:
            (Path(src) / "B 2024 J - Movie S2.mp4").write_bytes(b"x")
            args = other_tile_args(pub, [Path(empty), Path(src)], MEDIA / "loop.mp4", "ffmpeg")
            inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
            self.assertEqual(inputs, [str(Path(src) / "B 2024 J - Movie S2.mp4")])
        self.assertEqual(args[args.index("-i") - 4:args.index("-i")], ["-ss", "1.00", "-t", "6.00"])
        self.assertEqual(args[args.index("-/filter_complex") + 1], str(GRAPHS / "b.graph"))
        check_tile(pub, "[0:v]setpts=(PTS-STARTPTS)/1,fps=30[out]")  # the movie's own 2x speed counts
        with self.assertRaises(ValueError):
            check_tile(pub, "[0:v]setpts=(PTS-STARTPTS)/2,fps=30[out]")

    def test_first_folder_with_the_file_wins(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as root:
            self.make_sources(Path(b))
            (Path(a) / "sciadv.aeg3346_movie_s1.mp4").write_bytes(b"y")
            jobs = plan_jobs(self.papers, [Path(a), Path(b)], Path(root))
            src = {job.dst.name: job.src for job in jobs if "stiffness-driven-control" in job.dst.as_posix()}
            self.assertEqual(src["movie-s1.mp4"].parent, Path(a))
            self.assertEqual(src["movie-s2.mp4"].parent, Path(b))

    def test_missing_source_raises(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as root:
            self.make_sources(Path(src), skip="scirobotics.adl0307_movie_S7.mp4")
            with self.assertRaises(FileNotFoundError):
                plan_jobs(self.papers, [Path(src)], Path(root))


class TileSpeedTest(unittest.TestCase):
    """The tile label states each part's true speed, so the graph may change speed only in ways this check reads."""

    @classmethod
    def setUpClass(cls):
        cls.papers, _ = load_papers(ROOT / "content" / "papers.toml")

    def test_graph_speeds(self):
        self.assertEqual(graph_speeds("[0:v]crop=10:10:0:0,setpts=(PTS-STARTPTS)/4,scale=480:480[out]"), {0: 4.0})
        self.assertEqual(graph_speeds("[0:v]crop=8:8:0:'2+3*pow(min(t/4,1),2)',scale=48:48[a];[a]fade=t=out:st=1:d=1[out]"),
                         {0: 1.0})
        # A wide shot padded to a square on its own background color: padding cannot change speed.
        self.assertEqual(graph_speeds("[0:v]crop=16:9:0:0,pad=16:16:0:3:black,setpts=(PTS-STARTPTS)/5[out]"), {0: 5.0})
        bad = {
            "other setpts form": "[0:v]setpts=0.5*PTS[out]",
            "two setpts": "[0:v]setpts=(PTS-STARTPTS)/2,setpts=(PTS-STARTPTS)/2[out]",
            "setpts after mixing": "[0:v]scale=48:48[a];[a]setpts=(PTS-STARTPTS)/2[out]",
            "unknown filter": "[0:v]minterpolate=fps=60[out]",
        }
        for name, graph in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                graph_speeds(graph)

    def test_every_clip_label_matches_its_graph(self):
        for paper in self.papers:
            if paper.tile is not None and paper.tile.kind == "clip":
                with self.subTest(paper.slug):
                    check_tile(paper, (GRAPHS / paper.tile.graph).read_text(encoding="utf-8"))

    def test_check_tile_catches_a_wrong_label(self):
        paper = next(p for p in self.papers if p.slug == "stiffness-driven-control")
        wrong = replace(paper, tile=replace(paper.tile, segments=[Segment(0.0, 5.0)]))  # forgets S2's own 10x
        with self.assertRaises(ValueError):
            check_tile(wrong, (GRAPHS / paper.tile.graph).read_text(encoding="utf-8"))

    def test_label_switches_on_a_black_frame(self):
        # The label changes when the footage changes speed; that cut must fall on black, not on live footage.
        if FFMPEG is None:
            self.skipTest("ffmpeg not found; set FFMPEG")
        for paper in self.papers:
            if paper.tile is None:
                continue
            for segment in paper.tile.segments[1:]:
                with self.subTest(f"{paper.slug} at {segment.at}"):
                    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{segment.at + 0.02:.3f}",
                                          "-i", str(MEDIA / paper.slug / "loop.mp4"), "-frames:v", "1",
                                          "-vf", "format=gray", "-f", "rawvideo", "-"],
                                         capture_output=True, check=True).stdout
                    self.assertTrue(raw)
                    self.assertLess(sum(raw) / len(raw), 10)


class MediaOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.papers, _ = load_papers(ROOT / "content" / "papers.toml")

    def test_outputs_web_ready(self):
        for paper in self.papers:
            if paper.media_mode != "embed":
                continue
            for movie in paper.movies:
                if not movie.publish:
                    self.assertFalse((MEDIA / paper.slug / movie_file(movie)).exists(), movie.id)
                    continue
                with self.subTest(f"{paper.slug} {movie.id}"):
                    path = MEDIA / paper.slug / movie_file(movie)
                    info = probe(path)
                    self.assertTrue(info.faststart)
                    self.assertLessEqual(info.height, 1080)
                    self.assertLessEqual(path.stat().st_size, 100 * MIB)
                    self.assertTrue((MEDIA / paper.slug / poster_file(movie)).stat().st_size > 0)

    def test_probe_known_values(self):
        # Hand-checked against the source file: Sci. Robot. S1 is 172.8 s of silent 1080p.
        sails = probe(MEDIA / "scale-inspired-robotic-structures" / "movie-s1.mp4")
        self.assertAlmostEqual(sails.duration, 172.8, delta=0.2)
        self.assertEqual((sails.width, sails.height, sails.has_audio), (1920, 1080, False))

    def test_loops(self):
        _, others = load_papers(ROOT / "content" / "papers.toml")
        for paper in self.papers + others:
            if paper.tile is None:
                continue
            with self.subTest(paper.slug):
                path = MEDIA / paper.slug / "loop.mp4"
                info = probe(path)
                self.assertFalse(info.has_audio)
                self.assertEqual((info.width, info.height), (480, 480))  # fills the square home page tile
                self.assertGreaterEqual(info.duration, 4.0)
                self.assertLessEqual(info.duration, 12.0)  # the Science Robotics tile runs 11.4 s
                self.assertLessEqual(path.stat().st_size, 2_500_000)
                self.assertTrue((MEDIA / paper.slug / "loop-poster.jpg").stat().st_size > 0)

    def test_media_total(self):
        total = sum(p.stat().st_size for p in MEDIA.rglob("*") if p.is_file())
        self.assertLessEqual(total, 1_000_000_000)


if __name__ == "__main__":
    unittest.main()
