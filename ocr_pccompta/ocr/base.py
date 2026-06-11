"""
الفئة الأساسية لمحركات OCR — تحدد الواجهة الموحدة
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class RawExtractionResult:
    """الناتج الخام من أي محرك OCR قبل التحليل"""
    raw_text: str
    confidence: float
    structured_fields: dict       # حقول مُنظمة من Textract/Document AI
    tables: List[List[List[str]]] # قائمة جداول: [جدول[صف[خلية]]]
    page_count: int = 1
    engine_name: str = ""
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and bool(self.raw_text)


class BaseOCREngine(ABC):
    """الواجهة الموحدة لجميع محركات OCR"""

    @abstractmethod
    def extract(self, file_path: Path) -> RawExtractionResult:
        """استخراج النص والبنية من ملف صورة أو PDF"""

    @abstractmethod
    def is_available(self) -> bool:
        """التحقق من أن المحرك مُهيَّأ وجاهز للاستخدام"""

    def extract_batch(
        self, file_paths: List[Path]
    ) -> List[RawExtractionResult]:
        """معالجة دفعية — يمكن تجاوزها بتنفيذ متوازٍ في الفئات الفرعية"""
        return [self.extract(fp) for fp in file_paths]
