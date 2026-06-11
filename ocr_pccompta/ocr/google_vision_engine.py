"""
محرك Google Document AI — الخيار الثاني الموصى به
يستخدم Invoice Parser المتخصص للفواتير.
"""

from pathlib import Path
from typing import List

from .base import BaseOCREngine, RawExtractionResult


class GoogleVisionEngine(BaseOCREngine):
    """
    Google Document AI — Invoice Parser Processor.
    يتطلب: google-cloud-documentai, google-cloud-vision
    """

    def __init__(
        self,
        project_id: str = "",
        location: str = "eu",
        processor_id: str = "",
        credentials_path: str = "",
    ) -> None:
        self.project_id = project_id
        self.location = location
        self.processor_id = processor_id
        self.credentials_path = credentials_path
        self._client = None

    def is_available(self) -> bool:
        try:
            import google.cloud.documentai  # noqa: F401  type: ignore
            return bool(self.project_id and self.processor_id)
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            from google.cloud import documentai  # type: ignore
            import os

            if self.credentials_path:
                os.environ[
                    "GOOGLE_APPLICATION_CREDENTIALS"
                ] = self.credentials_path

            opts = {"api_endpoint": f"{self.location}-documentai.googleapis.com"}
            self._client = documentai.DocumentProcessorServiceClient(
                client_options=opts
            )
        return self._client

    def extract(self, file_path: Path) -> RawExtractionResult:
        try:
            from google.cloud import documentai  # type: ignore

            client = self._get_client()
            processor_name = client.processor_path(
                self.project_id, self.location, self.processor_id
            )

            mime_type = (
                "application/pdf"
                if file_path.suffix.lower() == ".pdf"
                else "image/png"
            )
            raw_document = documentai.RawDocument(
                content=file_path.read_bytes(),
                mime_type=mime_type,
            )

            request = documentai.ProcessRequest(
                name=processor_name,
                raw_document=raw_document,
            )
            result = client.process_document(request=request)
            document = result.document

            structured_fields = self._parse_entities(document)
            tables = self._parse_tables(document)
            confidence = self._compute_confidence(document)

            return RawExtractionResult(
                raw_text=document.text,
                confidence=confidence,
                structured_fields=structured_fields,
                tables=tables,
                engine_name="google_vision",
            )

        except Exception as exc:  # pylint: disable=broad-except
            return RawExtractionResult(
                raw_text="",
                confidence=0.0,
                structured_fields={},
                tables=[],
                engine_name="google_vision",
                error=str(exc),
            )

    def _parse_entities(self, document) -> dict:
        """استخراج الكيانات المسمّاة من Document AI"""
        fields: dict = {"line_items": []}
        for entity in document.entities:
            entity_type = entity.type_
            value = entity.mention_text
            confidence = entity.confidence
            fields[entity_type] = {
                "value": value,
                "confidence": round(confidence, 3),
            }
        return fields

    def _parse_tables(self, document) -> List[List[List[str]]]:
        tables: List[List[List[str]]] = []
        for page in document.pages:
            for table in page.tables:
                matrix: List[List[str]] = []
                for row in list(table.header_rows) + list(table.body_rows):
                    matrix.append(
                        [
                            document.text[
                                cell.layout.text_anchor.text_segments[0].start_index:
                                cell.layout.text_anchor.text_segments[0].end_index
                            ]
                            if cell.layout.text_anchor.text_segments
                            else ""
                            for cell in row.cells
                        ]
                    )
                if matrix:
                    tables.append(matrix)
        return tables

    def _compute_confidence(self, document) -> float:
        scores = [e.confidence for e in document.entities if e.confidence]
        return round(sum(scores) / len(scores), 3) if scores else 0.0
