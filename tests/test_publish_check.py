import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.check_publish import (content_problems, file_problems, hosted_pdfs, paper_pdf_problems, pdf_problems,
                                 public_allowances)
from tools.content import load_papers, load_site

ROOT = Path(__file__).resolve().parents[1]


def clean_pdf() -> bytes:
    import fitz  # PyMuPDF
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Curriculum vitae")
    doc.set_metadata({"title": "CV", "author": "Someone"})
    return doc.tobytes()


def paper_pdf(text: str, **metadata) -> bytes:
    import fitz  # PyMuPDF
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.set_metadata({"title": "A paper", "author": "A. Author", **metadata})
    return doc.tobytes()


STAMP = ("Downloaded from https://publisher.example/doi/10.1/x by A UNIVERSITY, Online Library on [28/10/2026]. "
         "See the Terms and Conditions")


def git_repo_with(files: dict[str, bytes]) -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return tmp


class ContentProblemsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = load_site(ROOT / "content" / "site.toml")
        cls.papers, cls.others = load_papers(ROOT / "content" / "papers.toml")

    def test_cv_draft_is_flagged(self):
        # The experience, education and skills text stays a draft until Tianyu confirms it on the built page.
        self.assertIn("site.cv: draft", content_problems(replace(self.site, cv_status="draft"), self.papers, self.others))
        self.assertNotIn("site.cv: draft",
                         content_problems(replace(self.site, cv_status="confirmed"), self.papers, self.others))

    def test_reports_placeholders_and_drafts(self):
        site = replace(self.site, bio="TODO: bio", links={**self.site.links, "email": "TODO: address"})
        papers = [replace(p, summary_status="draft") if p.slug == "programmable-morphing-structure"
                  else replace(p, summary_status="confirmed") for p in self.papers]
        others = [replace(o, summary_status="draft") if o.slug == "active-fabrics"
                  else replace(o, summary_status="confirmed") for o in self.others]
        problems = content_problems(site, papers, others, ROOT)
        self.assertIn("other.active-fabrics.one_line: draft", problems)
        self.assertNotIn("other.hierarchical-tessellation.one_line: draft", problems)
        self.assertIn("site.bio", problems)
        self.assertIn("site.links.email", problems)
        drafted = content_problems(replace(self.site, bio="A bio.", bio_status="draft"), papers, others, ROOT)
        self.assertIn("site.bio: draft", drafted)  # a bio Claude drafted waits for Tianyu, like the one-liners
        self.assertIn("paper.programmable-morphing-structure.summary: draft", problems)
        self.assertNotIn("paper.scale-inspired-robotic-structures.summary: draft", problems)

    def test_reports_placeholder_photo(self):
        placeholder = replace(self.site, photo="assets/img/photo-placeholder.svg")
        self.assertIn("site.photo: placeholder image", content_problems(placeholder, self.papers, self.others, ROOT))
        real = replace(self.site, photo="assets/img/photo.jpg")
        self.assertNotIn("site.photo: placeholder image", content_problems(real, self.papers, self.others, ROOT))

    def test_allowances_come_from_the_site(self):
        email = "someone" + "@" + "university.example"
        chosen = replace(self.site, links={**self.site.links, "email": email, "cv": "files/cv.pdf"})
        self.assertEqual(public_allowances(chosen), ({email}, {"files/cv.pdf"}))
        pending = replace(self.site, links={k: "TODO: later" for k in self.site.links})
        self.assertEqual(public_allowances(pending), (set(), set()))
        # The paper pages show each corresponding author's email, which the papers' data names.
        emails, _ = public_allowances(pending, self.papers)
        self.assertEqual(emails, {"yifan.wang@ntu.edu.sg", "mejjli@csu.edu.cn"})

    def test_clean_when_filled(self):
        site = replace(self.site, bio="Bio.", bio_status="confirmed", cv_status="confirmed", photo="assets/img/photo.jpg",
                       links={k: "https://example.invalid/" for k in self.site.links})
        papers = [replace(p, summary_status="confirmed")
                  for p in self.papers]
        others = [replace(o, summary_status="confirmed", thumb="") for o in self.others]
        self.assertEqual(content_problems(site, papers, others, ROOT), [])

    def test_link_mode_with_local_movies_is_reported(self):
        papers = [replace(p, media_mode="link") if p.slug == "scale-inspired-robotic-structures" else p
                  for p in self.papers]
        problems = content_problems(self.site, papers, self.others, ROOT)
        self.assertIn("paper.scale-inspired-robotic-structures: link mode but movies exist in media/", problems)


class PublishedPdfTest(unittest.TestCase):
    def test_published_cv_is_clean(self):
        site = load_site(ROOT / "content" / "site.toml")
        self.assertEqual(pdf_problems(ROOT / site.links["cv"]), [])

    def test_catches_phone_postcode_and_metadata(self):
        import fitz  # PyMuPDF
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cv.pdf"
            doc = fitz.open()
            doc.new_page().insert_text((72, 72), "Lab, Bristol BS16 1QY, UK (+44)7900000000")
            doc.set_metadata({"title": "CV", "author": "Someone", "creator": "a user account"})
            doc.save(path)
            self.assertEqual(pdf_problems(path), ["phone number", "postcode", "metadata beyond title and author"])


class HostedPaperPdfTest(unittest.TestCase):
    def test_hosted_papers_are_clean(self):
        papers, others = load_papers(ROOT / "content" / "papers.toml")
        self.assertEqual(len(hosted_pdfs(papers, others)), 13)  # seven papers, six supplements
        for path in sorted(hosted_pdfs(papers, others)):
            self.assertEqual(paper_pdf_problems(ROOT / path), [], path)

    def test_catches_download_stamps_and_metadata(self):
        # What a download adds: the stamp naming who downloaded the PDF and when, and the reader's metadata.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "paper.pdf"
            path.write_bytes(paper_pdf(f"Results.\n{STAMP}", creator="a user account"))
            self.assertEqual(paper_pdf_problems(path), ["download stamp", "metadata beyond title and author"])
            path.write_bytes(paper_pdf("Results."))
            self.assertEqual(paper_pdf_problems(path), [])

    def test_papers_keep_what_they_print(self):
        # A paper prints its authors' institutions and the corresponding author's contact as published; the CV may not.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "paper.pdf"
            path.write_bytes(paper_pdf("Lab, Bristol BS16 1QY, UK (+44)7900000000 " + "someone" + "@" + "university.example"))
            self.assertEqual(paper_pdf_problems(path), [])
            self.assertEqual(pdf_problems(path), ["phone number", "postcode"])


class FileProblemsTest(unittest.TestCase):
    def test_current_repo_is_clean(self):
        # As main() runs it: the email, CV and open-access papers the owner chose to publish are allowed, nothing else.
        papers, others = load_papers(ROOT / "content" / "papers.toml")
        emails, files = public_allowances(load_site(ROOT / "content" / "site.toml"), papers)
        self.assertEqual(file_problems(ROOT, allow_emails=emails, allow_files=files,
                                       paper_pdfs=hosted_pdfs(papers, others)), [])

    def test_hosted_papers_pass_their_own_check(self):
        tmp = git_repo_with({"files/papers/a.pdf": paper_pdf("Lab, Bristol BS16 1QY"),
                             "files/papers/b.pdf": paper_pdf(STAMP), "files/other.pdf": paper_pdf("Results.")})
        with tmp:
            problems = file_problems(Path(tmp.name), paper_pdfs={"files/papers/a.pdf", "files/papers/b.pdf"})
        self.assertFalse(any(p.startswith("files/papers/a.pdf") for p in problems), problems)
        self.assertIn("files/papers/b.pdf: download stamp", problems)
        self.assertIn("files/other.pdf: private file type", problems)

    def test_catches_private_files_and_trackers(self):
        tmp = git_repo_with({
            "CV.docx": b"x",
            "paper.pdf": b"x",
            "page.html": b'<script src="https://www.googletagmanager.com/gtag/js"></script>',
            "notes.md": b"write to someone" + b"@" + b"gmail.com",
            "ok.md": b"placeholder site" + b"@" + b"example.invalid",
        })
        with tmp:
            problems = file_problems(Path(tmp.name))
        self.assertIn("CV.docx: private file type", problems)
        self.assertIn("paper.pdf: private file type", problems)
        self.assertIn("page.html: tracking marker googletagmanager", problems)
        self.assertIn("notes.md: email address", problems)
        self.assertFalse(any(p.startswith("ok.md") for p in problems))

    def test_public_email_and_cv_are_allowed(self):
        email = "someone" + "@" + "university.example"
        tmp = git_repo_with({
            "index.html": f'<a href="mailto:{email}">Email</a>'.encode(),
            "files/cv.pdf": clean_pdf(),
            "other.pdf": b"%PDF",
            "notes.md": ("other" + "@" + "elsewhere.example").encode(),
        })
        with tmp:
            problems = file_problems(Path(tmp.name), allow_emails={email}, allow_files={"files/cv.pdf"})
        self.assertFalse(any(p.startswith(("index.html", "files/cv.pdf")) for p in problems), problems)
        self.assertIn("other.pdf: private file type", problems)
        self.assertIn("notes.md: email address", problems)

    def test_license_texts_may_name_their_licensors(self):
        # A font license must ship verbatim, and it carries the font authors' address.
        licensor = "team" + "@" + "fonts.example"
        tmp = git_repo_with({"assets/fonts/x/OFL.txt": f"Copyright 2010 by a foundry ({licensor})".encode(),
                             "page.html": licensor.encode()})
        with tmp:
            problems = file_problems(Path(tmp.name))
        self.assertFalse(any(p.startswith("assets/fonts/x/OFL.txt") for p in problems), problems)
        self.assertIn("page.html: email address", problems)

    def test_catches_private_words(self):
        # The real list (target employers, private folder names) lives outside the repo.
        tmp = git_repo_with({"content/x.toml": b"# ordered as in the Acme CV\n", "ok.md": b"fine\n"})
        with tmp:
            problems = file_problems(Path(tmp.name), deny_words={"Acme"})
        self.assertIn("content/x.toml: private word Acme", problems)
        self.assertFalse(any(p.startswith("ok.md") for p in problems))

    def test_catches_private_traces_in_movie_metadata(self):
        def box(kind: bytes, payload: bytes) -> bytes:
            return (8 + len(payload)).to_bytes(4, "big") + kind + payload
        ftyp = box(b"ftyp", b"isom\0\0\2\0")
        mdat = box(b"mdat", b"frames that mention D:" + b"\\" + b"only inside the media data")
        trace = b"<x:xmpmeta>C:" + b"\\" + b"projects" + b"\\" + b"edit.prproj</x:xmpmeta>"
        tmp = git_repo_with({"dirty.mp4": ftyp + box(b"uuid", b"\0" * 16 + trace) + mdat,
                             "clean.mp4": ftyp + box(b"free", b"\0" * 8) + mdat})
        with tmp:
            problems = file_problems(Path(tmp.name))
        self.assertIn("dirty.mp4: metadata carries private traces", problems)
        self.assertFalse(any(p.startswith("clean.mp4") for p in problems), problems)

    def test_catches_oversized_files(self):
        tmp = git_repo_with({"big.mp4": b"\0" * 1024})
        with tmp:
            problems = file_problems(Path(tmp.name), max_file=1000, max_total=10**9)
        self.assertIn("big.mp4: larger than 100 MiB", problems)


if __name__ == "__main__":
    unittest.main()
