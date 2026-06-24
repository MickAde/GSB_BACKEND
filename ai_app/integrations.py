"""
High-level AI integration functions for the GSB platform.

These are the functions the rest of the codebase (tasks, views, etc.) should
call — they handle provider selection, fallback, and error normalisation so
callers never need to touch the provider layer directly.

Provider selection order:
  1. Explicit provider_name argument (caller's choice)
  2. AI_DEFAULT_TEXT_PROVIDER / AI_DEFAULT_IMAGE_PROVIDER / AI_DEFAULT_SEARCH_PROVIDER setting
  3. Hard-coded fallback ('anthropic' / 'openai' / 'perplexity')

All functions raise RuntimeError when no configured provider is available.
"""

from __future__ import annotations

from django.conf import settings

from .providers import get_provider
from .providers.base import ConformityResult, ImageResult, LessonDocumentResult, LessonSuggestionResult, QuizResult, SearchResult, SummaryResult


def summarize_notes(
    text: str,
    subject_context: str = '',
    provider_name: str | None = None,
) -> SummaryResult:
    """
    Generate an educational three-part summary (paragraph + bullets + key points)
    from student note text.

    Best providers: anthropic (default), openai, gemini, perplexity.

    Args:
        text:             The confirmed OCR / typed student note content.
        subject_context:  Optional "Subject: X | Topic: Y" string for context.
        provider_name:    Override the default provider for this call.
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_TEXT_PROVIDER', 'anthropic')
    return get_provider(name).generate_summary(text, subject_context)


def generate_image(
    prompt: str,
    provider_name: str | None = None,
    **kwargs,
) -> ImageResult:
    """
    Generate an image from a text prompt.

    Best providers: openai (DALL-E 3, default), midjourney.

    Args:
        prompt:        Description of the image to generate.
        provider_name: Override the default provider for this call.
        **kwargs:      Provider-specific options (size, quality, aspect_ratio, etc.)
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_IMAGE_PROVIDER', 'openai')
    return get_provider(name).generate_image(prompt, **kwargs)


def research(
    query: str,
    provider_name: str | None = None,
    **kwargs,
) -> SearchResult:
    """
    Run a grounded web search and return a cited answer.

    Best provider: perplexity (default — returns live citations).

    Args:
        query:         The research question or search query.
        provider_name: Override the default provider for this call.
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_SEARCH_PROVIDER', 'perplexity')
    return get_provider(name).search(query, **kwargs)


def generate_quiz(
    text: str,
    num_questions: int,
    difficulty: str,
    provider_name: str | None = None,
) -> QuizResult:
    """
    Generate a set of MCQ + True/False quiz questions from student note text.

    Best providers: anthropic (default), openai, gemini.

    Args:
        text:          The confirmed OCR / typed note content.
        num_questions: How many questions to generate.
        difficulty:    'easy', 'moderate', or 'difficult'.
        provider_name: Override the default provider for this call.
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_TEXT_PROVIDER', 'anthropic')
    return get_provider(name).generate_quiz_questions(text, num_questions, difficulty)


def generate_lesson_suggestions(
    plan_text: str,
    subject_context: str = '',
    provider_name: str | None = None,
) -> LessonSuggestionResult:
    """
    Generate structured improvement suggestions for a teacher's lesson plan.

    Best providers: anthropic (default), openai, gemini.

    Args:
        plan_text:       The full lesson plan content as a string.
        subject_context: Optional "Subject: X | Topic: Y" string for context.
        provider_name:   Override the default provider for this call.
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_TEXT_PROVIDER', 'anthropic')
    return get_provider(name).generate_lesson_suggestions(plan_text, subject_context)


def generate_lesson_document(
    doc_type: str,
    curriculum_type: str,
    subject: str,
    topic: str,
    subtopic: str,
    class_level: str,
    term: int,
    week: int,
    additional_context: str = '',
    provider_name: str | None = None,
) -> LessonDocumentResult:
    """
    Generate a complete AI lesson document (plan or note) with diagnostic + resource cards.

    Best providers: anthropic (default), openai, gemini.

    Args:
        doc_type:           'plan' or 'note'
        curriculum_type:    'nerdc', 'british', 'american', 'blend_ng_uk', 'blend_ng_us'
        subject:            e.g. 'Biology'
        topic:              e.g. 'Photosynthesis'
        subtopic:           e.g. 'Light Reactions' (optional)
        class_level:        e.g. 'SSS 1'
        term:               1, 2, or 3
        week:               1–12
        additional_context: Extra teacher notes/instructions for the AI
        provider_name:      Override the default provider
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_TEXT_PROVIDER', 'anthropic')
    return get_provider(name).generate_lesson_document(
        doc_type=doc_type,
        curriculum_type=curriculum_type,
        subject=subject,
        topic=topic,
        subtopic=subtopic,
        class_level=class_level,
        term=term,
        week=week,
        additional_context=additional_context,
    )


def regenerate_lesson_section(
    full_markdown: str,
    section_heading: str,
    curriculum_type: str,
    subject: str,
    topic: str,
    class_level: str,
    instruction: str = '',
    provider_name: str | None = None,
) -> str:
    """
    Regenerate a single section of an existing lesson document.

    Args:
        full_markdown:   The complete current Markdown of the document (context).
        section_heading: The exact heading text to replace (e.g. '## Learning Objectives').
        curriculum_type: Curriculum key for rule enforcement.
        instruction:     Optional specific instruction from the teacher.
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_TEXT_PROVIDER', 'anthropic')
    return get_provider(name).regenerate_section(
        full_markdown=full_markdown,
        section_heading=section_heading,
        curriculum_type=curriculum_type,
        subject=subject,
        topic=topic,
        class_level=class_level,
        instruction=instruction,
    )


def compare_notes(
    student_text: str,
    teacher_text: str,
    subject_context: str = '',
    provider_name: str | None = None,
) -> ConformityResult:
    """
    Compare student notes against teacher reference material.
    Returns a conformity percentage (0-100) and a similarity analysis.

    Best providers: anthropic (default), openai, gemini.

    Args:
        student_text:    The student's confirmed OCR / typed note content.
        teacher_text:    The teacher's reference material text.
        subject_context: Optional "Subject: X | Topic: Y" string for context.
        provider_name:   Override the default provider for this call.
    """
    name = provider_name or getattr(settings, 'AI_DEFAULT_TEXT_PROVIDER', 'anthropic')
    return get_provider(name).compare_notes(student_text, teacher_text, subject_context)
