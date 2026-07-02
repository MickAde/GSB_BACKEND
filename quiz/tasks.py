import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    queue='celery_ai',
    name='quiz.tasks.generate_quiz_questions',
)
def generate_quiz_questions(self, quiz_id: str, provider_name: str | None = None):
    """
    Generate quiz questions from a note's OCR text via AI.

    Bulk-creates QuizQuestion records and advances the quiz to READY.
    Uses celery_ai queue (same as AI summary generation).
    """
    from .models import Quiz, QuizQuestion, QuizStatus

    try:
        quiz = Quiz.unscoped.select_related('note', 'lesson_doc').get(pk=quiz_id)
    except Quiz.DoesNotExist:
        logger.error('Quiz task: Quiz %s not found.', quiz_id)
        return

    # Idempotency: if a previous retry already created questions but failed to
    # commit the status update, just mark READY and return.
    if quiz.questions.exists():
        logger.warning('Quiz %s already has questions — marking READY (retry idempotency).', quiz_id)
        Quiz.unscoped.filter(pk=quiz_id).update(status=QuizStatus.READY, error_message='')
        return

    note_text = quiz.note.raw_ocr_text.strip()
    if not note_text:
        Quiz.unscoped.filter(pk=quiz_id).update(
            status=QuizStatus.FAILED,
            error_message='Note has no OCR text to generate questions from.',
        )
        return

    # When a teacher lesson doc is attached (high conformity path), combine both
    # sources so the AI generates questions that bridge student notes and official content.
    if quiz.lesson_doc_id and quiz.lesson_doc:
        teacher_content = quiz.lesson_doc.content_markdown.strip()
        if teacher_content:
            text_to_use = (
                f"STUDENT NOTES:\n{note_text}"
                f"\n\n---\n\nTEACHER LESSON NOTE:\n{teacher_content}"
            )
            logger.info('Quiz %s will use combined student+teacher content (%d chars).', quiz_id, len(text_to_use))
        else:
            text_to_use = note_text
    else:
        text_to_use = note_text

    logger.info('Quiz generation starting for quiz %s (%s, %s)', quiz_id, quiz.difficulty, quiz.num_questions)

    try:
        from ai_app.integrations import generate_quiz

        result = generate_quiz(
            text=text_to_use,
            num_questions=quiz.num_questions,
            difficulty=quiz.difficulty,
            provider_name=provider_name,
        )

        questions_to_create = []
        for i, q in enumerate(result.questions):
            q_type = q.get('type', 'MCQ').upper()
            if q_type not in ('MCQ', 'TF'):
                q_type = 'MCQ'
            questions_to_create.append(QuizQuestion(
                quiz_id=quiz_id,
                order=i + 1,
                question_type=q_type,
                question_text=q.get('question', ''),
                option_a=q.get('option_a', ''),
                option_b=q.get('option_b', ''),
                option_c=q.get('option_c', ''),
                option_d=q.get('option_d', ''),
                correct=(q.get('correct') or 'A').upper()[:1],
                explanation=q.get('explanation', ''),
            ))

        # Wrap in atomic so a transient DB error rolls back BOTH the questions
        # AND the status update together — keeping retry safe (no duplicate questions).
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            QuizQuestion.objects.bulk_create(questions_to_create)
            Quiz.unscoped.filter(pk=quiz_id).update(
                status=QuizStatus.READY,
                error_message='',
            )

        logger.info(
            'Quiz generation complete for %s via %s/%s — %d questions created.',
            quiz_id, result.provider, result.model, len(questions_to_create),
        )

    except Exception as exc:
        logger.exception('Quiz generation failed for %s: %s', quiz_id, exc)
        try:
            countdown = min(10 * 2 ** self.request.retries, 300)
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            Quiz.unscoped.filter(pk=quiz_id).update(
                status=QuizStatus.FAILED,
                error_message=f'Quiz generation failed after {self.max_retries} retries: {exc}',
            )
