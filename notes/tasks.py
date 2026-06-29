import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    queue='celery_ocr',
    name='notes.tasks.run_ocr_pipeline',
)
def run_ocr_pipeline(self, note_id: str):
    """
    Downloads the uploaded file from storage, extracts raw text via OCR,
    and advances the note to AWAITING_STUDENT_APPROVAL.

    The PRD requires:
    - Raw extracted text ONLY — no AI interpretation at this stage.
    - Student must review, correct errors, and confirm before AI proceeds.
    """
    from .models import NoteUpload, NoteStatus

    try:
        note = NoteUpload.unscoped.select_related('owner').get(pk=note_id)
    except NoteUpload.DoesNotExist:
        logger.error('OCR task: NoteUpload %s not found.', note_id)
        return

    logger.info('OCR pipeline starting for note %s (type=%s)', note_id, note.note_type)

    try:
        file_bytes = _download_file(note.file_url)

        if not file_bytes:
            logger.warning('Note %s: file could not be downloaded, proceeding with empty OCR.', note_id)
            raw_text = ''
        else:
            from core.ocr import extract_text
            raw_text = extract_text(file_bytes, note.note_type)

        note.raw_ocr_text = raw_text
        note.status = NoteStatus.AWAITING_APPROVAL
        note.save(update_fields=['raw_ocr_text', 'status', 'updated_at'])

        logger.info('OCR complete for note %s — extracted %d chars.', note_id, len(raw_text))

    except Exception as exc:
        logger.exception('OCR failed for note %s: %s', note_id, exc)
        try:
            # Exponential backoff: 10s, 20s, 40s (capped at 300s).
            countdown = min(10 * 2 ** self.request.retries, 300)
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            NoteUpload.unscoped.filter(pk=note_id).update(
                status=NoteStatus.FAILED,
                error_message=f'OCR failed after {self.max_retries} retries: {exc}',
            )


def _download_file(file_url: str) -> bytes | None:
    """Fetches raw file bytes from Supabase Storage (authenticated) or local media path."""
    if not file_url:
        return None

    from django.conf import settings

    if file_url.startswith('http'):
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            # Use the authenticated Supabase client — required for private buckets.
            # Unauthenticated urlopen would get a 403 on private storage.
            try:
                from core.storage import storage
                parts = file_url.split(f'/{settings.SUPABASE_NOTES_BUCKET}/')
                if len(parts) != 2:
                    logger.error('Cannot parse Supabase path from URL: %s', file_url)
                    return None
                return storage.download(settings.SUPABASE_NOTES_BUCKET, parts[1])
            except Exception as exc:
                logger.error('Failed to download from Supabase %s: %s', file_url, exc)
                return None
        else:
            # Dev fallback: no Supabase configured, attempt unauthenticated fetch.
            import urllib.request
            try:
                with urllib.request.urlopen(file_url, timeout=30) as resp:
                    return resp.read()
            except Exception as exc:
                logger.error('Failed to download %s: %s', file_url, exc)
                return None

    # Strip MEDIA_URL prefix so we get the path relative to MEDIA_ROOT.
    # default_storage.url() returns e.g. '/media/notes/uuid-file.pdf';
    # prepending MEDIA_ROOT would double the 'media/' segment.
    from django.core.files.storage import default_storage
    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    relative = file_url[len(media_url):] if file_url.startswith(media_url) else file_url.lstrip('/')
    try:
        with default_storage.open(relative, 'rb') as fh:
            return fh.read()
    except Exception as exc:
        logger.error('Failed to read local file "%s": %s', relative, exc)
        return None
