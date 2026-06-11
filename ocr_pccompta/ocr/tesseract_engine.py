"""
محرك Tesseract — للبيئات المحلية التي تشترط خصوصية البيانات الكاملة.
يستلزم معالجة مسبقة جيدة ويُنتج نتائج أقل دقة من الخيارات السحابية.
"""

from pathlib import Path

from .base import BaseOCREngine, RawExtractionResult
from .preprocessor import ImagePreprocessor


class TesseractEngine(BaseOCREngine):
    """
    يعمل محلياً بالكامل — لا بيانات تُرسل لخوادم خارجية.
    الدقة منخفضة نسبياً على الفواتير المعقدة؛ يُفضَّل مع Textract.
    """

    def __init__(
        self,
        tesseract_cmd: str = "/usr/bin/tesseract",
        lang: str = "ara+fra+eng",
        preprocess: bool = True,
    ) -> None:
        self.lang = lang
        self.preprocess = preprocess
        self._preprocessor = ImagePreprocessor()

        try:
            import pytesseract  # type: ignore
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            self._pytesseract = pytesseract
        except ImportError:
            self._pytesseract = None

    def is_available(self) -> bool:
        if self._pytesseract is None:
            return False
        try:
            self._pytesseract.get_tesseract_version()
            return True
        except Exception:  # pylint: disable=broad-except
            return False

    def extract(self, file_path: Path) -> RawExtractionResult:
        if not self.is_available():
            return RawExtractionResult(
                raw_text="",
                confidence=0.0,
                structured_fields={},
                tables=[],
                engine_name="tesseract",
                error="Tesseract غير متاح. تحقق من التثبيت.",
            )

        try:
            target = file_path
            if self.preprocess:
                target = self._preprocessor.process(file_path)

            # استخراج النص الكامل
            config = (
                f"--oem 3 --psm 6 -l {self.lang} "
                "--dpi 300 "
                "-c preserve_interword_spaces=1"
            )
            raw_text = self._pytesseract.image_to_string(
                str(target), config=config
            )

            # استخراج بيانات الثقة
            data = self._pytesseract.image_to_data(
                str(target),
                config=config,
                output_type=self._pytesseract.Output.DICT,
            )
            confidence = self._compute_confidence(data)

            # Tesseract لا يُنتج جداول منظمة — نُعيد قائمة فارغة
            return RawExtractionResult(
                raw_text=raw_text.strip(),
                confidence=confidence,
                structured_fields={},
                tables=[],
                engine_name="tesseract",
            )

        except Exception as exc:  # pylint: disable=broad-except
            return RawExtractionResult(
                raw_text="",
                confidence=0.0,
                structured_fields={},
                tables=[],
                engine_name="tesseract",
                error=str(exc),
            )

    def _compute_confidence(self, data: dict) -> float:
        scores = [
            c / 100
            for c in data.get("conf", [])
            if isinstance(c, (int, float)) and c >= 0
        ]
        return round(sum(scores) / len(scores), 3) if scores else 0.0
