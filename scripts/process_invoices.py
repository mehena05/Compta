#!/usr/bin/env python3
"""
واجهة سطر الأوامر لمعالجة الفواتير

الاستخدام:
    # معالجة ملف واحد
    python scripts/process_invoices.py invoice.pdf

    # معالجة مجلد كامل
    python scripts/process_invoices.py --dir data/input/

    # تحديد محرك OCR
    python scripts/process_invoices.py invoice.pdf --engine google_vision

    # عرض ملخص فقط
    python scripts/process_invoices.py invoice.pdf --dry-run
"""

import argparse
import sys
from pathlib import Path

# إضافة الجذر للمسار
sys.path.insert(0, str(Path(__file__).parent.parent))

from ocr_pccompta.config.settings import Settings
from ocr_pccompta.pipeline.document_pipeline import DocumentPipeline, PipelineStatus
from ocr_pccompta.utils.logging import configure_file_logging, get_logger

logger = get_logger("process_invoices")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="معالجة الفواتير وتصديرها إلى PCCompta",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "file", nargs="?", type=Path,
        help="مسار ملف الفاتورة (PDF أو صورة)",
    )
    parser.add_argument(
        "--dir", type=Path,
        help="معالجة جميع الملفات في مجلد",
    )
    parser.add_argument(
        "--engine",
        choices=["textract", "google_vision", "tesseract"],
        default=None,
        help="محرك OCR (الافتراضي: من الإعدادات)",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        help="مجلد حفظ ملفات Excel",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="استخراج وتحقق فقط — لا تصدير لـ PCCompta",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="تفاصيل إضافية",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.file and not args.dir:
        print("خطأ: يجب تحديد ملف أو مجلد للمعالجة.")
        print("استخدم --help لرؤية الخيارات المتاحة.")
        return 1

    # تحميل وتعديل الإعدادات
    settings = Settings.from_env()
    if args.engine:
        settings.ocr_engine = args.engine
    if args.output_dir:
        settings.output_dir = args.output_dir
    settings.ensure_dirs()

    configure_file_logging(settings.log_file, settings.log_level)

    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    # إنشاء Pipeline
    pipeline = DocumentPipeline.from_settings(settings)

    # تحديد الملفات للمعالجة
    if args.dir:
        results = pipeline.process_directory(args.dir)
    else:
        results = [pipeline.process(args.file)]

    # عرض النتائج
    success = warning = failed = 0
    for result in results:
        if result.status == PipelineStatus.SUCCESS:
            success += 1
            icon = "✅"
        elif result.status == PipelineStatus.NEEDS_REVIEW:
            warning += 1
            icon = "⚠️ "
        else:
            failed += 1
            icon = "❌"

        print(f"\n{icon} {result.summary()}")
        print(f"   الوقت: {result.processing_time_ms:.0f} مللي ثانية")

    # ملخص نهائي
    total = len(results)
    print(f"\n{'─' * 50}")
    print(
        f"الملخص: {total} مستند | "
        f"✅ {success} نجح | "
        f"⚠️  {warning} يتطلب مراجعة | "
        f"❌ {failed} فشل"
    )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
