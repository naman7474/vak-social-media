from __future__ import annotations

import io

import numpy as np
from PIL import Image


class SareeValidator:
    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold

    def _to_gray(self, image_bytes: bytes, size: tuple[int, int] = (256, 256)) -> np.ndarray:
        image = Image.open(io.BytesIO(image_bytes)).convert("L").resize(size)
        return np.asarray(image, dtype=np.float32)

    def _ssim(self, x: np.ndarray, y: np.ndarray) -> float:
        c1 = 6.5025
        c2 = 58.5225

        x_mean = x.mean()
        y_mean = y.mean()
        x_var = x.var()
        y_var = y.var()
        covariance = ((x - x_mean) * (y - y_mean)).mean()

        numerator = (2 * x_mean * y_mean + c1) * (2 * covariance + c2)
        denominator = (x_mean**2 + y_mean**2 + c1) * (x_var + y_var + c2)
        if denominator == 0:
            return 0.0
        return float(numerator / denominator)

    def verify_preserved(self, original_bytes: bytes, generated_bytes: bytes) -> tuple[bool, float]:
        orig = self._to_gray(original_bytes)
        gen = self._to_gray(generated_bytes)
        score = self._ssim(orig, gen)
        return score >= self.threshold, score
