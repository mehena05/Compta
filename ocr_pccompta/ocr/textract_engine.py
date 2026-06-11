"""
محرك Amazon Textract — الخيار الأول الموصى به للفواتير المحاسبية
"""

import os
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseOCREngine, RawExtractionResult


class TextractEngine(BaseOCREngine):
    """
    يستخدم AnalyzeExpense API لاستخراج حقول الفواتير والمصروفات
    مع دعم جداول بنية كاملة عبر AnalyzeDocument.
    """

    def __init__(
        self,
        region: str = "eu-west-1",
        s3_bucket: str = "",
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
    ) -> None:
        self.region = region
        self.s3_bucket = s3_bucket
        self._ak = aws_access_key_id
        self._sk = aws_secret_access_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3  # type: ignore

            kwargs: Dict[str, Any] = {"region_name": self.region}
            if self._ak:
                kwargs["aws_access_key_id"] = self._ak
                kwargs["aws_secret_access_key"] = self._sk
            self._client = boto3.client("textract", **kwargs)
        return self._client

    def is_available(self) -> bool:
        try:
            import boto3  # noqa: F401  type: ignore
            return bool(
                os.getenv("AWS_ACCESS_KEY_ID") or self._ak
            )
        except ImportError:
            return False

    def extract(self, file_path: Path) -> RawExtractionResult:
        client = self._get_client()
        file_bytes = file_path.read_bytes()

        try:
            # 1. استخراج حقول الفاتورة المنظمة
            expense_response = client.analyze_expense(
                Document={"Bytes": file_bytes}
            )
            structured_fields = self._parse_expense_response(
                expense_response
            )

            # 2. استخراج النص الكامل والجداول
            doc_response = client.analyze_document(
                Document={"Bytes": file_bytes},
                FeatureTypes=["TABLES", "FORMS"],
            )
            raw_text = self._extract_raw_text(doc_response)
            tables = self._extract_tables(doc_response)
            confidence = self._compute_overall_confidence(doc_response)

            return RawExtractionResult(
                raw_text=raw_text,
                confidence=confidence,
                structured_fields=structured_fields,
                tables=tables,
                engine_name="textract",
            )

        except Exception as exc:  # pylint: disable=broad-except
            return RawExtractionResult(
                raw_text="",
                confidence=0.0,
                structured_fields={},
                tables=[],
                engine_name="textract",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # معالجة ردود Textract
    # ------------------------------------------------------------------

    def _parse_expense_response(self, response: dict) -> dict:
        """استخراج الحقول المنظمة من AnalyzeExpense"""
        fields: Dict[str, Any] = {
            "line_items": [],
        }

        for expense_doc in response.get("ExpenseDocuments", []):
            # حقول الملخص
            for f in expense_doc.get("SummaryFields", []):
                key = f.get("Type", {}).get("Text", "").upper()
                value = f.get("ValueDetection", {}).get("Text", "")
                conf = f.get("ValueDetection", {}).get("Confidence", 0) / 100
                fields[key] = {"value": value, "confidence": conf}

            # بنود التفصيل
            for group in expense_doc.get("LineItemGroups", []):
                for item in group.get("LineItems", []):
                    line: Dict[str, Any] = {}
                    for f in item.get("LineItemExpenseFields", []):
                        key = f.get("Type", {}).get("Text", "").upper()
                        value = f.get("ValueDetection", {}).get("Text", "")
                        line[key] = value
                    if line:
                        fields["line_items"].append(line)

        return fields

    def _extract_raw_text(self, response: dict) -> str:
        lines: List[str] = []
        for block in response.get("Blocks", []):
            if block.get("BlockType") == "LINE":
                lines.append(block.get("Text", ""))
        return "\n".join(lines)

    def _extract_tables(
        self, response: dict
    ) -> List[List[List[str]]]:
        """إعادة بناء الجداول من مخرجات Textract"""
        blocks_by_id = {b["Id"]: b for b in response.get("Blocks", [])}
        tables: List[List[List[str]]] = []

        for block in response.get("Blocks", []):
            if block.get("BlockType") != "TABLE":
                continue
            cells: Dict[tuple, str] = {}
            max_row = max_col = 0

            for rel in block.get("Relationships", []):
                if rel.get("Type") != "CHILD":
                    continue
                for cell_id in rel.get("Ids", []):
                    cell = blocks_by_id.get(cell_id, {})
                    if cell.get("BlockType") != "CELL":
                        continue
                    row = cell.get("RowIndex", 1)
                    col = cell.get("ColumnIndex", 1)
                    max_row = max(max_row, row)
                    max_col = max(max_col, col)
                    text_parts: List[str] = []
                    for word_rel in cell.get("Relationships", []):
                        if word_rel.get("Type") != "CHILD":
                            continue
                        for word_id in word_rel.get("Ids", []):
                            word_block = blocks_by_id.get(word_id, {})
                            text_parts.append(
                                word_block.get("Text", "")
                            )
                    cells[(row, col)] = " ".join(text_parts)

            if max_row and max_col:
                matrix = [
                    [
                        cells.get((r, c), "")
                        for c in range(1, max_col + 1)
                    ]
                    for r in range(1, max_row + 1)
                ]
                tables.append(matrix)

        return tables

    def _compute_overall_confidence(self, response: dict) -> float:
        scores = [
            b.get("Confidence", 0) / 100
            for b in response.get("Blocks", [])
            if b.get("BlockType") == "WORD"
        ]
        return round(sum(scores) / len(scores), 3) if scores else 0.0
