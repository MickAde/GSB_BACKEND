"""
Celery tasks for AI-driven lesson document generation.

Queue: celery_ai  (shares queue with quiz generation)
"""
import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue='celery_ai',
    name='teaching.tasks.generate_lesson_document',
)
def generate_lesson_document(self, lesson_doc_id: str) -> None:
    """
    Generate a full lesson document (plan or note) using AI.

    1. Fetches the LessonDocument record
    2. Reads the school's curriculum_type
    3. Calls the AI integration layer
    4. Saves title, content_markdown, board_summary, diagnostic_cards, resource_cards
    5. Sets status → DRAFT (ready to edit)
    On failure after retries: sets status → DRAFT with generation_error populated
    """
    from ai_app.integrations import generate_lesson_document as ai_generate
    from .models import LessonDocument, LessonDocumentStatus

    try:
        doc = LessonDocument.objects.select_related('school').get(pk=lesson_doc_id)
    except LessonDocument.DoesNotExist:
        logger.error('LessonDocument %s not found — skipping task.', lesson_doc_id)
        return

    curriculum_type = getattr(doc.school, 'curriculum_type', 'nerdc')

    try:
        result = ai_generate(
            doc_type=doc.doc_type,
            curriculum_type=curriculum_type,
            subject=doc.subject,
            topic=doc.topic,
            subtopic=doc.subtopic,
            class_level=doc.class_level,
            term=doc.term,
            week=doc.week,
            additional_context=doc.additional_context,
        )

        with transaction.atomic():
            doc.title            = result.title
            doc.content_markdown = result.content_markdown
            doc.board_summary    = result.board_summary
            doc.diagnostic_cards = result.diagnostic_cards
            doc.resource_cards   = result.resource_cards
            doc.status           = LessonDocumentStatus.DRAFT
            doc.generation_error = ''
            doc.save(update_fields=[
                'title', 'content_markdown', 'board_summary',
                'diagnostic_cards', 'resource_cards',
                'status', 'generation_error', 'updated_at',
            ])

        logger.info('LessonDocument %s generated successfully (%s provider).', lesson_doc_id, result.provider)

    except Exception as exc:
        logger.exception('LessonDocument %s generation failed: %s', lesson_doc_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            LessonDocument.objects.filter(pk=lesson_doc_id).update(
                status=LessonDocumentStatus.DRAFT,
                generation_error=str(exc),
                ai_task_id='',
            )


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    queue='celery_ai',
    name='teaching.tasks.regenerate_lesson_section',
)
def regenerate_lesson_section(
    self,
    lesson_doc_id: str,
    section_heading: str,
    instruction: str = '',
) -> dict:
    """
    Regenerate a single section of an existing lesson document.
    Returns the new section markdown (used by the view to return inline).
    """
    from ai_app.integrations import regenerate_lesson_section as ai_regen
    from .models import LessonDocument

    try:
        doc = LessonDocument.objects.select_related('school').get(pk=lesson_doc_id)
    except LessonDocument.DoesNotExist:
        logger.error('LessonDocument %s not found for section regen.', lesson_doc_id)
        return {'error': 'Not found'}

    curriculum_type = getattr(doc.school, 'curriculum_type', 'nerdc')

    try:
        new_section = ai_regen(
            full_markdown=doc.content_markdown,
            section_heading=section_heading,
            curriculum_type=curriculum_type,
            subject=doc.subject,
            topic=doc.topic,
            class_level=doc.class_level,
            instruction=instruction,
        )
        return {'section_heading': section_heading, 'new_content': new_section}

    except Exception as exc:
        logger.exception('Section regen failed for %s: %s', lesson_doc_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'error': str(exc)}
