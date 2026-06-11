"""
محرك استخراج وتحليل بيانات الفواتير من ناتج OCR الخام
"""

import re
from datetime import datetime
from typing import List, Optional

from ..models.invoice import ExtractionSource, InvoiceData, LineItem
from ..ocr.base import RawExtractionResult


class InvoiceDataExtractor:
    """
    يحول ناتج OCR الخام (نص + حقول منظمة) إلى كائن InvoiceData منظم.
    يعمل مع جميع محركات OCR المدعومة.
    """

    # --- أنماط Regex متعددة اللغات (عربي / فرنسي / إنجليزي) ---

    _DATE_PATTERNS = [
        r'(?:تاريخ|date d[\'e]?|invoice date|dated?)[:\s]*'
        r'(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})',
        r'(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})',
        r'(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})',
    ]

    _INVOICE_NUM_PATTERNS = [
        r'(?:رقم الفاتورة|facture\s*n[o°]?\.?|invoice\s*no\.?|réf\.?)'
        r'[:\s#]*([A-Z0-9/\-]{3,25})',
        r'(?:n°|no\.?|ref\.?)[:\s#]*([A-Z0-9/\-]{4,20})',
    ]

    _VENDOR_PATTERNS = [
        r'(?:من|fournisseur|vendor|société|raison sociale)[:\s]+'
        r'([^\n,]{3,60})',
    ]

    _AMOUNT_PATTERNS = {
        "total_ttc": [
            r'(?:total\s*ttc|إجمالي|montant\s*total|net\s*à\s*payer|total)'
            r'[:\s]*([0-9\s,\.]+)',
        ],
        "tva_amount": [
            r'(?:tva|ضريبة القيمة المضافة|montant\s*tva|vat)[:\s]*'
            r'([0-9\s,\.]+)',
        ],
        "subtotal_ht": [
            r'(?:total\s*ht|montant\s*ht|sous.total|hors\s*taxes?)'
            r'[:\s]*([0-9\s,\.]+)',
            r'(?:^|\s)ht\s*[:\s]+([0-9\s,\.]+)',
        ],
    }

    _TVA_RATE_PATTERN = r'(?:tva|taxe)\s*(?:à|au|@|:)?\s*(\d+)\s*%'

    _VENDOR_TAX_PATTERNS = [
        r'(?:mf|matricule fiscal|tax\s*id|siret)[:\s]*([A-Z0-9/\-]{5,20})',
    ]

    # رموز Textract المعيارية لحقول الفواتير
    _TEXTRACT_FIELD_MAP = {
        "VENDOR_NAME":             "vendor_name",
        "VENDOR_ADDRESS":          "vendor_address",
        "VENDOR_PHONE":            "vendor_phone",
        "RECEIVER_NAME":           "client_name",
        "RECEIVER_ADDRESS":        "client_address",
        "INVOICE_RECEIPT_ID":      "invoice_number",
        "INVOICE_RECEIPT_DATE":    "invoice_date",
        "DUE_DATE":                "due_date",
        "SUBTOTAL":                "subtotal_ht",
        "TAX":                     "tva_amount",
        "TOTAL":                   "total_ttc",
    }

    # رموز Google Document AI
    _GOOGLE_FIELD_MAP = {
        "supplier_name":           "vendor_name",
        "supplier_address":        "vendor_address",
        "receiver_name":           "client_name",
        "invoice_id":              "invoice_number",
        "invoice_date":            "invoice_date",
        "due_date":                "due_date",
        "net_amount":              "subtotal_ht",
        "total_tax_amount":        "tva_amount",
        "total_amount":            "total_ttc",
    }

    def extract(
        self,
        ocr_result: RawExtractionResult,
        source_file: str = "",
    ) -> InvoiceData:
        engine = ExtractionSource(
            ocr_result.engine_name
        ) if ocr_result.engine_name in [e.value for e in ExtractionSource] \
            else ExtractionSource.TEXTRACT

        invoice = InvoiceData(
            source_file=source_file,
            extraction_source=engine,
            raw_text=ocr_result.raw_text,
        )

        # 1. استخراج من الحقول المنظمة (Textract / Google)
        if ocr_result.structured_fields:
            self._extract_from_structured(
                ocr_result.structured_fields, invoice, engine
            )

        # 2. استخراج من النص الخام لتكملة ما ينقص
        self._extract_from_raw_text(ocr_result.raw_text, invoice)

        # 3. استخراج بنود التفصيل من الجداول
        if ocr_result.tables:
            invoice.line_items = self._extract_line_items(
                ocr_result.tables
            )

        # 4. استخراج البنود من الحقول المنظمة إن لم تُستخرج من الجداول
        if not invoice.line_items and ocr_result.structured_fields.get(
            "line_items"
        ):
            invoice.line_items = self._parse_structured_line_items(
                ocr_result.structured_fields["line_items"]
            )

        # 5. حساب المبالغ المفقودة
        self._compute_missing_amounts(invoice)

        # 6. حساب نسبة الثقة النهائية
        invoice.confidence_score = self._calculate_confidence(
            invoice, ocr_result.confidence
        )
        invoice.needs_review = (
            invoice.confidence_score
            < 0.85  # threshold مبدئي — يأتي من الإعدادات في الـ pipeline
        )

        return invoice

    # ------------------------------------------------------------------
    # استخراج من الحقول المنظمة
    # ------------------------------------------------------------------

    def _extract_from_structured(
        self,
        fields: dict,
        invoice: InvoiceData,
        engine: ExtractionSource,
    ) -> None:
        field_map = (
            self._GOOGLE_FIELD_MAP
            if engine == ExtractionSource.GOOGLE_VISION
            else self._TEXTRACT_FIELD_MAP
        )

        for api_key, attr in field_map.items():
            entry = fields.get(api_key)
            if not entry:
                continue
            raw_value = (
                entry["value"] if isinstance(entry, dict) else str(entry)
            )
            if not raw_value:
                continue

            if attr in ("invoice_date", "due_date"):
                parsed = self._parse_date(raw_value)
                if parsed:
                    setattr(invoice, attr, parsed)
            elif attr in ("subtotal_ht", "tva_amount", "total_ttc"):
                amount = self._normalize_amount(raw_value)
                if amount is not None:
                    setattr(invoice, attr, amount)
            else:
                if not getattr(invoice, attr):
                    setattr(invoice, attr, raw_value.strip())

    # ------------------------------------------------------------------
    # استخراج من النص الخام
    # ------------------------------------------------------------------

    def _extract_from_raw_text(
        self, text: str, invoice: InvoiceData
    ) -> None:
        if not text:
            return
        text_lower = text.lower()

        if not invoice.invoice_number:
            invoice.invoice_number = self._match_first(
                self._INVOICE_NUM_PATTERNS, text, flags=re.IGNORECASE
            )

        if not invoice.invoice_date:
            date_str = self._match_first(
                self._DATE_PATTERNS, text, flags=re.IGNORECASE
            )
            if date_str:
                invoice.invoice_date = self._parse_date(date_str)

        if not invoice.vendor_name:
            invoice.vendor_name = self._match_first(
                self._VENDOR_PATTERNS, text, flags=re.IGNORECASE
            )

        if not invoice.vendor_tax_id:
            invoice.vendor_tax_id = self._match_first(
                self._VENDOR_TAX_PATTERNS, text, flags=re.IGNORECASE
            )

        for field, patterns in self._AMOUNT_PATTERNS.items():
            if getattr(invoice, field) is not None:
                continue
            raw = self._match_first(patterns, text_lower, re.IGNORECASE)
            if raw:
                amount = self._normalize_amount(raw)
                if amount is not None:
                    setattr(invoice, field, amount)

        if invoice.tva_rate is None:
            match = re.search(self._TVA_RATE_PATTERN, text_lower)
            if match:
                invoice.tva_rate = float(match.group(1))

    # ------------------------------------------------------------------
    # استخراج بنود التفصيل من الجداول
    # ------------------------------------------------------------------

    def _extract_line_items(
        self, tables: List[List[List[str]]]
    ) -> List[LineItem]:
        items: List[LineItem] = []
        for table in tables:
            if len(table) < 2:
                continue
            headers = [h.lower().strip() for h in table[0]]
            for row in table[1:]:
                item = self._row_to_line_item(row, headers)
                if item:
                    item.compute_totals()
                    items.append(item)
        return items

    def _row_to_line_item(
        self, row: List[str], headers: List[str]
    ) -> Optional[LineItem]:
        item = LineItem()
        has_data = False

        col_aliases = {
            "description": [
                "description", "désignation", "libellé",
                "article", "produit", "البيان", "الوصف",
            ],
            "quantity": [
                "qté", "quantité", "qty", "quantity", "الكمية",
            ],
            "unit_price": [
                "pu ht", "prix unitaire", "unit price",
                "p.u", "سعر الوحدة",
            ],
            "total_ht": [
                "montant ht", "total ht", "amount",
                "المجموع ht", "المبلغ",
            ],
            "tva_rate": ["taux tva", "tva %", "% tva", "نسبة tva"],
        }

        for attr, aliases in col_aliases.items():
            for i, header in enumerate(headers):
                if i >= len(row):
                    break
                if any(alias in header for alias in aliases):
                    val = row[i].strip()
                    if not val:
                        continue
                    has_data = True
                    if attr in ("quantity", "unit_price", "total_ht"):
                        setattr(item, attr, self._normalize_amount(val))
                    elif attr == "tva_rate":
                        m = re.search(r"(\d+)", val)
                        if m:
                            item.tva_rate = float(m.group(1))
                    else:
                        setattr(item, attr, val)
                    break

        return item if has_data else None

    def _parse_structured_line_items(
        self, raw_items: list
    ) -> List[LineItem]:
        items: List[LineItem] = []
        for raw in raw_items:
            item = LineItem(
                description=raw.get("ITEM", raw.get("DESCRIPTION", "")),
                quantity=self._normalize_amount(raw.get("QUANTITY", "")),
                unit_price=self._normalize_amount(raw.get("UNIT_PRICE", "")),
                total_ht=self._normalize_amount(raw.get("PRICE", "")),
            )
            item.compute_totals()
            items.append(item)
        return items

    # ------------------------------------------------------------------
    # حساب المبالغ المفقودة
    # ------------------------------------------------------------------

    def _compute_missing_amounts(self, invoice: InvoiceData) -> None:
        # HT + TVA → TTC
        if (invoice.subtotal_ht is not None
                and invoice.tva_amount is not None
                and invoice.total_ttc is None):
            invoice.total_ttc = round(
                invoice.subtotal_ht + invoice.tva_amount, 3
            )

        # TTC - TVA → HT
        if (invoice.total_ttc is not None
                and invoice.tva_amount is not None
                and invoice.subtotal_ht is None):
            invoice.subtotal_ht = round(
                invoice.total_ttc - invoice.tva_amount, 3
            )

        # HT × rate → TVA
        if (invoice.subtotal_ht is not None
                and invoice.tva_rate is not None
                and invoice.tva_amount is None):
            invoice.tva_amount = round(
                invoice.subtotal_ht * invoice.tva_rate / 100, 3
            )

        # استخراج من مجموع البنود إن كانت متاحة
        if not invoice.subtotal_ht and invoice.line_items:
            total = invoice.sum_line_items_ht()
            if total:
                invoice.subtotal_ht = total

    # ------------------------------------------------------------------
    # حساب نسبة الثقة
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self, invoice: InvoiceData, ocr_confidence: float
    ) -> float:
        required = [
            invoice.invoice_number,
            invoice.invoice_date,
            invoice.vendor_name,
            invoice.total_ttc,
        ]
        completeness = sum(1 for f in required if f is not None) / len(
            required
        )

        score = (completeness * 0.6) + (ocr_confidence * 0.4)

        # مكافأة إذا تحقق التوازن الحسابي
        if all(
            [invoice.subtotal_ht, invoice.tva_amount, invoice.total_ttc]
        ):
            expected = round(invoice.subtotal_ht + invoice.tva_amount, 2)
            if abs(expected - invoice.total_ttc) <= 0.02:
                score = min(1.0, score + 0.05)
            else:
                score -= 0.15
                invoice.add_issue(
                    f"خلل حسابي: {invoice.subtotal_ht} + "
                    f"{invoice.tva_amount} ≠ {invoice.total_ttc}"
                )

        return round(max(0.0, min(1.0, score)), 3)

    # ------------------------------------------------------------------
    # دوال مساعدة
    # ------------------------------------------------------------------

    def _match_first(
        self, patterns: list, text: str, flags: int = 0
    ) -> Optional[str]:
        for pattern in patterns:
            m = re.search(pattern, text, flags)
            if m:
                return m.group(1).strip()
        return None

    def _normalize_amount(self, raw: str) -> Optional[float]:
        if not raw:
            return None
        cleaned = re.sub(r"[^\d,\.]", "", raw.strip())
        if not cleaned:
            return None
        # تنسيق أوروبي: 1.234,56 → 1234.56
        if re.match(r"\d{1,3}(\.\d{3})*,\d{1,3}$", cleaned):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        # فاصل عشري بفاصلة فقط
        elif "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            value = float(cleaned)
            return value if value > 0 else None
        except ValueError:
            return None

    def _parse_date(self, raw: str) -> Optional[datetime]:
        raw = raw.strip()
        formats = [
            "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
            "%Y/%m/%d", "%Y-%m-%d",
            "%d/%m/%y", "%d-%m-%y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None
