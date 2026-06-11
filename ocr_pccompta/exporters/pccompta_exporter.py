"""
مُصدِّر PCCompta — يحوّل InvoiceData إلى ملفات CSV بصيغة PCCompta
"""

import csv
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..models.invoice import InvoiceData
from ..utils.logging import get_logger

logger = get_logger(__name__)


class PCComptaExporter:
    """
    يُنتج ملف CSV بتنسيق استيراد PCCompta المعياري ويضعه
    في مجلد الاستيراد لكي يلتقطه البرنامج.

    صيغة الأسطر:
        JOURNAL;DATE;PIECE;COMPTE;LIBELLE;DEBIT;CREDIT
    """

    CSV_HEADER = ["JOURNAL", "DATE", "PIECE", "COMPTE", "LIBELLE",
                  "DEBIT", "CREDIT"]
    CSV_DELIMITER = ";"
    CSV_ENCODING = "utf-8-sig"  # BOM لدعم Excel العربي

    def __init__(
        self,
        import_dir: Path,
        processed_dir: Optional[Path] = None,
    ) -> None:
        self.import_dir = Path(import_dir)
        self.processed_dir = Path(
            processed_dir or import_dir / "processed"
        )
        self.import_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def export(self, invoice: InvoiceData) -> Path:
        """
        يُنتج ملف CSV ويضعه في مجلد الاستيراد.
        يُعيد مسار الملف المُنشأ.
        """
        rows = self._build_journal_rows(invoice)
        if not rows:
            raise ValueError(
                f"لا توجد بيانات كافية لتصدير الفاتورة "
                f"{invoice.invoice_number}"
            )

        filename = self._build_filename(invoice)
        csv_path = self.import_dir / filename

        with open(csv_path, "w", newline="", encoding=self.CSV_ENCODING) as f:
            writer = csv.writer(f, delimiter=self.CSV_DELIMITER)
            writer.writerow(self.CSV_HEADER)
            writer.writerows(rows)

        logger.info("تم تصدير الفاتورة %s → %s", invoice.invoice_number, csv_path)
        invoice.is_imported_pccompta = True
        return csv_path

    def export_batch(self, invoices: List[InvoiceData]) -> List[Path]:
        paths = []
        for invoice in invoices:
            try:
                paths.append(self.export(invoice))
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "فشل تصدير الفاتورة %s: %s",
                    invoice.invoice_number, exc
                )
        return paths

    def mark_processed(self, csv_path: Path) -> None:
        """نقل الملف إلى مجلد الأرشيف بعد استيراده بنجاح"""
        dest = self.processed_dir / csv_path.name
        shutil.move(str(csv_path), str(dest))
        logger.info("تم أرشفة %s", dest)

    # ------------------------------------------------------------------
    # بناء أسطر دفتر اليومية
    # ------------------------------------------------------------------

    def _build_journal_rows(self, invoice: InvoiceData) -> List[list]:
        rows = []
        journal = invoice.pccompta_journal or "ACH"
        date = (
            invoice.invoice_date.strftime("%d/%m/%Y")
            if invoice.invoice_date else ""
        )
        ref = invoice.invoice_number or ""
        vendor = invoice.vendor_name or ""
        vendor_account = (
            invoice.pccompta_account_vendor
            or "401" + (vendor[:5].upper().replace(" ", "") or "XXXXX")
        )
        purchase_account = invoice.pccompta_account_purchase or "607000"
        tva_account = invoice.pccompta_account_tva or "445660"

        # سطر المورد — مدين بـ TTC
        if invoice.total_ttc:
            rows.append([
                journal, date, ref,
                vendor_account,
                f"Achat - {vendor}"[:50],
                self._fmt_amount(invoice.total_ttc),
                "",
            ])

        # سطر TVA — مدين بـ TVA (إذا كانت > 0)
        if invoice.tva_amount and invoice.tva_amount > 0:
            rows.append([
                journal, date, ref,
                tva_account,
                f"TVA déductible - {vendor}"[:50],
                self._fmt_amount(invoice.tva_amount),
                "",
            ])

        # سطر المشتريات — دائن بـ HT
        if invoice.subtotal_ht:
            rows.append([
                journal, date, ref,
                purchase_account,
                f"Achats HT - {vendor}"[:50],
                "",
                self._fmt_amount(invoice.subtotal_ht),
            ])

        # إذا لم تتوفر HT و TVA، نُنشئ سطراً واحداً بـ TTC
        if not rows and invoice.total_ttc:
            rows.append([
                journal, date, ref,
                vendor_account,
                f"Achat - {vendor}"[:50],
                self._fmt_amount(invoice.total_ttc),
                "",
            ])
            rows.append([
                journal, date, ref,
                purchase_account,
                f"Achats - {vendor}"[:50],
                "",
                self._fmt_amount(invoice.total_ttc),
            ])

        return rows

    def _build_filename(self, invoice: InvoiceData) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_ref = (
            (invoice.invoice_number or "NOINV")
            .replace("/", "-")
            .replace("\\", "-")
            .replace(" ", "_")
        )
        return f"import_{safe_ref}_{ts}.csv"

    @staticmethod
    def _fmt_amount(value: Optional[float]) -> str:
        """تنسيق المبلغ: فاصل عشري بفاصلة للتوافق مع Excel الفرنسي"""
        if value is None:
            return ""
        return f"{value:.3f}".replace(".", ",")
