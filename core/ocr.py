"""
OCR Engine — multi-strategy text extraction.

Strategy by note_type:
  pdf   → PyMuPDF  (text-based PDFs, no binary needed)
          → page-to-image + Tesseract  (scanned/image PDFs)
  image → Tesseract (pytesseract)
  voice → stub  (speech-to-text is Phase 3+, needs Whisper / Google STT)
  text  → pass-through  (student typed directly, no extraction needed)

Tesseract binary must be installed separately:
  Windows: https://github.com/UB-Mannheim/tesseract/wiki
  Linux:   apt-get install tesseract-ocr
  macOS:   brew install tesseract

If Tesseract is not installed, images/scanned PDFs will return empty string
and the note will enter AWAITING_STUDENT_APPROVAL so the student can type
the text manually.  Text-based PDFs still work without Tesseract.
"""
import io
import logging

logger = logging.getLogger(__name__)


def extract_text(file_bytes: bytes, note_type: str) -> str:
    """
    Main entry point. Returns raw extracted text.
    Never interprets or summarises — that is the AI layer's job.
    """
    note_type = note_type.lower()

    if note_type == 'text':
        return ''

    if note_type == 'voice':
        logger.info('Voice note OCR not yet implemented — student will review manually.')
        return ''

    if note_type == 'pdf':
        return _extract_pdf(file_bytes)

    if note_type == 'image':
        return _extract_image(file_bytes)

    logger.warning('Unknown note_type "%s" — returning empty text.', note_type)
    return ''


# ── PDF extraction ────────────────────────────────────────────

def _extract_pdf(file_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error('PyMuPDF not installed. Run: pip install PyMuPDF')
        return ''

    try:
        doc = fitz.open(stream=file_bytes, filetype='pdf')
        pages_text = []

        for page_num, page in enumerate(doc):
            text = page.get_text('text').strip()

            if text:
                pages_text.append(text)
            else:
                # Scanned page — render to image and run Tesseract
                logger.info('Page %d has no selectable text — attempting image OCR.', page_num + 1)
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes('png')
                ocr_text = _tesseract_on_bytes(img_bytes)
                if ocr_text:
                    pages_text.append(ocr_text)

        doc.close()
        return '\n\n'.join(pages_text).strip()

    except Exception as exc:
        logger.exception('PDF extraction failed: %s', exc)
        return ''


# ── Image extraction ──────────────────────────────────────────

def _extract_image(file_bytes: bytes) -> str:
    return _tesseract_on_bytes(file_bytes)


def _tesseract_on_bytes(image_bytes: bytes) -> str:
    """Runs Tesseract OCR on raw image bytes. Returns empty string if Tesseract is not installed."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.error('pytesseract / Pillow not installed.')
        return ''

    try:
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed (RGBA, palette, etc. can cause issues)
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')

        text = pytesseract.image_to_string(image, config='--psm 6')
        return text.strip()

    except pytesseract.TesseractNotFoundError:
        logger.warning(
            'Tesseract binary not found. Install from https://github.com/UB-Mannheim/tesseract/wiki '
            'The student can review and type text manually.'
        )
        return ''

    except Exception as exc:
        logger.exception('Tesseract OCR failed: %s', exc)
        return ''
