"""OCR fallback — EasyOCR (ko/en) → RapidOCR → Tesseract → no-op.

도메인 무관. 이미지 위 글자를 읽어 ContentBlock으로 만든다.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OcrLine:
    text: str
    # image-pixel bbox (x0,y0,x1,y1)
    bbox: tuple[float, float, float, float]
    confidence: float


@dataclass
class OcrResult:
    text: str
    confidence: float
    engine: str
    available: bool
    lines: list[OcrLine] = field(default_factory=list)


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


@lru_cache(maxsize=1)
def _easyocr_reader():
    import easyocr

    # GPU if available; EasyOCR picks automatically when gpu=True fails
    try:
        return easyocr.Reader(["ko", "en"], gpu=True, verbose=False)
    except Exception:
        return easyocr.Reader(["ko", "en"], gpu=False, verbose=False)


def ocr_image(image_path: str | Path, *, lang: str = "kor+eng") -> OcrResult:
    if not settings.ocr_enabled:
        return OcrResult(text="", confidence=0.0, engine="disabled", available=False)

    path = Path(image_path)
    if not path.is_file():
        return OcrResult(text="", confidence=0.0, engine="none", available=False)

    # 1) EasyOCR — best Korean for presentation PDFs
    try:
        return _ocr_easyocr(path)
    except Exception as e:
        logger.warning("EasyOCR failed: %s", e)

    # 2) RapidOCR (latin-heavy; weak Korean)
    try:
        return _ocr_rapid(path)
    except Exception as e:
        logger.warning("RapidOCR failed: %s", e)

    # 3) Tesseract if installed
    if tesseract_available():
        return _ocr_tesseract(path, lang=lang)

    return OcrResult(text="", confidence=0.0, engine="none", available=False)


def image_bbox_to_page(
    bbox: tuple[float, float, float, float],
    *,
    dpi: int,
) -> tuple[float, float, float, float]:
    """Convert rendered PNG pixel bbox → PDF points (72 dpi base)."""
    scale = 72.0 / float(dpi or 72)
    x0, y0, x1, y1 = bbox
    return (x0 * scale, y0 * scale, x1 * scale, y1 * scale)


def _ocr_easyocr(path: Path) -> OcrResult:
    reader = _easyocr_reader()
    raw = reader.readtext(str(path), detail=1, paragraph=False)
    lines: list[OcrLine] = []
    confs: list[float] = []
    for item in raw or []:
        box, text, conf = item[0], item[1], float(item[2])
        text = (text or "").strip()
        if not text:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        lines.append(
            OcrLine(
                text=text,
                bbox=(min(xs), min(ys), max(xs), max(ys)),
                confidence=conf,
            )
        )
        confs.append(conf)
    joined = "\n".join(ln.text for ln in lines)
    avg = sum(confs) / len(confs) if confs else 0.0
    return OcrResult(
        text=joined,
        confidence=avg,
        engine="easyocr",
        available=True,
        lines=lines,
    )


def _ocr_rapid(path: Path) -> OcrResult:
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    result, _ = engine(str(path))
    lines: list[OcrLine] = []
    confs: list[float] = []
    for row in result or []:
        box, text, conf = row
        text = (text or "").strip()
        if not text:
            continue
        try:
            c = float(conf)
        except (TypeError, ValueError):
            c = 0.5
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        lines.append(
            OcrLine(text=text, bbox=(min(xs), min(ys), max(xs), max(ys)), confidence=c)
        )
        confs.append(c)
    joined = "\n".join(ln.text for ln in lines)
    avg = sum(confs) / len(confs) if confs else 0.0
    return OcrResult(
        text=joined,
        confidence=avg,
        engine="rapidocr",
        available=bool(lines),
        lines=lines,
    )


def _ocr_tesseract(path: Path, *, lang: str) -> OcrResult:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return OcrResult(text="", confidence=0.0, engine="none", available=False)

    img = Image.open(path)
    try:
        data = pytesseract.image_to_data(
            img, lang=lang, output_type=pytesseract.Output.DICT
        )
    except Exception:
        try:
            data = pytesseract.image_to_data(
                img, lang="eng", output_type=pytesseract.Output.DICT
            )
        except Exception:
            return OcrResult(text="", confidence=0.0, engine="tesseract", available=False)

    lines: list[OcrLine] = []
    confs: list[float] = []
    n = len(data.get("text") or [])
    for i in range(n):
        t = (data["text"][i] or "").strip()
        if not t:
            continue
        try:
            c = float(data["conf"][i])
        except (TypeError, ValueError):
            c = -1
        if c < 0:
            continue
        x, y, w, h = (
            float(data["left"][i]),
            float(data["top"][i]),
            float(data["width"][i]),
            float(data["height"][i]),
        )
        lines.append(
            OcrLine(text=t, bbox=(x, y, x + w, y + h), confidence=c / 100.0)
        )
        confs.append(c / 100.0)
    joined = " ".join(ln.text for ln in lines)
    avg = sum(confs) / len(confs) if confs else 0.0
    return OcrResult(
        text=joined,
        confidence=avg,
        engine="tesseract",
        available=True,
        lines=lines,
    )


def correct_ocr_lines(
    lines: list[OcrLine], lexicon: list[str], *, max_distance: int = 2
) -> list[OcrLine]:
    """Correct OCR labels toward high-confidence page lexicon (no domain dict)."""
    lex: list[str] = []
    for t in lexicon:
        if not t:
            continue
        for part in re.split(r"[\n|/·\-–—]+", t):
            p = _norm_lex(part)
            if 1 < len(p) <= 36:
                lex.append(p)
    lex = list(dict.fromkeys(lex))
    if not lex:
        return lines
    out: list[OcrLine] = []
    for ln in lines:
        fixed = _best_lex_match(ln.text, lex, max_distance=max_distance)
        if fixed and fixed != ln.text:
            out.append(
                OcrLine(text=fixed, bbox=ln.bbox, confidence=min(1.0, ln.confidence + 0.05))
            )
        else:
            out.append(ln)
    return out


def _norm_lex(s: str) -> str:
    return " ".join((s or "").split()).strip()


def _best_lex_match(text: str, lexicon: list[str], *, max_distance: int) -> str | None:
    t = _norm_lex(text)
    if not t:
        return None
    tn = _compact(t)
    best = None
    best_d = max_distance + 1
    for cand in lexicon:
        cn = _compact(cand)
        if not cn:
            continue
        if tn == cn:
            return cand
        # containment for OCR fragment vs full label
        if len(tn) >= 3 and (tn in cn or cn in tn) and abs(len(tn) - len(cn)) <= 4:
            d = abs(len(tn) - len(cn))
            if d < best_d:
                best_d = d
                best = cand
            continue
        d = _levenshtein(tn, cn)
        if d < best_d and d <= max_distance and abs(len(tn) - len(cn)) <= max_distance + 1:
            best_d = d
            best = cand
    return best


def _compact(s: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", s).lower()


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for i, cb in enumerate(b, 1):
        cur = [i]
        for j, ca in enumerate(a, 1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]
