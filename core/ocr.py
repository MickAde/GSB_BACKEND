"""
OCR Engine — multi-strategy text extraction.

Strategy by note_type:
  pdf   → PyMuPDF  (text-based pages, fast and free)
          → AI Vision  (scanned/handwritten pages — uses configured AI provider)
          → Tesseract fallback  (if no AI key configured)
  image → AI Vision first  (handles pencil, children's handwriting, low contrast)
          → Tesseract fallback
  voice → stub  (Phase 3+, needs Whisper / Google STT)
  text  → pass-through

AI Vision priority: OpenAI (GPT-4o) → Anthropic (Claude) → Gemini
Tesseract preprocessing pipeline (used when AI Vision is unavailable):
  grayscale → upscale to ≥2000px → autocontrast → contrast ×2 → unsharp mask → binarise

Why Vision AI outperforms Tesseract for handwritten notes:
  - Tesseract was trained on printed text; accuracy on pencil/handwriting is 30–60%.
  - GPT-4o / Claude / Gemini Vision achieve 90–100% on the same content because
    they were trained on billions of images including handwritten text and understand
    context to resolve ambiguous letters.
"""
import io
import base64
import logging

logger = logging.getLogger(__name__)

_TRANSCRIPTION_PROMPT = (
    "Transcribe ALL text visible in this image exactly as written. "
    "This is a student's handwritten note — include every word, heading, date, "
    "number, and label on diagrams. Preserve line breaks where possible. "
    "Do NOT summarise, interpret, or reformat. Output only the raw transcribed text."
)


# ── Public entry point ────────────────────────────────────────

def extract_text(file_bytes: bytes, note_type: str) -> str:
    """Returns raw extracted text. Never interprets — that is the AI layer's job."""
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
            # Try selectable text first — fast, free, perfect for typed PDFs
            text = page.get_text('text').strip()

            if text:
                pages_text.append(text)
            else:
                # Scanned or handwritten page — render to image then use Vision AI
                logger.info('Page %d: no selectable text — using image OCR.', page_num + 1)
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes('png')
                ocr_text = _extract_image(img_bytes)
                if ocr_text:
                    pages_text.append(ocr_text)

        doc.close()
        return '\n\n'.join(pages_text).strip()

    except Exception as exc:
        logger.exception('PDF extraction failed: %s', exc)
        return ''


# ── Image extraction ──────────────────────────────────────────

def _extract_image(image_bytes: bytes) -> str:
    """Try AI Vision first; fall back to Tesseract if no AI provider is configured."""
    text = _vision_transcribe(image_bytes)
    if text:
        return text

    logger.info('No AI Vision provider available — falling back to Tesseract.')
    return _tesseract_on_bytes(image_bytes)


# ── AI Vision transcription ───────────────────────────────────

def _vision_transcribe(image_bytes: bytes) -> str:
    """
    Send the image to a multimodal AI model for transcription.

    GPT-4o Vision is the default for all image/handwriting OCR — it achieves
    90-100% accuracy on pencil writing and children's handwriting.
    Falls back to Claude, then Gemini, if GPT-4o is unavailable.
    Returns empty string if all providers fail or no keys are configured.
    """
    from django.conf import settings

    # Vision provider order is fixed: GPT-4o first, regardless of AI_DEFAULT_TEXT_PROVIDER.
    # GPT-4o is the benchmark for handwriting transcription accuracy.
    providers = [
        (_openai_vision,    'OPENAI_API_KEY',    'GPT-4o Vision'),
        (_anthropic_vision, 'ANTHROPIC_API_KEY', 'Claude Vision'),
        (_gemini_vision,    'GEMINI_API_KEY',    'Gemini Vision'),
    ]

    for fn, key_attr, label in providers:
        if not getattr(settings, key_attr, ''):
            continue
        logger.info('Using %s for image transcription.', label)
        text = fn(image_bytes)
        if text:
            return text
        logger.warning('%s returned empty — trying next provider.', label)

    return ''


def _anthropic_vision(image_bytes: bytes) -> str:
    try:
        import anthropic
        from django.conf import settings

        # Detect media type from the image header bytes
        media_type = _detect_media_type(image_bytes)

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        b64 = base64.standard_b64encode(image_bytes).decode('utf-8')

        message = client.messages.create(
            model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            max_tokens=4096,
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': media_type,
                                'data': b64,
                            },
                        },
                        {'type': 'text', 'text': _TRANSCRIPTION_PROMPT},
                    ],
                }
            ],
        )
        text = message.content[0].text.strip()
        logger.info('Claude Vision extracted %d chars.', len(text))
        return text

    except Exception as exc:
        logger.exception('Claude Vision transcription failed: %s', exc)
        return ''


def _openai_vision(image_bytes: bytes) -> str:
    try:
        from openai import OpenAI
        from django.conf import settings

        media_type = _detect_media_type(image_bytes)
        b64 = base64.standard_b64encode(image_bytes).decode('utf-8')
        data_url = f'data:{media_type};base64,{b64}'

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': _TRANSCRIPTION_PROMPT},
                        {'type': 'image_url', 'image_url': {'url': data_url}},
                    ],
                }
            ],
            max_tokens=4096,
        )
        text = (response.choices[0].message.content or '').strip()
        logger.info('GPT-4o Vision extracted %d chars.', len(text))
        return text

    except Exception as exc:
        logger.exception('GPT-4o Vision transcription failed: %s', exc)
        return ''


def _gemini_vision(image_bytes: bytes) -> str:
    try:
        import google.generativeai as genai
        from django.conf import settings

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')

        # Gemini needs PIL Image for inline data
        from PIL import Image
        image = Image.open(io.BytesIO(image_bytes))

        model = genai.GenerativeModel(model_name)
        response = model.generate_content([_TRANSCRIPTION_PROMPT, image])
        text = (response.text or '').strip()
        logger.info('Gemini Vision extracted %d chars.', len(text))
        return text

    except Exception as exc:
        logger.exception('Gemini Vision transcription failed: %s', exc)
        return ''


def _detect_media_type(image_bytes: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if image_bytes[:4] == b'\x89PNG':
        return 'image/png'
    if image_bytes[:2] == b'\xff\xd8':
        return 'image/jpeg'
    if image_bytes[:4] == b'GIF8':
        return 'image/gif'
    if image_bytes[:4] in (b'RIFF', b'WEBP'):
        return 'image/webp'
    return 'image/jpeg'  # safe default


# ── Tesseract fallback ────────────────────────────────────────

def _preprocess_image(image: 'Image.Image') -> 'Image.Image':  # type: ignore[name-defined]
    """
    Pillow-only preprocessing pipeline for Tesseract.
    Helps with pencil writing but nowhere near Vision AI quality.
    """
    from PIL import ImageEnhance, ImageFilter, ImageOps

    image = image.convert('L')

    w, h = image.size
    if max(w, h) < 2000:
        scale = 2000 / max(w, h)
        from PIL import Image as _Image
        image = image.resize((int(w * scale), int(h * scale)), _Image.LANCZOS)

    # Autocontrast is the key step for pencil — stretches faint gray to full black
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    image = image.point(lambda x: 0 if x < 140 else 255, 'L')

    return image


def _tesseract_on_bytes(image_bytes: bytes) -> str:
    """Tesseract OCR with preprocessing. Used only when no AI Vision key is available."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.error('pytesseract / Pillow not installed.')
        return ''

    try:
        original = Image.open(io.BytesIO(image_bytes))
        processed = _preprocess_image(original)

        # --oem 1 = LSTM neural net (better for handwriting than legacy)
        # --psm 6 = uniform block of text
        text = pytesseract.image_to_string(processed, config='--oem 1 --psm 6')

        if len(text.strip()) < 30:
            logger.info('PSM 6 returned %d chars — retrying with PSM 3.', len(text.strip()))
            text_auto = pytesseract.image_to_string(processed, config='--oem 1 --psm 3')
            if len(text_auto.strip()) > len(text.strip()):
                text = text_auto

        result = text.strip()
        logger.info('Tesseract extracted %d chars.', len(result))
        return result

    except pytesseract.TesseractNotFoundError:
        logger.warning(
            'Tesseract binary not found. '
            'Install from https://github.com/UB-Mannheim/tesseract/wiki — '
            'the student can type text manually in the review step.'
        )
        return ''

    except Exception as exc:
        logger.exception('Tesseract OCR failed: %s', exc)
        return ''
