"""Read duration, frame size, audio and fast start from an MP4/MOV file's boxes, without decoding."""
import re
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mp4Info:
    duration: float
    width: int
    height: int
    has_audio: bool
    faststart: bool  # moov before mdat, so a browser can start playing before the download finishes


def _boxes(buf: bytes, start: int = 0, end: int | None = None):
    end = len(buf) if end is None else end
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack(">I4s", buf[i:i + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", buf[i + 8:i + 16])[0]
            header = 16
        elif size == 0:
            size = end - i
        if size < header:
            return
        yield kind, i + header, min(i + size, end)
        i += size


def _find(buf: bytes, path: list[bytes], start: int = 0, end: int | None = None):
    for kind, s, e in _boxes(buf, start, end):
        if kind == path[0]:
            if len(path) == 1:
                yield s, e
            else:
                yield from _find(buf, path[1:], s, e)


def _times(buf: bytes, s: int) -> tuple[int, int]:
    # mvhd and mdhd share the layout of timescale and duration
    if buf[s] == 1:
        return struct.unpack(">IQ", buf[s + 20:s + 32])
    return struct.unpack(">II", buf[s + 12:s + 20])


def _top_level(f, total: int):
    """Yield (kind, payload_size) for each top-level box, leaving f at the start of its payload."""
    pos = 0
    while pos + 8 <= total:
        f.seek(pos)
        size, kind = struct.unpack(">I4s", f.read(8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            header = 16
        elif size == 0:
            size = total - pos
        if size < header:
            return
        yield kind, size - header
        pos += size


def metadata_text(path: Path) -> str:
    """Printable runs (8+ characters) in every top-level box except the media data, like `strings`."""
    path = Path(path)
    runs = []
    with path.open("rb") as f:
        for kind, size in _top_level(f, path.stat().st_size):
            if kind != b"mdat":
                runs += re.findall(rb"[\x20-\x7e]{8,}", f.read(size))
    return "\n".join(run.decode("ascii") for run in runs)


def probe(path: Path) -> Mp4Info:
    path = Path(path)
    order, moov = [], None
    with path.open("rb") as f:
        for kind, size in _top_level(f, path.stat().st_size):
            order.append(kind)
            if kind == b"moov":
                moov = f.read(size)
    if moov is None:
        raise ValueError(f"{path.name}: no moov box, not an MP4 file")

    duration = 0.0
    for s, _ in _find(moov, [b"mvhd"]):
        scale, length = _times(moov, s)
        duration = length / scale if scale else 0.0
    width = height = 0
    has_audio = False
    for ts, te in _find(moov, [b"trak"]):
        handler = b""
        for s, _ in _find(moov, [b"mdia", b"hdlr"], ts, te):
            handler = moov[s + 8:s + 12]
        if handler == b"soun":
            has_audio = True
        elif handler == b"vide" and not width:
            for _, e in _find(moov, [b"tkhd"], ts, te):
                w, h = struct.unpack(">II", moov[e - 8:e])
                width, height = w >> 16, h >> 16
    faststart = b"mdat" in order and order.index(b"moov") < order.index(b"mdat")
    return Mp4Info(duration, width, height, has_audio, faststart)
