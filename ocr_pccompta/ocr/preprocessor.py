"""
معالجة الصور المسبقة لتحسين دقة OCR
"""

import math
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image


class ImagePreprocessor:
    """
    سلسلة معالجة الصور قبل إرسالها لمحرك OCR.
    مهمة بشكل خاص مع Tesseract وللصور ذات الجودة المنخفضة.
    """

    MIN_DPI = 300

    def process(
        self,
        image_path: Path,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        تطبيق سلسلة المعالجة الكاملة وحفظ الناتج.
        تُعيد مسار الصورة المعالجة.
        """
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"تعذّر تحميل الصورة: {image_path}")

        img = self._upscale_if_needed(img)
        img = self._to_grayscale(img)
        img = self._enhance_contrast(img)
        img = self._denoise(img)
        img = self._binarize(img)
        img = self._deskew(img)
        img = self._remove_borders(img)

        dest = output_path or image_path.with_suffix(".processed.png")
        cv2.imwrite(str(dest), img)
        return dest

    # ------------------------------------------------------------------
    # خطوات المعالجة الفردية
    # ------------------------------------------------------------------

    def _upscale_if_needed(
        self, img: np.ndarray, target_height: int = 2400
    ) -> np.ndarray:
        """تكبير الصورة إذا كانت صغيرة جداً"""
        h, w = img.shape[:2]
        if h < target_height:
            scale = target_height / h
            img = cv2.resize(
                img, None, fx=scale, fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )
        return img

    def _to_grayscale(self, img: np.ndarray) -> np.ndarray:
        if len(img.shape) == 3:
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """CLAHE — تحسين التباين المحلي"""
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(img)

    def _denoise(self, img: np.ndarray) -> np.ndarray:
        return cv2.fastNlMeansDenoising(img, h=10)

    def _binarize(self, img: np.ndarray) -> np.ndarray:
        """ثنائية Otsu — تحويل للأبيض والأسود"""
        _, binary = cv2.threshold(
            img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        return binary

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """تصحيح انحراف المستند"""
        angle = self._detect_skew_angle(img)
        if abs(angle) < 0.5:
            return img
        h, w = img.shape
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _detect_skew_angle(self, img: np.ndarray) -> float:
        """حساب زاوية انحراف المستند باستخدام تحويل Hough"""
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=200)
        if lines is None:
            return 0.0
        angles = []
        for line in lines[:20]:
            rho, theta = line[0]
            angle_deg = math.degrees(theta) - 90
            if abs(angle_deg) < 45:
                angles.append(angle_deg)
        return float(np.median(angles)) if angles else 0.0

    def _remove_borders(self, img: np.ndarray) -> np.ndarray:
        """إزالة الحواف السوداء الناتجة عن المسح الضوئي"""
        contours, _ = cv2.findContours(
            img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return img
        x, y, w, h = cv2.boundingRect(
            max(contours, key=cv2.contourArea)
        )
        return img[y: y + h, x: x + w]

    def pdf_to_images(
        self, pdf_path: Path, output_dir: Path, dpi: int = 300
    ) -> list[Path]:
        """تحويل PDF إلى صور PNG (يتطلب pdf2image)"""
        try:
            from pdf2image import convert_from_path  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "pdf2image مطلوب لمعالجة PDF: pip install pdf2image"
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        pages = convert_from_path(str(pdf_path), dpi=dpi)
        paths: list[Path] = []
        for i, page in enumerate(pages):
            out = output_dir / f"{pdf_path.stem}_page_{i+1:03d}.png"
            page.save(str(out), "PNG")
            paths.append(out)
        return paths
