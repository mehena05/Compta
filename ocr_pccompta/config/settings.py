"""
إعدادات النظام المركزية — تُحمَّل من متغيرات البيئة أو ملف .env
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class Settings:
    # === محرك OCR ===
    # الخيارات: "textract" | "google_vision" | "tesseract"
    ocr_engine: str = "textract"

    # Amazon Textract
    aws_region: str = "eu-west-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = ""

    # Google Vision / Document AI
    google_credentials_path: str = ""
    google_project_id: str = ""
    google_processor_id: str = ""  # Document AI processor ID

    # Tesseract
    tesseract_cmd: str = "/usr/bin/tesseract"
    tesseract_lang: str = "ara+fra+eng"

    # === مسارات الملفات ===
    input_dir: Path = Path("data/input")
    output_dir: Path = Path("data/output")
    excel_template_dir: Path = Path("data/templates")
    pccompta_import_dir: Path = Path("C:/PCCompta/Import")
    processed_dir: Path = Path("data/processed")
    failed_dir: Path = Path("data/failed")

    # === إعدادات التحقق ===
    # نسبة ثقة OCR — ما دونها يُوضع للمراجعة اليدوية
    confidence_threshold_auto: float = 0.95
    confidence_threshold_review: float = 0.60

    # الفارق المقبول في التحقق الحسابي (بالوحدة المحلية)
    amount_tolerance: float = 0.02

    # نسب TVA المقبولة (تونس)
    valid_tva_rates: list = field(default_factory=lambda: [0, 7, 13, 19])

    # === إعدادات Excel ===
    excel_sheet_main: str = "بيانات الفاتورة"
    excel_sheet_items: str = "بنود التفصيل"
    excel_sheet_pccompta: str = "استيراد PCCompta"
    excel_sheet_log: str = "سجل المعالجة"

    # === إعدادات PCCompta ===
    # رموز دفاتر اليومية
    journal_purchases: str = "ACH"
    journal_sales: str = "VTE"
    journal_cash: str = "CAI"

    # حسابات PCCompta الافتراضية
    account_purchases: str = "607000"
    account_tva_deductible: str = "445660"
    account_tva_collected: str = "445710"

    # === إعدادات التسجيل (Logging) ===
    log_level: str = "INFO"
    log_file: Path = Path("logs/ocr_pccompta.log")

    @classmethod
    def from_env(cls) -> "Settings":
        """تحميل الإعدادات من متغيرات البيئة"""
        return cls(
            ocr_engine=os.getenv("OCR_ENGINE", "textract"),
            aws_region=os.getenv("AWS_REGION", "eu-west-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            aws_s3_bucket=os.getenv("AWS_S3_BUCKET", ""),
            google_credentials_path=os.getenv(
                "GOOGLE_APPLICATION_CREDENTIALS", ""),
            google_project_id=os.getenv("GOOGLE_PROJECT_ID", ""),
            google_processor_id=os.getenv("GOOGLE_PROCESSOR_ID", ""),
            tesseract_cmd=os.getenv(
                "TESSERACT_CMD", "/usr/bin/tesseract"),
            tesseract_lang=os.getenv(
                "TESSERACT_LANG", "ara+fra+eng"),
            input_dir=Path(os.getenv("INPUT_DIR", "data/input")),
            output_dir=Path(os.getenv("OUTPUT_DIR", "data/output")),
            pccompta_import_dir=Path(
                os.getenv("PCCOMPTA_IMPORT_DIR", "C:/PCCompta/Import")),
            confidence_threshold_auto=float(
                os.getenv("CONFIDENCE_THRESHOLD_AUTO", "0.95")),
            confidence_threshold_review=float(
                os.getenv("CONFIDENCE_THRESHOLD_REVIEW", "0.60")),
            amount_tolerance=float(
                os.getenv("AMOUNT_TOLERANCE", "0.02")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

    def ensure_dirs(self) -> None:
        """إنشاء المجلدات الضرورية إن لم تكن موجودة"""
        for d in [
            self.input_dir,
            self.output_dir,
            self.excel_template_dir,
            self.processed_dir,
            self.failed_dir,
            self.log_file.parent,
        ]:
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """إرجاع نسخة وحيدة من الإعدادات (Singleton)"""
    settings = Settings.from_env()
    settings.ensure_dirs()
    return settings
