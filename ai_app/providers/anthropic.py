from django.conf import settings
from .base import AIProvider, ConformityResult, LessonDocumentResult, LessonSuggestionResult, QuizResult, SummaryResult


class AnthropicProvider(AIProvider):
    """Claude — long-form analysis, coding, creative writing."""

    name = 'anthropic'

    def is_available(self) -> bool:
        return bool(getattr(settings, 'ANTHROPIC_API_KEY', ''))

    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        import anthropic

        model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6')
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        message = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{'role': 'user', 'content': self._build_summary_prompt(text, subject_context)}],
        )
        paragraph, bullets, key_points = self._parse_summary_response(message.content[0].text)
        return SummaryResult(
            paragraph=paragraph,
            bullets=bullets,
            key_points=key_points,
            provider=self.name,
            model=model,
        )

    def compare_notes(self, student_text: str, teacher_text: str, subject_context: str = '') -> ConformityResult:
        import anthropic

        model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6')
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        message = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{'role': 'user', 'content': self._build_conformity_prompt(student_text, teacher_text, subject_context)}],
        )
        percentage, analysis, matched_section = self._parse_conformity_response(message.content[0].text)
        return ConformityResult(
            percentage=percentage,
            analysis=analysis,
            matched_section=matched_section,
            provider=self.name,
            model=model,
        )

    def generate_quiz_questions(self, text: str, num_questions: int, difficulty: str) -> QuizResult:
        import anthropic

        model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6')
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{'role': 'user', 'content': self._build_quiz_prompt(text, num_questions, difficulty)}],
        )
        questions = self._parse_quiz_response(message.content[0].text)
        return QuizResult(questions=questions, provider=self.name, model=model)

    def generate_lesson_suggestions(self, plan_text: str, subject_context: str = '') -> LessonSuggestionResult:
        import anthropic

        model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6')
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        message = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{'role': 'user', 'content': self._build_lesson_suggestions_prompt(plan_text, subject_context)}],
        )
        return LessonSuggestionResult(
            suggestions=message.content[0].text.strip(),
            provider=self.name,
            model=model,
        )

    def generate_lesson_document(
        self, doc_type, curriculum_type, subject, topic, subtopic,
        class_level, term, week, additional_context='',
    ) -> LessonDocumentResult:
        import anthropic

        model  = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6')
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = self._build_lesson_document_prompt(
            doc_type, curriculum_type, subject, topic, subtopic,
            class_level, term, week, additional_context,
        )
        message = client.messages.create(
            model=model,
            max_tokens=16000,
            messages=[{'role': 'user', 'content': prompt}],
        )
        data = self._parse_lesson_document_response(message.content[0].text)
        return LessonDocumentResult(
            title=data.get('title', ''),
            content_markdown=data.get('content_markdown', ''),
            board_summary=data.get('board_summary', ''),
            diagnostic_cards=data.get('diagnostic_cards', []),
            resource_cards=data.get('resource_cards', []),
            provider=self.name,
            model=model,
        )

    def regenerate_section(
        self, full_markdown, section_heading, curriculum_type,
        subject, topic, class_level, instruction='',
    ) -> str:
        import anthropic

        model  = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-6')
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = self._build_section_regeneration_prompt(
            full_markdown, section_heading, curriculum_type,
            subject, topic, class_level, instruction,
        )
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return message.content[0].text.strip()
