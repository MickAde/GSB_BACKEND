from django.conf import settings
from .base import AIProvider, ConformityResult, LessonDocumentResult, LessonSuggestionResult, QuizResult, SummaryResult


class GeminiProvider(AIProvider):
    """Google Gemini — multimodal, Google Workspace integration."""

    name = 'gemini'

    def is_available(self) -> bool:
        return bool(getattr(settings, 'GEMINI_API_KEY', ''))

    def _model(self, model_name: str):
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        return genai.GenerativeModel(model_name)

    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        response = self._model(model_name).generate_content(self._build_summary_prompt(text, subject_context))
        paragraph, bullets, key_points = self._parse_summary_response(response.text)
        return SummaryResult(
            paragraph=paragraph,
            bullets=bullets,
            key_points=key_points,
            provider=self.name,
            model=model_name,
        )

    def compare_notes(self, student_text: str, teacher_text: str, subject_context: str = '') -> ConformityResult:
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        response = self._model(model_name).generate_content(
            self._build_conformity_prompt(student_text, teacher_text, subject_context)
        )
        percentage, analysis = self._parse_conformity_response(response.text)
        return ConformityResult(percentage=percentage, analysis=analysis, provider=self.name, model=model_name)

    def generate_quiz_questions(self, text: str, num_questions: int, difficulty: str) -> QuizResult:
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        response = self._model(model_name).generate_content(self._build_quiz_prompt(text, num_questions, difficulty))
        questions = self._parse_quiz_response(response.text)
        return QuizResult(questions=questions, provider=self.name, model=model_name)

    def generate_lesson_suggestions(self, plan_text: str, subject_context: str = '') -> LessonSuggestionResult:
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        response = self._model(model_name).generate_content(
            self._build_lesson_suggestions_prompt(plan_text, subject_context)
        )
        return LessonSuggestionResult(
            suggestions=response.text.strip(),
            provider=self.name,
            model=model_name,
        )

    def generate_lesson_document(
        self, doc_type, curriculum_type, subject, topic, subtopic,
        class_level, term, week, additional_context='',
    ) -> LessonDocumentResult:
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        prompt = self._build_lesson_document_prompt(
            doc_type, curriculum_type, subject, topic, subtopic,
            class_level, term, week, additional_context,
        )
        response = self._model(model_name).generate_content(prompt)
        data = self._parse_lesson_document_response(response.text)
        return LessonDocumentResult(
            title=data.get('title', ''),
            content_markdown=data.get('content_markdown', ''),
            board_summary=data.get('board_summary', ''),
            diagnostic_cards=data.get('diagnostic_cards', []),
            resource_cards=data.get('resource_cards', []),
            provider=self.name,
            model=model_name,
        )

    def regenerate_section(
        self, full_markdown, section_heading, curriculum_type,
        subject, topic, class_level, instruction='',
    ) -> str:
        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        prompt = self._build_section_regeneration_prompt(
            full_markdown, section_heading, curriculum_type,
            subject, topic, class_level, instruction,
        )
        response = self._model(model_name).generate_content(prompt)
        return response.text.strip()
