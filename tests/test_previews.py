from pathlib import Path

from app.previews import PreviewRenderer
from app.telegram_bridge import DownloadedTelegramFile


def test_image_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="photo.png",
        content=b"png-bytes",
        mime_type="image/png",
    )

    preview = renderer.render(file_id=1, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "image/png"
    assert preview.content == b"png-bytes"


def test_pdf_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="doc.pdf",
        content=b"%PDF-bytes",
        mime_type="application/pdf",
    )

    preview = renderer.render(file_id=2, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "application/pdf"


def test_unsupported_type_returns_none(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="archive.7z",
        content=b"7z-bytes",
        mime_type="application/x-7z-compressed",
    )

    preview = renderer.render(file_id=3, downloaded=downloaded)

    assert preview is None


def test_video_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="clip.mp4",
        content=b"video-bytes",
        mime_type="video/mp4",
    )

    preview = renderer.render(file_id=4, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "video/mp4"
    assert preview.content == b"video-bytes"


def test_audio_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="song.mp3",
        content=b"audio-bytes",
        mime_type="audio/mpeg",
    )

    preview = renderer.render(file_id=5, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "audio/mpeg"
    assert preview.content == b"audio-bytes"


def test_text_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="notes.txt",
        content=b"plain text",
        mime_type="text/plain",
    )

    preview = renderer.render(file_id=6, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "text/plain"
    assert preview.content == b"plain text"


def test_markdown_preview_passes_through(tmp_path: Path):
    renderer = PreviewRenderer(tmp_path)
    downloaded = DownloadedTelegramFile(
        filename="README.md",
        content=b"# Title",
        mime_type="text/markdown",
    )

    preview = renderer.render(file_id=7, downloaded=downloaded)

    assert preview is not None
    assert preview.mime_type == "text/markdown"
    assert preview.content == b"# Title"
