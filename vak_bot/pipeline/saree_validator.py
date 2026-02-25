from __future__ import annotations

import io

import numpy as np
from PIL import Image

try:
    import lpips
    import torch
    _LPIPS_AVAILABLE = True
except ImportError:
    _LPIPS_AVAILABLE = False


class SareeValidator:
    def __init__(self, threshold: float = 0.6, lpips_threshold: float = 0.15) -> None:
        self.threshold = threshold
        self.lpips_threshold = lpips_threshold
        self._lpips_fn = None
        if _LPIPS_AVAILABLE:
            self._lpips_fn = lpips.LPIPS(net='alex')

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

    def verify_preserved(self, original_bytes: bytes, generated_bytes: bytes) -> tuple[bool, float, float | None]:
        orig_gray = self._to_gray(original_bytes)
        gen_gray = self._to_gray(generated_bytes)
        ssim_score = self._ssim(orig_gray, gen_gray)
        
        lpips_score = None
        if self._lpips_fn:
            # LPIPS needs RGB tensors in [-1, 1]
            orig_rgb = np.array(Image.open(io.BytesIO(original_bytes)).convert("RGB")) / 255.0
            gen_rgb = np.array(Image.open(io.BytesIO(generated_bytes)).convert("RGB"))
            
            # Resize gen to match orig
            gen_pil = Image.fromarray((gen_rgb * 255).astype(np.uint8)).resize((orig_rgb.shape[1], orig_rgb.shape[0]))
            gen_rgb = np.array(gen_pil) / 255.0
            
            orig_t = torch.from_numpy(orig_rgb).permute(2, 0, 1).unsqueeze(0).float() * 2 - 1
            gen_t = torch.from_numpy(gen_rgb).permute(2, 0, 1).unsqueeze(0).float() * 2 - 1
            
            lpips_score = self._lpips_fn(orig_t, gen_t).item()

        # The validity is determined by SSIM primarily. LPIPS is for warning checking in orchestrator.
        # We also treat the failure as a warning only per user request.
        is_valid = ssim_score >= self.threshold
        
        return is_valid, ssim_score, lpips_score
