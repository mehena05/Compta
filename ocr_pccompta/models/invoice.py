"""
نماذج البيانات الأساسية — تمثل الوثائق المحاسبية المستخرجة
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class DocumentType(Enum):
    INVOICE_PURCHASE = "invoice_purchase"   # فاتورة شراء
    INVOICE_SALE = "invoice_sale"           # فاتورة بيع
    RECEIPT = "receipt"                     # وصل/إيصال
    CREDIT_NOTE = "credit_note"             # أذن إضافة
    DEBIT_NOTE = "debit_note"               # أذن خصم
    UNKNOWN = "unknown"


class ExtractionSource(Enum):
    TEXTRACT = "textract"
    GOOGLE_VISION = "google_vision"
    TESSERACT = "tesseract"
    MANUAL = "manual"


@dataclass
class LineItem:
    """بند تفصيلي في الفاتورة"""
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_ht: Optional[float] = None
    tva_rate: Optional[float] = None
    tva_amount: Optional[float] = None
    total_ttc: Optional[float] = None

    # رمز المنتج/الخدمة (للتحليل المحاسبي)
    product_code: Optional[str] = None
    accounting_account: Optional[str] = None

    confidence: float = 1.0

    def compute_totals(self) -> None:
        """حساب المبالغ المفقودة من البيانات المتاحة"""
        if self.quantity and self.unit_price and not self.total_ht:
            self.total_ht = round(self.quantity * self.unit_price, 3)

        if self.total_ht and self.tva_rate is not None and not self.tva_amount:
            self.tva_amount = round(self.total_ht * self.tva_rate / 100, 3)

        if self.total_ht is not None and self.tva_amount is not None \
                and not self.total_ttc:
            self.total_ttc = round(self.total_ht + self.tva_amount, 3)


@dataclass
class InvoiceData:
    """
    النموذج الموحد لبيانات الفاتورة المستخرجة.
    يمثل الناتج من طبقة OCR وإدخال طبقات التحقق والتصدير.
    """

    # معرّف داخلي فريد لكل مستند معالج
    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    document_type: DocumentType = DocumentType.UNKNOWN
    source_file: Optional[str] = None
    extraction_source: ExtractionSource = ExtractionSource.TEXTRACT
    extracted_at: datetime = field(default_factory=datetime.now)

    # --- معلومات الفاتورة ---
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None

    # --- معلومات الأطراف ---
    vendor_name: Optional[str] = None
    vendor_tax_id: Optional[str] = None       # رقم التعريف الضريبي (MF)
    vendor_address: Optional[str] = None
    vendor_phone: Optional[str] = None
    vendor_iban: Optional[str] = None

    client_name: Optional[str] = None
    client_tax_id: Optional[str] = None
    client_address: Optional[str] = None

    # --- المبالغ المالية ---
    subtotal_ht: Optional[float] = None       # Montant HT
    tva_rate: Optional[float] = None          # Taux TVA (%)
    tva_amount: Optional[float] = None        # Montant TVA
    total_ttc: Optional[float] = None         # Montant TTC
    currency: str = "TND"                     # Dinar Tunisien par défaut

    # --- بنود التفصيل ---
    line_items: List[LineItem] = field(default_factory=list)

    # --- معلومات القيد المحاسبي PCCompta ---
    pccompta_journal: Optional[str] = None
    pccompta_account_vendor: Optional[str] = None
    pccompta_account_purchase: Optional[str] = None
    pccompta_account_tva: Optional[str] = None

    # --- مقاييس جودة الاستخراج ---
    confidence_score: float = 0.0
    needs_review: bool = True
    extraction_issues: List[str] = field(default_factory=list)
    raw_text: Optional[str] = None

    # --- حالة المعالجة ---
    is_validated: bool = False
    is_exported_excel: bool = False
    is_imported_pccompta: bool = False

    def add_issue(self, message: str) -> None:
        self.extraction_issues.append(message)

    def sum_line_items_ht(self) -> Optional[float]:
        totals = [li.total_ht for li in self.line_items if li.total_ht]
        return round(sum(totals), 3) if totals else None

    def sum_line_items_tva(self) -> Optional[float]:
        amounts = [li.tva_amount for li in self.line_items if li.tva_amount]
        return round(sum(amounts), 3) if amounts else None

    def to_pccompta_dict(self) -> dict:
        """تصدير بيانات الفاتورة بتنسيق PCCompta CSV"""
        date_str = (
            self.invoice_date.strftime("%d/%m/%Y")
            if self.invoice_date else ""
        )
        return {
            "journal": self.pccompta_journal or "ACH",
            "date": date_str,
            "reference": self.invoice_number or "",
            "vendor": self.vendor_name or "",
            "total_ht": self.subtotal_ht or 0.0,
            "tva": self.tva_amount or 0.0,
            "total_ttc": self.total_ttc or 0.0,
            "account_vendor": self.pccompta_account_vendor or "",
            "account_purchase": self.pccompta_account_purchase or "607000",
            "account_tva": self.pccompta_account_tva or "445660",
        }
