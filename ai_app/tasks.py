import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)

# Minimum cosine similarity required to consider two notes as covering the same topic.
EMBEDDING_MATCH_THRESHOLD = 0.65


# ── Embedding helpers ─────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity — no numpy required."""
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _find_best_matching_note(source_note, candidate_qs):
    """
    Return the candidate note that best matches source_note semantically.

    Uses cosine similarity of stored embeddings when available.
    Falls back to returning the most recent candidate when:
    - source note has no embedding, OR
    - no candidate has an embedding yet (e.g. existing notes pre-migration)

    Cross-provider embeddings (openai 1536-dim vs gemini 768-dim) are skipped
    to prevent silently wrong similarity scores.
    """
    if not source_note.embedding:
        return candidate_qs.first()

    source_provider   = source_note.embedding_provider or ''
    best_note         = None
    best_score        = EMBEDDING_MATCH_THRESHOLD
    any_had_embedding = False

    for candidate in candidate_qs:
        if not candidate.embedding:
            continue
        # Skip cross-provider comparison — different dimensions give invalid scores
        cand_provider = candidate.embedding_provider or ''
        if source_provider and cand_provider and source_provider != cand_provider:
            continue
        any_had_embedding = True
        score = _cosine_similarity(source_note.embedding, candidate.embedding)
        if score > best_score:
            best_score = score
            best_note  = candidate

    # If no compatible candidates have been embedded yet, fall back to most-recent
    if not any_had_embedding:
        return candidate_qs.first()

    return best_note


def _notes_are_related(student_note, teacher_note) -> bool:
    """
    True when the two notes are semantically related enough for conformity grading.

    If neither has an embedding, falls back to subject-name comparison (or True
    if neither has a subject set, to preserve old behaviour).

    Cross-provider embeddings are never compared — falls through to subject matching.
    """
    if student_note.embedding and teacher_note.embedding:
        s_prov = student_note.embedding_provider or ''
        t_prov = teacher_note.embedding_provider or ''
        if s_prov and t_prov and s_prov != t_prov:
            # Incompatible dimensions — fall through to subject matching
            pass
        else:
            return _cosine_similarity(student_note.embedding, teacher_note.embedding) >= EMBEDDING_MATCH_THRESHOLD

    # Fallback: subject string match when embeddings aren't ready or are incompatible
    if student_note.subject and teacher_note.subject:
        return student_note.subject.strip().lower() == teacher_note.subject.strip().lower()

    return True  # can't determine — proceed and let the AI judge


# ── Conformity auto-trigger ───────────────────────────────────────────────────

def _auto_trigger_conformity(note):
    """
    Called after a note reaches READY status (and embedding has been generated).

    STUDENT note → find the best-matching READY teacher note in the same class
                   via embedding cosine similarity and queue a conformity report.

    TEACHER note → find all READY student notes in the same class that are
                   semantically related, and queue conformity reports for each.

    Skips if: no class assignment, or a report already exists for the pair.
    Subject field is used as a pre-filter hint when set, but matching is
    primarily driven by embedding similarity.
    """
    from notes.models import NoteUpload, NoteStatus, NoteConformityReport
    from users.models import UserRole

    if not note.owner_id:
        return

    try:
        owner = note.owner
    except Exception:
        return

    if not owner.student_class_id:
        return

    if owner.role == UserRole.STUDENT:
        # Candidate pool: all READY teacher notes in the same class
        teacher_qs = (
            NoteUpload.unscoped
            .filter(
                school=note.school,
                status=NoteStatus.READY,
                owner__role=UserRole.TEACHER,
                owner__student_class_id=owner.student_class_id,
            )
            .order_by('-created_at')
        )

        # Narrow by subject when the student provided one (efficiency hint only)
        if note.subject:
            narrowed = teacher_qs.filter(subject__iexact=note.subject)
            if narrowed.exists():
                teacher_qs = narrowed

        teacher_note = _find_best_matching_note(note, teacher_qs)
        if not teacher_note:
            logger.info('Auto-conformity: no matching teacher note found for student note %s', note.id)
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
                'Auto-conformity queued: student note %s vs teacher note %s (report %s, similarity-based)',
                note.id, teacher_note.id, report.id,
            )

    elif owner.role == UserRole.TEACHER:
        # When a teacher note is ready, back-fill all matching student notes
        student_qs = (
            NoteUpload.unscoped
            .filter(
                school=note.school,
                status=NoteStatus.READY,
                owner__role=UserRole.STUDENT,
                owner__student_class_id=owner.student_class_id,
            )
        )

        for student_note in student_qs:
            if not _notes_are_related(student_note, note):
                continue
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


# ── AI summary task ───────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    queue='celery_ai',
    name='ai_app.tasks.run_ai_summary',
)
def run_ai_summary(self, note_id: str, provider_name: str | None = None):
    """
    Generate a three-part AI summary for a confirmed student note.

    After the summary is saved (status → READY) this task also generates an
    embedding for the note so that _auto_trigger_conformity can use cosine
    similarity instead of subject-string matching.
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

        # Generate embedding for semantic topic matching, then auto-trigger conformity.
        note.refresh_from_db()
        try:
            from ai_app.integrations import generate_embedding_with_provider
            emb, emb_provider = generate_embedding_with_provider(note.raw_ocr_text)
            NoteUpload.unscoped.filter(pk=note_id).update(
                embedding=emb,
                embedding_provider=emb_provider,
            )
            note.embedding = emb
            note.embedding_provider = emb_provider
            logger.info(
                'Embedding generated for note %s via %s (%d dims)',
                note_id, emb_provider, len(emb),
            )
        except Exception as emb_exc:
            logger.warning(
                'Embedding generation failed for note %s — conformity will fall back to subject matching: %s',
                note_id, emb_exc,
            )

        try:
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


# ── Conformity analysis task ──────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    queue='celery_ai',
    name='ai_app.tasks.run_conformity_analysis',
)
def run_conformity_analysis(self, report_id: str, provider_name: str | None = None):
    """
    Generate a partial-scoring conformity report comparing student notes against
    only the corresponding portion of the teacher's master note (N_t').

    The AI identifies the student's stopping point, extracts the matching
    subset of the teacher's document, and scores only against that subset —
    so students are not penalised for content not yet taught in class.
    """
    from notes.models import NoteConformityReport, ConformityStatus

    try:
        report = NoteConformityReport.unscoped.select_related(
            'student_note', 'teacher_note', 'teacher_lesson_doc'
        ).get(pk=report_id)
    except NoteConformityReport.DoesNotExist:
        logger.error('Conformity task: NoteConformityReport %s not found.', report_id)
        return

    NoteConformityReport.unscoped.filter(pk=report_id).update(status=ConformityStatus.PROCESSING)
    logger.info('Conformity analysis starting for report %s', report_id)

    student_text = report.student_note.raw_ocr_text.strip()
    if report.teacher_note:
        teacher_text = report.teacher_note.raw_ocr_text.strip()
    elif report.teacher_lesson_doc:
        teacher_text = (report.teacher_lesson_doc.content_markdown or '').strip()
    else:
        teacher_text = ''

    if not student_text or not teacher_text:
        NoteConformityReport.unscoped.filter(pk=report_id).update(status=ConformityStatus.FAILED)
        logger.warning('Conformity task: empty note text for report %s', report_id)
        return

    try:
        from ai_app.integrations import compare_notes

        subject_context = ''
        subject_src = report.student_note.subject or (
            report.teacher_lesson_doc.subject if report.teacher_lesson_doc else ''
        )
        topic_src = report.student_note.topic or (
            report.teacher_lesson_doc.topic if report.teacher_lesson_doc else ''
        )
        if subject_src:
            subject_context = f'Subject: {subject_src}'
            if topic_src:
                subject_context += f' | Topic: {topic_src}'

        result = compare_notes(
            student_text=student_text,
            teacher_text=teacher_text,
            subject_context=subject_context,
            provider_name=provider_name,
        )

        from django.utils import timezone
        NoteConformityReport.unscoped.filter(pk=report_id).update(
            conformity_percentage=result.percentage,
            similarity_analysis=result.analysis,
            matched_teacher_section=result.matched_section,
            status=ConformityStatus.DONE,
            last_run_at=timezone.now(),
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
