"""
مولّد ملفات Excel بتنسيق متوافق مع PCCompta
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

from ..models.invoice import InvoiceData
from ..validators.accounting_validator import ValidationResult


class PCComptaExcelGenerator:
    """
    ينتج ملف Excel بأربع أوراق:
      1. بيانات الفاتورة  — الحقول الرئيسية
      2. بنود التفصيل     — جدول البنود
      3. استيراد PCCompta — القيود الجاهزة للاستيراد
      4. سجل المعالجة    — معلومات التتبع والمراجعة
    """

    # ألوان حسب نسبة الثقة
    _COLOR_HIGH   = "C8E6C9"   # > 85%  أخضر فاتح
    _COLOR_MEDIUM = "FFF9C4"   # 60-85% أصفر
    _COLOR_LOW    = "FFCDD2"   # < 60%  أحمر فاتح

    _COLOR_HEADER = "1565C0"   # أزرق داكن لرؤوس الأعمدة
    _COLOR_TITLE  = "0D47A1"   # أزرق أكثر عمقاً للعناوين

    def generate(
        self,
        invoice: InvoiceData,
        output_path: Path,
        validation: Optional[ValidationResult] = None,
    ) -> Path:
        wb = openpyxl.Workbook()

        ws_main = wb.active
        ws_main.title = "بيانات الفاتورة"
        self._fill_main_sheet(ws_main, invoice, validation)

        ws_items = wb.create_sheet("بنود التفصيل")
        self._fill_items_sheet(ws_items, invoice)

        ws_pc = wb.create_sheet("استيراد PCCompta")
        self._fill_pccompta_sheet(ws_pc, invoice)

        ws_log = wb.create_sheet("سجل المعالجة")
        self._fill_log_sheet(ws_log, invoice, validation)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path

    # ------------------------------------------------------------------
    # ورقة 1 — البيانات الرئيسية
    # ------------------------------------------------------------------

    def _fill_main_sheet(
        self,
        ws,
        invoice: InvoiceData,
        validation: Optional[ValidationResult],
    ) -> None:
        ws.sheet_view.rightToLeft = True
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 38

        confidence_color = self._confidence_color(invoice.confidence_score)

        # عنوان الصفحة
        self._write_title(ws, "A1", "بيانات الفاتورة المستخرجة", span="B1")

        sections = [
            ("معلومات الفاتورة", [
                ("رقم الفاتورة",    invoice.invoice_number),
                ("تاريخ الفاتورة",  self._fmt_date(invoice.invoice_date)),
                ("تاريخ الاستحقاق", self._fmt_date(invoice.due_date)),
                ("نوع المستند",     invoice.document_type.value),
            ]),
            ("معلومات المورد", [
                ("اسم المورد",             invoice.vendor_name),
                ("رقم التعريف الضريبي",    invoice.vendor_tax_id),
                ("عنوان المورد",           invoice.vendor_address),
                ("هاتف المورد",            invoice.vendor_phone),
            ]),
            ("المبالغ المالية", [
                ("المجموع بدون ضريبة HT", invoice.subtotal_ht),
                ("نسبة TVA %",            invoice.tva_rate),
                ("مبلغ TVA",              invoice.tva_amount),
                ("الإجمالي TTC",          invoice.total_ttc),
                ("العملة",                invoice.currency),
            ]),
            ("معلومات الجودة", [
                ("نسبة الثقة",        f"{invoice.confidence_score:.0%}"),
                ("تتطلب مراجعة",      "نعم" if invoice.needs_review else "لا"),
                ("محرك الاستخراج",    invoice.extraction_source.value),
                ("تاريخ المعالجة",    invoice.extracted_at.strftime(
                    "%d/%m/%Y %H:%M")),
            ]),
        ]

        row = 3
        for section_title, fields in sections:
            self._write_section_header(ws, row, section_title)
            row += 1
            for label, value in fields:
                cell_label = ws.cell(row=row, column=1, value=label)
                cell_label.font = Font(bold=True, size=10)
                cell_label.alignment = Alignment(
                    horizontal="right", vertical="center"
                )

                cell_val = ws.cell(row=row, column=2, value=value)
                cell_val.alignment = Alignment(
                    horizontal="right", vertical="center"
                )
                # لون خلفية حسب الثقة للحقول المالية
                if label in (
                    "المجموع بدون ضريبة HT",
                    "مبلغ TVA",
                    "الإجمالي TTC",
                ):
                    cell_val.fill = PatternFill(
                        start_color=confidence_color, fill_type="solid"
                    )
                row += 1
            row += 1  # مسافة بين الأقسام

        # مشكلات الاستخراج
        if invoice.extraction_issues:
            self._write_section_header(ws, row, "مشكلات الاستخراج")
            row += 1
            for issue in invoice.extraction_issues:
                ws.cell(row=row, column=1, value="⚠️").alignment = \
                    Alignment(horizontal="center")
                cell = ws.cell(row=row, column=2, value=issue)
                cell.fill = PatternFill(
                    start_color="FFCDD2", fill_type="solid"
                )
                row += 1

    # ------------------------------------------------------------------
    # ورقة 2 — بنود التفصيل
    # ------------------------------------------------------------------

    def _fill_items_sheet(self, ws, invoice: InvoiceData) -> None:
        ws.sheet_view.rightToLeft = True

        headers = [
            "الوصف", "الكمية", "سعر الوحدة HT",
            "المجموع HT", "نسبة TVA %", "مبلغ TVA", "المجموع TTC",
        ]
        self._write_header_row(ws, 1, headers)

        if not invoice.line_items:
            ws.cell(row=2, column=1,
                    value="لا توجد بنود تفصيلية مستخرجة")
            return

        for i, item in enumerate(invoice.line_items, start=2):
            row_data = [
                item.description,
                item.quantity,
                item.unit_price,
                item.total_ht,
                item.tva_rate,
                item.tva_amount,
                item.total_ttc,
            ]
            color = self._confidence_color(item.confidence)
            for col, value in enumerate(row_data, start=1):
                cell = ws.cell(row=i, column=col, value=value)
                cell.alignment = Alignment(
                    horizontal="right" if col > 1 else "right",
                    vertical="center",
                )
                if col > 1 and value is not None:
                    cell.fill = PatternFill(
                        start_color=color, fill_type="solid"
                    )
                cell.number_format = (
                    "#,##0.000" if col in (3, 4, 6, 7) else "General"
                )

        # صف المجاميع
        total_row = len(invoice.line_items) + 2
        ws.cell(row=total_row, column=1,
                value="المجموع").font = Font(bold=True)
        for col, attr in [(4, "sum_line_items_ht"), (6, "sum_line_items_tva")]:
            val = getattr(invoice, attr)()
            cell = ws.cell(row=total_row, column=col, value=val)
            cell.font = Font(bold=True)
            cell.number_format = "#,##0.000"

        self._auto_width(ws, len(headers))

    # ------------------------------------------------------------------
    # ورقة 3 — استيراد PCCompta
    # ------------------------------------------------------------------

    def _fill_pccompta_sheet(self, ws, invoice: InvoiceData) -> None:
        headers = [
            "JOURNAL", "DATE", "PIECE",
            "COMPTE", "LIBELLE", "DEBIT", "CREDIT",
        ]
        self._write_header_row(ws, 1, headers)

        date_str = self._fmt_date(invoice.invoice_date) or ""
        ref = invoice.invoice_number or ""
        vendor = invoice.vendor_name or ""
        vendor_account = invoice.pccompta_account_vendor or (
            "401" + vendor[:5].upper().replace(" ", "")
        )
        purchase_account = invoice.pccompta_account_purchase or "607000"
        tva_account = invoice.pccompta_account_tva or "445660"
        journal = invoice.pccompta_journal or "ACH"

        rows = []

        # سطر المورد (مدين)
        if invoice.total_ttc:
            rows.append([
                journal, date_str, ref,
                vendor_account,
                f"Achat - {vendor}",
                invoice.total_ttc, "",
            ])

        # سطر TVA (مدين)
        if invoice.tva_amount and invoice.tva_amount > 0:
            rows.append([
                journal, date_str, ref,
                tva_account,
                f"TVA déductible - {vendor}",
                invoice.tva_amount, "",
            ])

        # سطر المشتريات (دائن)
        if invoice.subtotal_ht:
            rows.append([
                journal, date_str, ref,
                purchase_account,
                f"Achats HT - {vendor}",
                "", invoice.subtotal_ht,
            ])

        for i, row_data in enumerate(rows, start=2):
            for col, value in enumerate(row_data, start=1):
                cell = ws.cell(row=i, column=col, value=value)
                cell.alignment = Alignment(
                    horizontal="center" if col in (1, 2, 3)
                    else "right",
                    vertical="center",
                )
                if col in (6, 7) and value:
                    cell.number_format = "#,##0.000"

        # سطر التحقق من التوازن
        total_row = len(rows) + 3
        ws.cell(row=total_row, column=5,
                value="مجموع المدين = مجموع الدائن؟").font = Font(bold=True)

        debit_sum = sum(
            r[5] for r in rows if r[5]
        )
        credit_sum = sum(
            r[6] for r in rows if r[6]
        )
        ws.cell(row=total_row, column=6, value=debit_sum).font = \
            Font(bold=True)
        ws.cell(row=total_row, column=7, value=credit_sum).font = \
            Font(bold=True)

        balanced = abs(debit_sum - credit_sum) < 0.01
        status_cell = ws.cell(
            row=total_row + 1, column=5,
            value="✅ متوازن" if balanced else "❌ غير متوازن"
        )
        status_cell.font = Font(
            bold=True,
            color="2E7D32" if balanced else "C62828"
        )

        self._auto_width(ws, len(headers))

    # ------------------------------------------------------------------
    # ورقة 4 — سجل المعالجة
    # ------------------------------------------------------------------

    def _fill_log_sheet(
        self,
        ws,
        invoice: InvoiceData,
        validation: Optional[ValidationResult],
    ) -> None:
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 50

        self._write_title(ws, "A1", "سجل معالجة المستند", span="B1")

        data = [
            ("معرّف المستند",          invoice.document_id),
            ("الملف المصدر",           invoice.source_file or ""),
            ("محرك OCR",               invoice.extraction_source.value),
            ("تاريخ المعالجة",          invoice.extracted_at.strftime(
                "%Y-%m-%d %H:%M:%S")),
            ("نسبة الثقة",              f"{invoice.confidence_score:.1%}"),
            ("تتطلب مراجعة",            "نعم" if invoice.needs_review else "لا"),
            ("تم التحقق",               "نعم" if invoice.is_validated else "لا"),
            ("تم تصدير Excel",          "نعم" if invoice.is_exported_excel else "لا"),
            ("تم الاستيراد PCCompta",   "نعم" if invoice.is_imported_pccompta else "لا"),
        ]

        for row_idx, (label, value) in enumerate(data, start=3):
            ws.cell(row=row_idx, column=1, value=label).font = \
                Font(bold=True)
            ws.cell(row=row_idx, column=2, value=value)

        if validation:
            row = len(data) + 5
            ws.cell(row=row, column=1,
                    value="نتائج التحقق").font = Font(bold=True, size=11)
            row += 1
            for msg, sev in validation.issues:
                icon = "❌" if sev.value == "error" else "⚠️"
                ws.cell(row=row, column=1, value=icon)
                cell = ws.cell(row=row, column=2, value=msg)
                cell.fill = PatternFill(
                    start_color=(
                        "FFCDD2" if sev.value == "error" else "FFF9C4"
                    ),
                    fill_type="solid",
                )
                row += 1

    # ------------------------------------------------------------------
    # دوال مساعدة للتنسيق
    # ------------------------------------------------------------------

    def _write_title(self, ws, cell_ref: str, text: str,
                     span: str = "") -> None:
        cell = ws[cell_ref]
        cell.value = text
        cell.font = Font(bold=True, size=13, color="FFFFFF")
        cell.fill = PatternFill(
            start_color=self._COLOR_TITLE, fill_type="solid"
        )
        cell.alignment = Alignment(horizontal="center", vertical="center")
        if span:
            ws.merge_cells(f"{cell_ref}:{span}")

    def _write_section_header(self, ws, row: int, text: str) -> None:
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = Font(bold=True, size=11, color="FFFFFF")
        cell.fill = PatternFill(
            start_color=self._COLOR_HEADER, fill_type="solid"
        )
        cell.alignment = Alignment(horizontal="right")
        ws.cell(row=row, column=2).fill = PatternFill(
            start_color=self._COLOR_HEADER, fill_type="solid"
        )

    def _write_header_row(self, ws, row: int, headers: list) -> None:
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=row, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            cell.fill = PatternFill(
                start_color=self._COLOR_HEADER, fill_type="solid"
            )
            cell.alignment = Alignment(
                horizontal="center", vertical="center"
            )
            thin = Side(border_style="thin", color="FFFFFF")
            cell.border = Border(
                left=thin, right=thin, top=thin, bottom=thin
            )

    def _auto_width(self, ws, col_count: int) -> None:
        for col in range(1, col_count + 1):
            max_len = 10
            col_letter = get_column_letter(col)
            for cell in ws[col_letter]:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)) + 4)
            ws.column_dimensions[col_letter].width = min(max_len, 50)

    def _confidence_color(self, score: float) -> str:
        if score >= 0.85:
            return self._COLOR_HIGH
        if score >= 0.60:
            return self._COLOR_MEDIUM
        return self._COLOR_LOW

    def _fmt_date(self, dt) -> Optional[str]:
        return dt.strftime("%d/%m/%Y") if dt else None
