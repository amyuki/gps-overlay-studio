"""Low-level OpenCV drawing helpers."""

from typing import Tuple

import cv2
import numpy as np


def alpha_rect(
    img: np.ndarray,
    x: int, y: int, w: int, h: int,
    color: Tuple[int, int, int],
    alpha: int,
) -> None:
    """Draw a semi-transparent filled rectangle onto img (in-place)."""
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
    cv2.addWeighted(overlay, alpha / 255, img, 1 - alpha / 255, 0, img)


def put_text(
    img: np.ndarray,
    text: str,
    x: int, y: int,
    size: float = 0.55,
    color: Tuple[int, int, int] = (230, 235, 245),
    thick: int = 1,
    bold: bool = False,
) -> None:
    """Render text with a drop shadow."""
    font = cv2.FONT_HERSHEY_DUPLEX if bold else cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, text, (x + 1, y + 1), font, size, (0, 0, 0), thick + 1, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), font, size, color, thick, cv2.LINE_AA)


def text_size(text: str, size: float = 0.55, thick: int = 1) -> Tuple[int, int]:
    """Return (width, height) of the rendered text."""
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, size, thick)
    return w, h
