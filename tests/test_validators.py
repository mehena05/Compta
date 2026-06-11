"""
اختبارات محرك التحقق المحاسبي
"""

import pytest
from datetime import datetime, timedelta
from ocr_pccompta.models.invoice import InvoiceData
from ocr_pccompta.validators.accounting_validator import (
    AccountingValidator,
    ValidationSeverity,
)


@pytest.fixture
def validator():
    return AccountingValidator()


@pytest.fixture
def valid_invoice():
    return InvoiceData(
        invoice_number="FAC-2024-001",
        invoice_date=datetime(2024, 3, 15),
        vendor_name="Test SARL",
        vendor_tax_id="1234567A",
        subtotal_ht=1000.0,
        tva_rate=19.0,
        tva_amount=190.0,
        total_ttc=1190.0,
    )


class TestCompleteness:

    def test_all_required_fields_present(self, validator, valid_invoice):
        result = validator.validate(valid_invoice)
        errors = [m for m, s in result.issues
                  if s == ValidationSeverity.ERROR and "إلزامي" in m]
        assert len(errors) == 0

    def test_missing_invoice_number(self, validator, valid_invoice):
        valid_invoice.invoice_number = None
        result = validator.validate(valid_invoice)
        assert any("رقم الفاتورة" in m for m, _ in result.issues)
        assert not result.is_valid

    def test_missing_vendor_name(self, validator, valid_invoice):
        valid_invoice.vendor_name = None
        result = validator.validate(valid_invoice)
        assert not result.is_valid

    def test_missing_total_is_error(self, validator, valid_invoice):
        valid_invoice.total_ttc = None
        result = validator.validate(valid_invoice)
        assert not result.is_valid


class TestArithmetic:

    def test_correct_calculation_passes(self, validator, valid_invoice):
        result = validator.validate(valid_invoice)
        arithmetic_errors = [
            m for m, s in result.issues
            if s == ValidationSeverity.ERROR and "حسابي" in m
        ]
        assert len(arithmetic_errors) == 0

    def test_wrong_total_is_error(self, validator, valid_invoice):
        valid_invoice.total_ttc = 1500.0  # خطأ متعمد
        result = validator.validate(valid_invoice)
        assert any("حسابي" in m for m, _ in result.issues)
        assert not result.is_valid

    def test_tolerance_accepted(self, validator, valid_invoice):
        valid_invoice.total_ttc = 1190.01  # ضمن التحمل 0.02
        result = validator.validate(valid_invoice)
        arithmetic_errors = [
            m for m, s in result.issues
            if s == ValidationSeverity.ERROR and "حسابي" in m
        ]
        assert len(arithmetic_errors) == 0

    def test_unusual_tva_rate_is_warning(self, validator, valid_invoice):
        valid_invoice.tva_amount = 150.0  # 15% غير معتاد
        valid_invoice.total_ttc = 1150.0
        result = validator.validate(valid_invoice)
        warnings = [m for m, s in result.issues
                    if s == ValidationSeverity.WARNING and "TVA" in m]
        assert len(warnings) > 0


class TestLogicalConsistency:

    def test_future_date_is_error(self, validator, valid_invoice):
        valid_invoice.invoice_date = datetime.now() + timedelta(days=30)
        result = validator.validate(valid_invoice)
        assert any("المستقبل" in m for m, _ in result.issues)

    def test_negative_amount_is_error(self, validator, valid_invoice):
        valid_invoice.total_ttc = -100.0
        result = validator.validate(valid_invoice)
        assert any("سالبة" in m for m, _ in result.issues)

    def test_due_date_before_invoice_date_is_error(
        self, validator, valid_invoice
    ):
        valid_invoice.due_date = valid_invoice.invoice_date - timedelta(
            days=5
        )
        result = validator.validate(valid_invoice)
        assert any("الاستحقاق" in m for m, _ in result.issues)
