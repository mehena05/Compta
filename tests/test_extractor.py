"""
اختبارات محرك استخراج بيانات الفواتير
"""

import pytest
from ocr_pccompta.extractors.invoice_extractor import InvoiceDataExtractor
from ocr_pccompta.ocr.base import RawExtractionResult


@pytest.fixture
def extractor():
    return InvoiceDataExtractor()


def _make_ocr_result(text: str, fields: dict = None) -> RawExtractionResult:
    return RawExtractionResult(
        raw_text=text,
        confidence=0.92,
        structured_fields=fields or {},
        tables=[],
        engine_name="textract",
    )


class TestRawTextExtraction:

    def test_extract_invoice_number_french(self, extractor):
        result = _make_ocr_result("Facture N° FAC-2024-001\nDate: 15/03/2024")
        invoice = extractor.extract(result)
        assert invoice.invoice_number == "FAC-2024-001"

    def test_extract_invoice_number_arabic(self, extractor):
        result = _make_ocr_result("رقم الفاتورة: INV-2024-055")
        invoice = extractor.extract(result)
        assert invoice.invoice_number == "INV-2024-055"

    def test_extract_date(self, extractor):
        result = _make_ocr_result("Date: 25/06/2024")
        invoice = extractor.extract(result)
        assert invoice.invoice_date is not None
        assert invoice.invoice_date.year == 2024
        assert invoice.invoice_date.month == 6
        assert invoice.invoice_date.day == 25

    def test_extract_total_ttc(self, extractor):
        result = _make_ocr_result("Total TTC: 1190.000")
        invoice = extractor.extract(result)
        assert invoice.total_ttc == 1190.0

    def test_extract_amounts_european_format(self, extractor):
        result = _make_ocr_result(
            "Total HT: 1.000,000\nTVA: 190,000\nTotal TTC: 1.190,000"
        )
        invoice = extractor.extract(result)
        assert invoice.subtotal_ht == 1000.0
        assert invoice.tva_amount == 190.0
        assert invoice.total_ttc == 1190.0


class TestStructuredFieldsExtraction:

    def test_textract_fields_mapping(self, extractor):
        fields = {
            "VENDOR_NAME":          {"value": "SARL Example", "confidence": 0.99},
            "INVOICE_RECEIPT_ID":   {"value": "FAC-001", "confidence": 0.98},
            "TOTAL":                {"value": "1190.000", "confidence": 0.97},
            "SUBTOTAL":             {"value": "1000.000", "confidence": 0.97},
            "TAX":                  {"value": "190.000", "confidence": 0.96},
            "line_items":           [],
        }
        result = _make_ocr_result("", fields)
        invoice = extractor.extract(result)

        assert invoice.vendor_name == "SARL Example"
        assert invoice.invoice_number == "FAC-001"
        assert invoice.total_ttc == 1190.0
        assert invoice.subtotal_ht == 1000.0
        assert invoice.tva_amount == 190.0

    def test_structured_takes_precedence_over_raw(self, extractor):
        # الحقول المنظمة يجب أن تُقدَّم على النص الخام
        fields = {
            "TOTAL": {"value": "1190.000", "confidence": 0.99},
            "line_items": [],
        }
        result = _make_ocr_result(
            "Total: 9999.000",  # قيمة خاطئة في النص الخام
            fields,
        )
        invoice = extractor.extract(result)
        assert invoice.total_ttc == 1190.0


class TestAmountNormalization:

    def test_normalize_integer_amount(self, extractor):
        assert extractor._normalize_amount("1190") == 1190.0

    def test_normalize_decimal_dot(self, extractor):
        assert extractor._normalize_amount("1190.500") == 1190.5

    def test_normalize_decimal_comma(self, extractor):
        assert extractor._normalize_amount("1190,500") == 1190.5

    def test_normalize_european_thousands(self, extractor):
        assert extractor._normalize_amount("1.190,500") == 1190.5

    def test_normalize_with_currency_suffix(self, extractor):
        assert extractor._normalize_amount("1190.000 TND") == 1190.0

    def test_normalize_zero_returns_none(self, extractor):
        assert extractor._normalize_amount("0") is None

    def test_normalize_empty_returns_none(self, extractor):
        assert extractor._normalize_amount("") is None


class TestMissingAmountComputation:

    def test_compute_total_from_ht_and_tva(self, extractor):
        result = _make_ocr_result("HT: 1000\nTVA: 190")
        invoice = extractor.extract(result)
        # يجب حساب TTC تلقائياً
        assert invoice.total_ttc == 1190.0

    def test_compute_ht_from_total_and_tva(self, extractor):
        result = _make_ocr_result("Total TTC: 1190\nTVA: 190")
        invoice = extractor.extract(result)
        assert invoice.subtotal_ht == 1000.0
