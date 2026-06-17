from django.conf import settings
from .base import AIProvider, ConformityResult, LessonSuggestionResult, QuizResult, SummaryResult

OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'


def _client():
    from openai import OpenAI
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            'HTTP-Referer': 'https://geniusstudybuddy.com',
            'X-Title':      'Genius Study Buddy',
        },
    )


class OpenRouterProvider(AIProvider):
    """OpenRouter — OpenAI-compatible gateway to 200+ models."""

    name = 'openrouter'

    def is_available(self) -> bool:
        return bool(getattr(settings, 'OPENROUTER_API_KEY', ''))

    def _model(self) -> str:
        return getattr(settings, 'OPENROUTER_MODEL', 'google/gemini-2.0-flash-001')

    def _chat(self, prompt: str, max_tokens: int = 2000) -> str:
        response = _client().chat.completions.create(
            model=self._model(),
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return response.choices[0].message.content or ''

    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        raw = self._chat(self._build_summary_prompt(text, subject_context), max_tokens=1500)
        paragraph, bullets, key_points = self._parse_summary_response(raw)
        return SummaryResult(
            paragraph=paragraph,
            bullets=bullets,
            key_points=key_points,
            provider=self.name,
            model=self._model(),
        )

    def compare_notes(self, student_text: str, teacher_text: str, subject_context: str = '') -> ConformityResult:
        raw = self._chat(self._build_conformity_prompt(student_text, teacher_text, subject_context), max_tokens=1000)
        percentage, analysis = self._parse_conformity_response(raw)
        return ConformityResult(
            percentage=percentage,
            analysis=analysis,
            provider=self.name,
            model=self._model(),
        )

    def generate_quiz_questions(self, text: str, num_questions: int, difficulty: str) -> QuizResult:
        raw = self._chat(self._build_quiz_prompt(text, num_questions, difficulty), max_tokens=4096)
        questions = self._parse_quiz_response(raw)
        return QuizResult(questions=questions, provider=self.name, model=self._model())

    def generate_lesson_suggestions(self, plan_text: str, subject_context: str = '') -> LessonSuggestionResult:
        raw = self._chat(self._build_lesson_suggestions_prompt(plan_text, subject_context), max_tokens=1500)
        return LessonSuggestionResult(
            suggestions=raw.strip(),
            provider=self.name,
            model=self._model(),
        )
