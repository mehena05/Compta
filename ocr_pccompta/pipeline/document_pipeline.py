"""
Pipeline التكاملي الكامل — يربط جميع المراحل من الملف إلى PCCompta
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from ..config.settings import Settings, get_settings
from ..exporters.excel_generator import PCComptaExcelGenerator
from ..exporters.pccompta_exporter import PCComptaExporter
from ..extractors.invoice_extractor import InvoiceDataExtractor
from ..models.invoice import InvoiceData
from ..ocr.base import BaseOCREngine
from ..ocr.preprocessor import ImagePreprocessor
from ..utils.logging import get_logger
from ..validators.accounting_validator import AccountingValidator, ValidationResult

logger = get_logger(__name__)


class PipelineStatus(Enum):
    SUCCESS = "success"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


@dataclass
class PipelineResult:
    status: PipelineStatus
    invoice: Optional[InvoiceData] = None
    validation: Optional[ValidationResult] = None
    excel_path: Optional[Path] = None
    csv_path: Optional[Path] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.status != PipelineStatus.FAILED

    def summary(self) -> str:
        lines = [f"الحالة: {self.status.value}"]
        if self.invoice:
            lines.append(
                f"فاتورة: {self.invoice.invoice_number} "
                f"| الثقة: {self.invoice.confidence_score:.0%}"
            )
        if self.excel_path:
            lines.append(f"Excel: {self.excel_path}")
        if self.csv_path:
            lines.append(f"CSV PCCompta: {self.csv_path}")
        if self.error:
            lines.append(f"خطأ: {self.error}")
        if self.validation:
            lines.append(self.validation.summary())
        return "\n".join(lines)


class DocumentPipeline:
    """
    يُنفّذ سلسلة المعالجة الكاملة:

        ملف → معالجة مسبقة → OCR → استخراج → تحقق → Excel → PCCompta

    الاستخدام::

        pipeline = DocumentPipeline.from_settings()
        result = pipeline.process(Path("invoice.pdf"))
        print(result.summary())
    """

    def __init__(
        self,
        ocr_engine: BaseOCREngine,
        settings: Optional[Settings] = None,
    ) -> None:
        self.ocr_engine = ocr_engine
        self.settings = settings or get_settings()
        self._preprocessor = ImagePreprocessor()
        self._extractor = InvoiceDataExtractor()
        self._validator = AccountingValidator()
        self._excel_gen = PCComptaExcelGenerator()
        self._pccompta_exp = PCComptaExporter(
            import_dir=self.settings.pccompta_import_dir,
            processed_dir=self.settings.processed_dir,
        )

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DocumentPipeline":
        """مصنع يختار محرك OCR تلقائياً بناءً على الإعدادات"""
        s = settings or get_settings()
        engine = cls._build_engine(s)
        return cls(ocr_engine=engine, settings=s)

    @staticmethod
    def _build_engine(s: Settings) -> BaseOCREngine:
        if s.ocr_engine == "textract":
            from ..ocr.textract_engine import TextractEngine
            return TextractEngine(
                region=s.aws_region,
                s3_bucket=s.aws_s3_bucket,
                aws_access_key_id=s.aws_access_key_id,
                aws_secret_access_key=s.aws_secret_access_key,
            )
        if s.ocr_engine == "google_vision":
            from ..ocr.google_vision_engine import GoogleVisionEngine
            return GoogleVisionEngine(
                project_id=s.google_project_id,
                processor_id=s.google_processor_id,
                credentials_path=s.google_credentials_path,
            )
        from ..ocr.tesseract_engine import TesseractEngine
        return TesseractEngine(
            tesseract_cmd=s.tesseract_cmd,
            lang=s.tesseract_lang,
        )

    # ------------------------------------------------------------------
    # المعالجة الرئيسية
    # ------------------------------------------------------------------

    def process(self, file_path: Path) -> PipelineResult:
        """معالجة مستند واحد — المسار الكامل"""
        import time
        start = time.time()

        try:
            result = self._run_pipeline(file_path)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Pipeline فشل للملف %s: %s", file_path, exc)
            result = PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"{exc}\n{traceback.format_exc()}",
            )

        result.processing_time_ms = (time.time() - start) * 1000
        logger.info(
            "معالجة %s: %s (%.0f ms)",
            file_path.name,
            result.status.value,
            result.processing_time_ms,
        )
        return result

    def process_batch(self, file_paths: List[Path]) -> List[PipelineResult]:
        results = []
        for fp in file_paths:
            logger.info("معالجة: %s", fp.name)
            results.append(self.process(fp))
        return results

    def process_directory(
        self, directory: Path, extensions: tuple = (".pdf", ".png", ".jpg", ".tiff")
    ) -> List[PipelineResult]:
        files = [
            f for f in directory.iterdir()
            if f.suffix.lower() in extensions
        ]
        logger.info("وُجد %d ملف للمعالجة في %s", len(files), directory)
        return self.process_batch(files)

    # ------------------------------------------------------------------
    # مراحل Pipeline الداخلية
    # ------------------------------------------------------------------

    def _run_pipeline(self, file_path: Path) -> PipelineResult:

        # --- المرحلة 1: معالجة مسبقة ---
        logger.debug("المرحلة 1: معالجة مسبقة — %s", file_path.name)
        processed_path = self._preprocess(file_path)

        # --- المرحلة 2: OCR ---
        logger.debug("المرحلة 2: OCR")
        ocr_result = self.ocr_engine.extract(processed_path)
        if not ocr_result.succeeded:
            self._move_to_failed(file_path)
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"OCR فشل: {ocr_result.error}",
            )

        # --- المرحلة 3: استخراج البيانات ---
        logger.debug("المرحلة 3: استخراج البيانات")
        invoice = self._extractor.extract(
            ocr_result, source_file=str(file_path)
        )
        self._assign_pccompta_accounts(invoice)

        # --- المرحلة 4: التحقق ---
        logger.debug("المرحلة 4: التحقق المحاسبي")
        validation = self._validator.validate(invoice)
        invoice.is_validated = True

        # --- المرحلة 5: توليد Excel ---
        logger.debug("المرحلة 5: توليد Excel")
        excel_path = self._generate_excel(invoice, validation, file_path)
        invoice.is_exported_excel = True

        # --- المرحلة 6: تقرير الحالة ---
        needs_review = (
            invoice.needs_review
            or invoice.confidence_score < self.settings.confidence_threshold_auto
            or validation.has_blocking_errors()
        )

        # --- المرحلة 7: استيراد PCCompta (فقط إذا لا تحتاج مراجعة) ---
        csv_path: Optional[Path] = None
        if not needs_review and not validation.has_blocking_errors():
            try:
                csv_path = self._pccompta_exp.export(invoice)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("تصدير PCCompta فشل: %s", exc)
                needs_review = True

        # نقل الملف الأصلي للمجلد المناسب
        if not needs_review and csv_path:
            self._move_to_processed(file_path)

        status = (
            PipelineStatus.NEEDS_REVIEW
            if needs_review
            else PipelineStatus.SUCCESS
        )

        return PipelineResult(
            status=status,
            invoice=invoice,
            validation=validation,
            excel_path=excel_path,
            csv_path=csv_path,
        )

    # ------------------------------------------------------------------
    # دوال مساعدة
    # ------------------------------------------------------------------

    def _preprocess(self, file_path: Path) -> Path:
        """معالجة مسبقة للصور؛ ترجع الملف الأصلي إذا كان PDF"""
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return file_path
        try:
            return self._preprocessor.process(file_path)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "تعذّرت المعالجة المسبقة، يُستخدم الملف الأصلي: %s", exc
            )
            return file_path

    def _generate_excel(
        self,
        invoice: InvoiceData,
        validation: ValidationResult,
        source_path: Path,
    ) -> Path:
        out_name = f"{source_path.stem}_ocr_{invoice.document_id[:8]}.xlsx"
        out_path = self.settings.output_dir / out_name
        return self._excel_gen.generate(invoice, out_path, validation)

    def _assign_pccompta_accounts(self, invoice: InvoiceData) -> None:
        """تعيين أرقام الحسابات المحاسبية الافتراضية"""
        if not invoice.pccompta_account_purchase:
            invoice.pccompta_account_purchase = \
                self.settings.account_purchases
        if not invoice.pccompta_account_tva:
            invoice.pccompta_account_tva = \
                self.settings.account_tva_deductible
        if not invoice.pccompta_journal:
            invoice.pccompta_journal = self.settings.journal_purchases

    def _move_to_processed(self, file_path: Path) -> None:
        dest = self.settings.processed_dir / file_path.name
        try:
            import shutil
            shutil.copy2(str(file_path), str(dest))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("تعذّر نسخ الملف للأرشيف: %s", exc)

    def _move_to_failed(self, file_path: Path) -> None:
        dest = self.settings.failed_dir / file_path.name
        try:
            import shutil
            shutil.copy2(str(file_path), str(dest))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("تعذّر نسخ الملف لمجلد الفشل: %s", exc)
