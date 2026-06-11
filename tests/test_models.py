"""
اختبارات نماذج البيانات
"""

import pytest
from datetime import datetime
from ocr_pccompta.models.invoice import InvoiceData, LineItem, DocumentType


class TestLineItem:

    def test_compute_totals_from_qty_and_price(self):
        item = LineItem(quantity=10, unit_price=100.0, tva_rate=19)
        item.compute_totals()
        assert item.total_ht == 1000.0
        assert item.tva_amount == 190.0
        assert item.total_ttc == 1190.0

    def test_compute_totals_no_overwrite(self):
        item = LineItem(
            quantity=10, unit_price=100.0,
            total_ht=999.0  # قيمة صريحة — لا تُحسب من جديد
        )
        item.compute_totals()
        assert item.total_ht == 999.0

    def test_compute_totals_zero_tva(self):
        item = LineItem(quantity=5, unit_price=200.0, tva_rate=0)
        item.compute_totals()
        assert item.total_ht == 1000.0
        assert item.tva_amount == 0.0
        assert item.total_ttc == 1000.0


class TestInvoiceData:

    def _sample_invoice(self) -> InvoiceData:
        return InvoiceData(
            invoice_number="FAC-2024-001",
            invoice_date=datetime(2024, 3, 15),
            vendor_name="Société Test SARL",
            subtotal_ht=1000.0,
            tva_rate=19.0,
            tva_amount=190.0,
            total_ttc=1190.0,
        )

    def test_to_pccompta_dict_keys(self):
        invoice = self._sample_invoice()
        d = invoice.to_pccompta_dict()
        for key in ("journal", "date", "reference", "vendor",
                    "total_ht", "tva", "total_ttc"):
            assert key in d

    def test_to_pccompta_dict_values(self):
        invoice = self._sample_invoice()
        d = invoice.to_pccompta_dict()
        assert d["reference"] == "FAC-2024-001"
        assert d["total_ht"] == 1000.0
        assert d["total_ttc"] == 1190.0

    def test_sum_line_items_ht(self):
        invoice = InvoiceData()
        invoice.line_items = [
            LineItem(total_ht=100.0),
            LineItem(total_ht=200.0),
            LineItem(total_ht=300.0),
        ]
        assert invoice.sum_line_items_ht() == 600.0

    def test_sum_line_items_empty(self):
        invoice = InvoiceData()
        assert invoice.sum_line_items_ht() is None

    def test_add_issue(self):
        invoice = InvoiceData()
        invoice.add_issue("خطأ تجريبي")
        assert "خطأ تجريبي" in invoice.extraction_issues

    def test_default_document_id_is_unique(self):
        inv1 = InvoiceData()
        inv2 = InvoiceData()
        assert inv1.document_id != inv2.document_id
