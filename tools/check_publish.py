"""List what still blocks publishing: placeholders, drafts, private files, trackers and size limits.

Usage: python -X utf8 tools/check_publish.py [--deny-file path/outside/repo.txt]   (exits 1 while anything is listed)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # lets `python tools/check_publish.py` import the tools package
    sys.path.insert(0, str(ROOT))

from tools.content import (  # noqa: E402
    PLACEHOLDER, OtherPub, Paper, Site, load_papers, load_site, movie_file, placeholders,
)

from tools.mp4meta import metadata_text  # noqa: E402

MIB = 1024 * 1024
PHOTO_PLACEHOLDER = "assets/img/photo-placeholder.svg"
MOVIE_SUFFIXES = {".mp4", ".mov", ".m4v"}
# Built without writing the word out, so this file does not trip the private-trace scans.
SYNCED_FOLDER = "One" + "Drive"
DRIVE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
XMP_MARKERS = ("xmpmeta", "<?xpacket")
PRIVATE_SUFFIXES = {".docx", ".doc", ".pdf", ".zip"}
TEXT_SUFFIXES = {".html", ".css", ".js", ".py", ".toml", ".md", ".svg", ".txt", ""}
TRACKERS = ("googletagmanager", "google-analytics", "gtag(", "analytics.js", "clarity.ms", "hotjar", "plausible")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# License texts that must ship verbatim; the addresses in them belong to the licensors, not the owner.
LICENSE_NAMES = {"OFL.txt"}
PHONE = re.compile(r"\+\s*\(?\s*\d{1,3}\s*\)?\s*\d[\d\s-]{6,}")
UK_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b")


def pdf_problems(path: Path) -> list[str]:
    """What a PDF the owner chose to publish (the CV) must not carry: a phone number, a postcode, or metadata
    beyond its title and author, where an account name or a folder path could hide."""
    import fitz  # PyMuPDF, needed only when a PDF is published

    try:  # read from memory, so a file that fails to open is not left locked
        with fitz.open(stream=Path(path).read_bytes(), filetype="pdf") as doc:
            text = " ".join(page.get_text() for page in doc)
            extra = {k: v for k, v in doc.metadata.items() if v and k not in ("format", "title", "author")}
            xmp = doc.get_xml_metadata()
    except (fitz.FileDataError, RuntimeError):
        return ["not a readable PDF"]
    problems = []
    if PHONE.search(text):
        problems.append("phone number")
    if UK_POSTCODE.search(text):
        problems.append("postcode")
    if extra or xmp:
        problems.append("metadata beyond title and author")
    return problems


def content_problems(site: Site, papers: list[Paper], others: list[OtherPub], root: Path = ROOT) -> list[str]:
    """Placeholders still to fill, drafts still to confirm, and link-mode papers whose movies exist locally."""
    problems = placeholders(site, papers, others)
    if site.photo == PHOTO_PLACEHOLDER:
        problems.append("site.photo: placeholder image")
    if site.bio_status == "draft" and not site.bio.startswith(PLACEHOLDER):
        problems.append("site.bio: draft")
    for paper in papers:
        if paper.summary_status == "draft":
            problems.append(f"paper.{paper.slug}.summary: draft")
        folder = Path(root) / "media" / paper.slug
        if paper.media_mode == "link" and any((folder / movie_file(m)).exists() for m in paper.movies):
            problems.append(f"paper.{paper.slug}: link mode but movies exist in media/")
    for pub in others:
        if pub.summary_status == "draft":
            problems.append(f"other.{pub.slug}.one_line: draft")
    return problems


def public_allowances(site: Site, papers: list[Paper] = ()) -> tuple[set[str], set[str]]:
    """The email address and CV file the owner chose to publish, and the corresponding authors' emails that the
    paper pages show, which the private checks must allow."""
    emails, files = set(), set()
    for paper in papers:
        emails |= set(paper.corresponding.values())
    email = site.links.get("email", "")
    if email and not email.startswith(PLACEHOLDER):
        emails.add(email)
    cv = site.links.get("cv", "")
    if cv and not cv.startswith(PLACEHOLDER) and not re.match(r"^[a-z][a-z0-9+.-]*:", cv):
        files.add(cv.lstrip("./"))
    return emails, files


def _tracked(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True).stdout
    return [name for name in out.split("\0") if name]


def file_problems(root: Path, max_file: int = 100 * MIB, max_total: int = 1_000_000_000,
                  deny_words: frozenset[str] = frozenset(), allow_emails: set[str] = frozenset(),
                  allow_files: set[str] = frozenset()) -> list[str]:
    """Problems in the files git tracks, which are exactly what GitHub Pages would publish.

    deny_words come from a private list kept outside the repo (for example target employers),
    so the list itself never becomes public.
    """
    problems, total = [], 0
    for name in _tracked(root):
        path = Path(root) / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        suffix = path.suffix.lower()
        if size > max_file:
            problems.append(f"{name}: larger than 100 MiB")
        if suffix in PRIVATE_SUFFIXES and name not in allow_files:
            problems.append(f"{name}: private file type")
        elif suffix == ".pdf":
            problems += [f"{name}: {problem}" for problem in pdf_problems(path)]
        if suffix in MOVIE_SUFFIXES:
            meta = metadata_text(path)
            if (any(marker in meta for marker in XMP_MARKERS) or SYNCED_FOLDER in meta or DRIVE_PATH.search(meta)
                    or any(e not in allow_emails for e in EMAIL.findall(meta))):
                problems.append(f"{name}: metadata carries private traces")
        text = path.read_text(encoding="utf-8", errors="replace") if suffix in TEXT_SUFFIXES else ""
        haystack = f"{name}\n{text}".lower()
        problems += [f"{name}: private word {word}" for word in sorted(deny_words) if word.lower() in haystack]
        if suffix in TEXT_SUFFIXES:
            if suffix in {".html", ".js", ".css"}:
                problems += [f"{name}: tracking marker {marker}" for marker in TRACKERS if marker in text]
            if path.name not in LICENSE_NAMES and any(not email.endswith("@example.invalid") and email not in allow_emails
                                                      for email in EMAIL.findall(text)):
                problems.append(f"{name}: email address")
    if total > max_total:
        problems.append(f"the site is {total / 1e9:.2f} GB, over the 1 GB limit")
    return problems


def _read_words(path: Path | None) -> frozenset[str]:
    if path is None:
        return frozenset()
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return frozenset(w.strip() for w in lines if w.strip() and not w.strip().startswith("#"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List what still blocks publishing.")
    parser.add_argument("--deny-file", type=Path, help="private word list kept outside the repo, one per line")
    args = parser.parse_args(argv)
    site = load_site(ROOT / "content" / "site.toml")
    papers, others = load_papers(ROOT / "content" / "papers.toml")
    emails, files = public_allowances(site, papers)
    problems = content_problems(site, papers, others, ROOT) + file_problems(
        ROOT, deny_words=_read_words(args.deny_file), allow_emails=emails, allow_files=files)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} item(s) to settle before publishing" if problems else "Ready to publish.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
