import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter, ImageOps
import pytesseract
from pytesseract import Output


logger = logging.getLogger(__name__)

OCR_PREPROCESS_VERSION = "v1"


@dataclass(frozen=True)
class OcrConfig:
    langs: str
    psm: int
    oem: int
    dpi: int
    max_workers: int
    page_timeout_seconds: float
    pdf_text_min_chars: int
    cache_dir: str
    cache_enabled: bool

    def tesseract_config(self) -> str:
        return f"--psm {self.psm} --oem {self.oem}"

    def config_hash(self) -> str:
        payload = {
            "langs": self.langs,
            "psm": self.psm,
            "oem": self.oem,
            "dpi": self.dpi,
            "preprocess": OCR_PREPROCESS_VERSION,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return digest


def get_ocr_config() -> OcrConfig:
    langs = os.getenv("OCR_LANGS", "eng")
    psm = _coerce_int(os.getenv("OCR_PSM", "6"), 6)
    oem = _coerce_int(os.getenv("OCR_OEM", "3"), 3)
    dpi = _clamp_dpi(_coerce_int(os.getenv("OCR_DPI", "300"), 300))
    max_workers = max(1, _coerce_int(os.getenv("OCR_MAX_WORKERS", "2"), 2))
    page_timeout = _coerce_float(
        os.getenv("OCR_PAGE_TIMEOUT_SECONDS", "20"), 20.0
    )
    pdf_text_min_chars = max(
        0, _coerce_int(os.getenv("OCR_PDF_TEXT_MIN_CHARS", "40"), 40)
    )
    cache_dir = os.getenv(
        "OCR_CACHE_DIR",
        os.path.join(os.getcwd(), "backend", "ocr_cache"),
    )
    cache_enabled = os.getenv("OCR_CACHE_ENABLED", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    return OcrConfig(
        langs=langs,
        psm=psm,
        oem=oem,
        dpi=dpi,
        max_workers=max_workers,
        page_timeout_seconds=page_timeout,
        pdf_text_min_chars=pdf_text_min_chars,
        cache_dir=cache_dir,
        cache_enabled=cache_enabled,
    )


def preprocess_image(image: Image.Image, config: OcrConfig) -> Image.Image:
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")

    image = _normalize_dpi(image, config.dpi)
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    image = _adaptive_threshold(image)
    return image


def ocr_image(image: Image.Image, config: OcrConfig) -> Tuple[str, Optional[float]]:
    data = pytesseract.image_to_data(
        image,
        lang=config.langs,
        config=config.tesseract_config(),
        output_type=Output.DICT,
    )
    text = _data_to_text(data)
    confidence = _data_to_confidence(data)
    return text.strip(), confidence


def text_density(text: str) -> int:
    if not text:
        return 0
    return len("".join(text.split()))


def build_cache_key(
    file_id: str, revision_id: str, page_number: int, config_hash: str
) -> str:
    raw = f"{file_id}:{revision_id}:{page_number}:{config_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cached_ocr(
    cache_dir: str, cache_key: str
) -> Optional[Tuple[str, Optional[float]]]:
    cache_path = os.path.join(cache_dir, f"{cache_key}.json")
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r") as handle:
            payload = json.load(handle)
        return payload.get("text", ""), payload.get("confidence")
    except Exception as exc:
        logger.warning("Failed reading OCR cache %s: %s", cache_path, exc)
        return None


def store_cached_ocr(
    cache_dir: str,
    cache_key: str,
    text: str,
    confidence: Optional[float],
) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{cache_key}.json")
    payload = {"text": text, "confidence": confidence}
    try:
        with open(cache_path, "w") as handle:
            json.dump(payload, handle)
    except Exception as exc:
        logger.warning("Failed writing OCR cache %s: %s", cache_path, exc)


def _normalize_dpi(image: Image.Image, target_dpi: int) -> Image.Image:
    if target_dpi <= 0:
        return image
    dpi = image.info.get("dpi")
    if not dpi:
        return image
    if isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
        current_dpi = (dpi[0] + dpi[1]) / 2 if dpi[0] and dpi[1] else dpi[0] or dpi[1]
    else:
        current_dpi = dpi
    if not current_dpi:
        return image
    scale = target_dpi / float(current_dpi)
    if abs(scale - 1.0) < 0.05:
        return image
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    resized.info["dpi"] = (target_dpi, target_dpi)
    return resized


def _adaptive_threshold(image: Image.Image, radius: int = 8, offset: int = 10) -> Image.Image:
    if image.mode != "L":
        image = image.convert("L")
    blurred = image.filter(ImageFilter.BoxBlur(radius))
    img_arr = np.array(image, dtype=np.int16)
    blur_arr = np.array(blurred, dtype=np.int16)
    threshold = blur_arr - offset
    binary = (img_arr > threshold).astype(np.uint8) * 255
    return Image.fromarray(binary, mode="L")


def _data_to_text(data: Dict[str, Any]) -> str:
    words = data.get("text") or []
    line_nums = data.get("line_num") or []
    par_nums = data.get("par_num") or []
    block_nums = data.get("block_num") or []
    if not words:
        return ""
    lines: Dict[Tuple[int, int, int], list[str]] = {}
    for idx, word in enumerate(words):
        if not word or not str(word).strip():
            continue
        key = (
            _safe_int(block_nums, idx),
            _safe_int(par_nums, idx),
            _safe_int(line_nums, idx),
        )
        lines.setdefault(key, []).append(str(word))
    ordered_keys = sorted(lines.keys())
    text_lines = [" ".join(lines[key]) for key in ordered_keys if lines.get(key)]
    return "\n".join(text_lines)


def _data_to_confidence(data: Dict[str, Any]) -> Optional[float]:
    confs = data.get("conf") or []
    values = []
    for entry in confs:
        try:
            value = float(entry)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            values.append(value)
    if not values:
        return None
    return sum(values) / (len(values) * 100.0)


def _safe_int(items: list, idx: int) -> int:
    if idx >= len(items):
        return 0
    try:
        return int(items[idx])
    except (TypeError, ValueError):
        return 0


def _clamp_dpi(value: int) -> int:
    if value < 200:
        return 200
    if value > 300:
        return 300
    return value


def _coerce_int(raw: Optional[str], fallback: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _coerce_float(raw: Optional[str], fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback
