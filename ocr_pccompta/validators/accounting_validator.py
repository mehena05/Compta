"""
محرك التحقق المحاسبي متعدد الطبقات
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple

from ..models.invoice import InvoiceData


class ValidationSeverity(Enum):
    ERROR = "error"       # يمنع الاستيراد إلى PCCompta
    WARNING = "warning"   # يتطلب مراجعة بشرية
    INFO = "info"         # ملاحظة معلوماتية


@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[Tuple[str, ValidationSeverity]] = field(
        default_factory=list
    )

    def has_blocking_errors(self) -> bool:
        return any(
            sev == ValidationSeverity.ERROR for _, sev in self.issues
        )

    @property
    def errors(self) -> List[str]:
        return [msg for msg, sev in self.issues
                if sev == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> List[str]:
        return [msg for msg, sev in self.issues
                if sev == ValidationSeverity.WARNING]

    def summary(self) -> str:
        if self.is_valid and not self.issues:
            return "✅ الفاتورة صحيحة — جاهزة للاستيراد"
        lines = [
            f"{'❌' if sev == ValidationSeverity.ERROR else '⚠️'} {msg}"
            for msg, sev in self.issues
        ]
        return "\n".join(lines)


class AccountingValidator:
    """
    أربع طبقات تحقق:
      1. حسابية   — صحة المعادلات المالية
      2. اكتمال    — الحقول الإلزامية
      3. منطقية   — تناسق القيم
      4. PCCompta  — توافق مع هيكل الحسابات
    """

    # نسب TVA المعتمدة في تونس (قابل للتعديل)
    VALID_TVA_RATES = {0, 7, 13, 19}
    AMOUNT_TOLERANCE = 0.02
    MAX_INVOICE_AGE_DAYS = 730   # سنتان
    FUTURE_DATE_DAYS = 7         # هامش خطأ للتواريخ المستقبلية

    # نطاق أرقام الحسابات الصحيح في PCCompta (مخطط حسابات تونسي)
    VALID_ACCOUNT_PREFIXES = {
        "1", "2", "3", "4", "5", "6", "7", "8", "9"
    }

    def validate(self, invoice: InvoiceData) -> ValidationResult:
        issues: List[Tuple[str, ValidationSeverity]] = []

        self._check_completeness(invoice, issues)
        self._check_arithmetic(invoice, issues)
        self._check_logical_consistency(invoice, issues)
        self._check_pccompta_compatibility(invoice, issues)

        is_valid = not any(
            sev == ValidationSeverity.ERROR for _, sev in issues
        )
        return ValidationResult(is_valid=is_valid, issues=issues)

    # ------------------------------------------------------------------
    # طبقة 1: التحقق من الاكتمال
    # ------------------------------------------------------------------

    def _check_completeness(
        self,
        invoice: InvoiceData,
        issues: List[Tuple[str, ValidationSeverity]],
    ) -> None:
        required = {
            "رقم الفاتورة": invoice.invoice_number,
            "تاريخ الفاتورة": invoice.invoice_date,
            "اسم المورد": invoice.vendor_name,
            "المبلغ الإجمالي TTC": invoice.total_ttc,
        }
        for name, value in required.items():
            if value is None:
                issues.append((
                    f"حقل إلزامي مفقود: {name}",
                    ValidationSeverity.ERROR,
                ))

        recommended = {
            "رقم التعريف الضريبي للمورد": invoice.vendor_tax_id,
            "المبلغ بدون ضريبة HT": invoice.subtotal_ht,
            "مبلغ TVA": invoice.tva_amount,
        }
        for name, value in recommended.items():
            if value is None:
                issues.append((
                    f"حقل مستحسن مفقود: {name}",
                    ValidationSeverity.WARNING,
                ))

    # ------------------------------------------------------------------
    # طبقة 2: التحقق الحسابي
    # ------------------------------------------------------------------

    def _check_arithmetic(
        self,
        invoice: InvoiceData,
        issues: List[Tuple[str, ValidationSeverity]],
    ) -> None:
        ht = invoice.subtotal_ht
        tva = invoice.tva_amount
        ttc = invoice.total_ttc
        rate = invoice.tva_rate

        # HT + TVA = TTC
        if ht is not None and tva is not None and ttc is not None:
            expected = round(ht + tva, 2)
            actual = round(ttc, 2)
            if abs(expected - actual) > self.AMOUNT_TOLERANCE:
                issues.append((
                    f"خطأ حسابي: {ht} + {tva} = {expected} ≠ {actual} (TTC)",
                    ValidationSeverity.ERROR,
                ))

        # نسبة TVA
        if ht and ht > 0 and tva is not None:
            computed_rate = round((tva / ht) * 100)
            if computed_rate not in self.VALID_TVA_RATES:
                issues.append((
                    f"نسبة TVA غير معتادة: {computed_rate}% "
                    f"(المعتمد: {sorted(self.VALID_TVA_RATES)})",
                    ValidationSeverity.WARNING,
                ))
            if rate is not None and abs(computed_rate - rate) > 1:
                issues.append((
                    f"تعارض في نسبة TVA: المصرّح {rate}% "
                    f"≠ المحسوب {computed_rate}%",
                    ValidationSeverity.WARNING,
                ))

        # مجموع بنود التفصيل = HT
        if invoice.line_items and ht is not None:
            lines_total = invoice.sum_line_items_ht()
            if lines_total and abs(lines_total - ht) > self.AMOUNT_TOLERANCE:
                issues.append((
                    f"مجموع البنود {lines_total} ≠ HT الإجمالي {ht}",
                    ValidationSeverity.WARNING,
                ))

    # ------------------------------------------------------------------
    # طبقة 3: التناسق المنطقي
    # ------------------------------------------------------------------

    def _check_logical_consistency(
        self,
        invoice: InvoiceData,
        issues: List[Tuple[str, ValidationSeverity]],
    ) -> None:
        now = datetime.now()

        if invoice.invoice_date:
            future_limit = (invoice.invoice_date - now).days
            if future_limit > self.FUTURE_DATE_DAYS:
                issues.append((
                    f"تاريخ الفاتورة في المستقبل: "
                    f"{invoice.invoice_date.strftime('%d/%m/%Y')}",
                    ValidationSeverity.ERROR,
                ))

            age_days = (now - invoice.invoice_date).days
            if age_days > self.MAX_INVOICE_AGE_DAYS:
                issues.append((
                    f"فاتورة قديمة جداً ({age_days} يوم)",
                    ValidationSeverity.WARNING,
                ))

        if invoice.due_date and invoice.invoice_date:
            if invoice.due_date < invoice.invoice_date:
                issues.append((
                    "تاريخ الاستحقاق أقدم من تاريخ الفاتورة",
                    ValidationSeverity.ERROR,
                ))

        for field_name, value in [
            ("total_ttc", invoice.total_ttc),
            ("subtotal_ht", invoice.subtotal_ht),
            ("tva_amount", invoice.tva_amount),
        ]:
            if value is not None and value < 0:
                issues.append((
                    f"قيمة سالبة غير متوقعة في {field_name}: {value}",
                    ValidationSeverity.ERROR,
                ))

    # ------------------------------------------------------------------
    # طبقة 4: توافق PCCompta
    # ------------------------------------------------------------------

    def _check_pccompta_compatibility(
        self,
        invoice: InvoiceData,
        issues: List[Tuple[str, ValidationSeverity]],
    ) -> None:
        for account_attr in (
            "pccompta_account_vendor",
            "pccompta_account_purchase",
            "pccompta_account_tva",
        ):
            account = getattr(invoice, account_attr)
            if account and not self._is_valid_account(account):
                issues.append((
                    f"رقم حساب غير صالح ({account_attr}): {account}",
                    ValidationSeverity.ERROR,
                ))

        if invoice.pccompta_journal:
            valid_journals = {"ACH", "VTE", "CAI", "BAN", "OD"}
            if invoice.pccompta_journal.upper() not in valid_journals:
                issues.append((
                    f"رمز دفتر يومية غير معروف: {invoice.pccompta_journal}",
                    ValidationSeverity.WARNING,
                ))

    def _is_valid_account(self, account: str) -> bool:
        """حساب مؤلف من 6-8 أرقام يبدأ بأحد الأرقام المعتمدة"""
        if not re.match(r"^\d{6,8}$", account):
            return False
        return account[0] in self.VALID_ACCOUNT_PREFIXES


import re  # noqa: E402 — استخدام في دالة منفردة
