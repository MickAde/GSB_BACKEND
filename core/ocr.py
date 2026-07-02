"""
OCR Engine — multi-strategy text extraction.

Strategy by note_type:
  pdf   → PyMuPDF  (text-based pages, fast and free)
          → AI Vision  (scanned/handwritten pages — uses configured AI provider)
          → Tesseract fallback  (if no AI key configured)
  image → AI Vision first  (handles pencil, children's handwriting, low contrast)
          → Tesseract fallback
  voice → AI transcription (uses AI_AUDIO_PROVIDER: openai Whisper or gemini)
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
        return _transcribe_audio(file_bytes)

    if note_type == 'pdf':
        return _extract_pdf(file_bytes)

    if note_type == 'image':
        return _extract_image(file_bytes)

    if note_type == 'doc':
        return _extract_doc(file_bytes)

    logger.warning('Unknown note_type "%s" — attempting generic AI extraction.', note_type)
    return _extract_doc(file_bytes)


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
    Send the image to the configured AI_VISION_PROVIDER for transcription.

    Set AI_VISION_PROVIDER in .env.local to choose the provider:
      anthropic  →  Claude Vision  (default)
      openai     →  GPT-4o Vision
      gemini     →  Gemini Vision

    Returns empty string if the provider is misconfigured or the call fails.
    """
    from django.conf import settings

    _provider_map = {
        'anthropic': ('ANTHROPIC_API_KEY', _anthropic_vision, 'Claude Vision'),
        'openai':    ('OPENAI_API_KEY',    _openai_vision,    'GPT-4o Vision'),
        'gemini':    ('GEMINI_API_KEY',    _gemini_vision,    'Gemini Vision'),
    }

    name = getattr(settings, 'AI_VISION_PROVIDER', 'anthropic').lower()
    entry = _provider_map.get(name)
    if not entry:
        logger.error(
            'Unknown AI_VISION_PROVIDER="%s". Valid options: anthropic, openai, gemini.', name
        )
        return ''

    key_attr, fn, label = entry
    if not getattr(settings, key_attr, ''):
        logger.error(
            'AI_VISION_PROVIDER=%s but %s is not set in your environment.', name, key_attr
        )
        return ''

    logger.info('Using %s for image transcription.', label)
    return fn(image_bytes)


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


# ── Audio transcription ───────────────────────────────────────

def _transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribe audio using the configured AI provider.

    Set AI_AUDIO_PROVIDER in .env.local to choose the provider:
      openai  →  Whisper  (default — best accuracy for speech-to-text)
      gemini  →  Gemini Audio

    Returns empty string if misconfigured; student can type manually.
    """
    from django.conf import settings

    _provider_map = {
        'openai': ('OPENAI_API_KEY', _whisper_transcribe, 'OpenAI Whisper'),
        'gemini': ('GEMINI_API_KEY', _gemini_audio_transcribe, 'Gemini Audio'),
    }

    name = getattr(settings, 'AI_AUDIO_PROVIDER', 'openai').lower()
    entry = _provider_map.get(name)
    if not entry:
        logger.error(
            'Unknown AI_AUDIO_PROVIDER="%s". Valid options: openai, gemini.', name
        )
        return ''

    key_attr, fn, label = entry
    if not getattr(settings, key_attr, ''):
        logger.error(
            'AI_AUDIO_PROVIDER=%s but %s is not set in your environment.', name, key_attr
        )
        return ''

    logger.info('Using %s for audio transcription.', label)
    return fn(audio_bytes)


def _detect_audio_mime(audio_bytes: bytes) -> tuple[str, str]:
    """Returns (mime_type, extension) detected from magic bytes."""
    if audio_bytes[:3] == b'ID3' or audio_bytes[:2] == b'\xff\xfb':
        return 'audio/mpeg', 'mp3'
    if audio_bytes[:4] == b'fLaC':
        return 'audio/flac', 'flac'
    if audio_bytes[:4] == b'OggS':
        return 'audio/ogg', 'ogg'
    if audio_bytes[:4] == b'RIFF':
        return 'audio/wav', 'wav'
    if audio_bytes[4:8] == b'ftyp':
        return 'audio/mp4', 'm4a'
    return 'audio/mpeg', 'mp3'  # safe default for Whisper


def _whisper_transcribe(audio_bytes: bytes) -> str:
    try:
        from openai import OpenAI
        from django.conf import settings

        mime, ext = _detect_audio_mime(audio_bytes)
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        transcript = client.audio.transcriptions.create(
            model='whisper-1',
            file=(f'audio.{ext}', audio_bytes, mime),
            response_format='text',
        )
        text = (transcript or '').strip()
        logger.info('Whisper transcribed %d chars.', len(text))
        return text
    except Exception as exc:
        logger.exception('Whisper transcription failed: %s', exc)
        return ''


def _gemini_audio_transcribe(audio_bytes: bytes) -> str:
    try:
        import google.generativeai as genai
        from django.conf import settings

        genai.configure(api_key=settings.GEMINI_API_KEY)
        mime, ext = _detect_audio_mime(audio_bytes)
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')

        # Gemini requires uploading the file first
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            audio_file = genai.upload_file(tmp_path, mime_type=mime)
            model    = genai.GenerativeModel(model_name)
            response = model.generate_content([
                'Transcribe this audio exactly as spoken. Output only the raw transcribed text — no summaries, no labels.',
                audio_file,
            ])
            text = (response.text or '').strip()
            logger.info('Gemini audio transcribed %d chars.', len(text))
            return text
        finally:
            os.unlink(tmp_path)

    except Exception as exc:
        logger.exception('Gemini audio transcription failed: %s', exc)
        return ''


# ── Document extraction (Word / PowerPoint / Excel / other) ──

def _extract_doc(file_bytes: bytes) -> str:
    """
    Extract text from office documents and arbitrary files.

    Strategy:
      1. Try python-docx  (.docx)
      2. Try python-pptx  (.pptx)
      3. Try openpyxl     (.xlsx)
      4. Try plain UTF-8 decode (CSV, code files, etc.)
      5. Fall back to AI Vision on first page rendered as image
    Each step is attempted silently; the first that returns text wins.
    """
    text = _try_docx(file_bytes)
    if text:
        return text

    text = _try_pptx(file_bytes)
    if text:
        return text

    text = _try_xlsx(file_bytes)
    if text:
        return text

    text = _try_plain_text(file_bytes)
    if text:
        return text

    logger.info('No structured extraction succeeded — sending to AI Vision.')
    return _vision_transcribe(file_bytes)


def _try_docx(file_bytes: bytes) -> str:
    try:
        import docx
        from io import BytesIO
        doc = docx.Document(BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = '\n'.join(paragraphs).strip()
        if text:
            logger.info('python-docx extracted %d chars.', len(text))
        return text
    except Exception:
        return ''


def _try_pptx(file_bytes: bytes) -> str:
    try:
        from pptx import Presentation
        from io import BytesIO
        prs = Presentation(BytesIO(file_bytes))
        lines = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        t = para.text.strip()
                        if t:
                            lines.append(t)
        text = '\n'.join(lines).strip()
        if text:
            logger.info('python-pptx extracted %d chars.', len(text))
        return text
    except Exception:
        return ''


def _try_xlsx(file_bytes: bytes) -> str:
    try:
        import openpyxl
        from io import BytesIO
        wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        lines = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    lines.append('\t'.join(cells))
        wb.close()
        text = '\n'.join(lines).strip()
        if text:
            logger.info('openpyxl extracted %d chars.', len(text))
        return text
    except Exception:
        return ''


def _try_plain_text(file_bytes: bytes) -> str:
    try:
        text = file_bytes.decode('utf-8').strip()
        if len(text) >= 10:
            logger.info('Plain UTF-8 decode extracted %d chars.', len(text))
            return text
        return ''
    except Exception:
        return ''


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
