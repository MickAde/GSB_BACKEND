import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)



def _auto_trigger_conformity(note):
    """
    Called after a note reaches READY status.

    - STUDENT note  → find the teacher's READY reference note for the same
                      subject + class and auto-create a conformity report.
    - TEACHER note  → find every READY student note for that subject + class
                      and auto-create conformity reports for all of them.

    Skips if: no subject, no class assignment, or a report already exists.
    """
    from notes.models import NoteUpload, NoteStatus, NoteConformityReport
    from users.models import UserRole

    if not note.subject or not note.owner_id:
        return

    try:
        owner = note.owner
    except Exception:
        return

    if not owner.student_class_id:
        return

    if owner.role == UserRole.STUDENT:
        teacher_note = (
            NoteUpload.unscoped
            .filter(
                school=note.school,
                subject__iexact=note.subject,
                status=NoteStatus.READY,
                owner__role=UserRole.TEACHER,
                owner__student_class_id=owner.student_class_id,
            )
            .order_by('-created_at')
            .first()
        )
        if not teacher_note:
            return

        if not NoteConformityReport.unscoped.filter(
            student_note=note, teacher_note=teacher_note
        ).exists():
            report = NoteConformityReport.unscoped.create(
                school=note.school,
                student_note=note,
                teacher_note=teacher_note,
            )
            run_conformity_analysis.apply_async(args=[str(report.id)], queue='celery_ai')
            logger.info(
                'Auto-conformity queued: student note %s vs teacher note %s (report %s)',
                note.id, teacher_note.id, report.id,
            )

    elif owner.role == UserRole.TEACHER:
        student_notes = NoteUpload.unscoped.filter(
            school=note.school,
            subject__iexact=note.subject,
            status=NoteStatus.READY,
            owner__role=UserRole.STUDENT,
            owner__student_class_id=owner.student_class_id,
        )
        for student_note in student_notes:
            if not NoteConformityReport.unscoped.filter(
                student_note=student_note, teacher_note=note
            ).exists():
                report = NoteConformityReport.unscoped.create(
                    school=note.school,
                    student_note=student_note,
                    teacher_note=note,
                )
                run_conformity_analysis.apply_async(args=[str(report.id)], queue='celery_ai')
                logger.info(
                    'Auto-conformity queued: student note %s vs new teacher note %s (report %s)',
                    student_note.id, note.id, report.id,
                )


@shared_task(
    bind=True,
    max_retries=3,
    queue='celery_ai',
    name='ai_app.tasks.run_ai_summary',
)
def run_ai_summary(self, note_id: str, provider_name: str | None = None):
    """
    Generate a three-part AI summary for a confirmed student note.

    Uses the provider specified by `provider_name`, or falls back to
    settings.AI_DEFAULT_TEXT_PROVIDER (default: 'anthropic').

    The provider can be overridden per-task:
        run_ai_summary.apply_async(args=[note_id], kwargs={'provider_name': 'openai'})
    """
    from notes.models import NoteUpload, NoteStatus

    try:
        note = NoteUpload.unscoped.get(pk=note_id)
    except NoteUpload.DoesNotExist:
        logger.error('AI task: NoteUpload %s not found.', note_id)
        return

    if not note.raw_ocr_text.strip():
        NoteUpload.unscoped.filter(pk=note_id).update(
            status=NoteStatus.FAILED,
            error_message='No confirmed text to summarise.',
        )
        return

    logger.info('AI summary starting for note %s', note_id)

    try:
        from ai_app.integrations import summarize_notes

        subject_context = ''
        if note.subject:
            subject_context = f'Subject: {note.subject}'
            if note.topic:
                subject_context += f' | Topic: {note.topic}'
            if note.subtopic:
                subject_context += f' | Subtopic: {note.subtopic}'

        result = summarize_notes(
            text=note.raw_ocr_text,
            subject_context=subject_context,
            provider_name=provider_name,
        )

        NoteUpload.unscoped.filter(pk=note_id).update(
            ai_summary_paragraph=result.paragraph,
            ai_bullet_points=result.bullets,
            ai_key_points=result.key_points,
            status=NoteStatus.READY,
            error_message='',
        )

        logger.info(
            'AI summary complete for note %s via %s/%s (%d bullets, %d key points)',
            note_id, result.provider, result.model, len(result.bullets), len(result.key_points),
        )

        # Auto-trigger conformity analysis now that this note is READY.
        try:
            note.refresh_from_db()
            _auto_trigger_conformity(note)
        except Exception as exc:
            logger.warning('Auto-conformity trigger failed for note %s: %s', note_id, exc)

    except Exception as exc:
        logger.exception('AI summary failed for note %s: %s', note_id, exc)
        try:
            countdown = min(10 * 2 ** self.request.retries, 300)
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            from notes.models import NoteUpload, NoteStatus
            NoteUpload.unscoped.filter(pk=note_id).update(
                status=NoteStatus.FAILED,
                error_message=f'AI summary failed after {self.max_retries} retries: {exc}',
            )


@shared_task(
    bind=True,
    max_retries=3,
    queue='celery_ai',
    name='ai_app.tasks.run_conformity_analysis',
)
def run_conformity_analysis(self, report_id: str, provider_name: str | None = None):
    """
    Generate an AI conformity analysis comparing student notes to teacher reference material.

    Uses the provider specified by `provider_name`, or falls back to
    settings.AI_DEFAULT_TEXT_PROVIDER (default: 'anthropic').
    """
    from notes.models import NoteConformityReport, ConformityStatus

    try:
        report = NoteConformityReport.unscoped.select_related(
            'student_note', 'teacher_note'
        ).get(pk=report_id)
    except NoteConformityReport.DoesNotExist:
        logger.error('Conformity task: NoteConformityReport %s not found.', report_id)
        return

    NoteConformityReport.unscoped.filter(pk=report_id).update(status=ConformityStatus.PROCESSING)
    logger.info('Conformity analysis starting for report %s', report_id)

    student_text = report.student_note.raw_ocr_text.strip()
    teacher_text = report.teacher_note.raw_ocr_text.strip()

    if not student_text or not teacher_text:
        NoteConformityReport.unscoped.filter(pk=report_id).update(status=ConformityStatus.FAILED)
        logger.warning('Conformity task: empty note text for report %s', report_id)
        return

    try:
        from ai_app.integrations import compare_notes

        subject_context = ''
        if report.student_note.subject:
            subject_context = f'Subject: {report.student_note.subject}'
            if report.student_note.topic:
                subject_context += f' | Topic: {report.student_note.topic}'

        result = compare_notes(
            student_text=student_text,
            teacher_text=teacher_text,
            subject_context=subject_context,
            provider_name=provider_name,
        )

        NoteConformityReport.unscoped.filter(pk=report_id).update(
            conformity_percentage=result.percentage,
            similarity_analysis=result.analysis,
            status=ConformityStatus.DONE,
        )
        logger.info(
            'Conformity analysis complete for report %s: %.1f%% via %s/%s',
            report_id, result.percentage, result.provider, result.model,
        )

    except Exception as exc:
        logger.exception('Conformity analysis failed for report %s: %s', report_id, exc)
        try:
            countdown = min(10 * 2 ** self.request.retries, 300)
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            NoteConformityReport.unscoped.filter(pk=report_id).update(
                status=ConformityStatus.FAILED,
            )
