from pathlib import Path
import subprocess
import tempfile

from app.telegram_bridge import DownloadedTelegramFile


IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}

PDF_MIME_TYPE = "application/pdf"

OFFICE_MIME_TYPES = {
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "text/plain",
    "text/markdown",
}


class PreviewRenderer:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def render(self, *, file_id: int, downloaded: DownloadedTelegramFile) -> DownloadedTelegramFile | None:
        mime_type = downloaded.mime_type or "application/octet-stream"
        if mime_type in IMAGE_MIME_TYPES:
            return downloaded
        if mime_type == PDF_MIME_TYPE:
            return downloaded
        if mime_type not in OFFICE_MIME_TYPES:
            return None
        pdf_path = self._cache_dir / f"{file_id}.pdf"
        if not pdf_path.exists():
            pdf_path = self._convert_to_pdf(downloaded.filename, downloaded.content, pdf_path)
        return DownloadedTelegramFile(
            filename=pdf_path.name,
            content=pdf_path.read_bytes(),
            mime_type=PDF_MIME_TYPE,
        )

    def _convert_to_pdf(self, filename: str, content: bytes, output: Path) -> Path:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / filename
            source.write_bytes(content)
            subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(source)],
                capture_output=True,
                check=True,
                timeout=180,
            )
            pdf_candidates = list(Path(tmp).glob("*.pdf"))
            if not pdf_candidates:
                raise RuntimeError(f"LibreOffice produced no PDF for {filename}")
            output.write_bytes(pdf_candidates[0].read_bytes())
        return output
