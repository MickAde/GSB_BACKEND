from django.conf import settings
from .base import AIProvider, ImageResult, LessonSuggestionResult, QuizResult, SummaryResult


class OpenAIProvider(AIProvider):
    """ChatGPT (text generation) + DALL-E 3 (image generation)."""

    name = 'openai'

    def is_available(self) -> bool:
        return bool(getattr(settings, 'OPENAI_API_KEY', ''))

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')

        response = self._client().chat.completions.create(
            model=model,
            max_tokens=1500,
            messages=[
                {'role': 'system', 'content': 'You are an expert educational assistant.'},
                {'role': 'user', 'content': self._build_summary_prompt(text, subject_context)},
            ],
        )
        raw = response.choices[0].message.content
        paragraph, bullets, key_points = self._parse_summary_response(raw)
        return SummaryResult(
            paragraph=paragraph,
            bullets=bullets,
            key_points=key_points,
            provider=self.name,
            model=model,
        )

    def compare_notes(self, student_text: str, teacher_text: str, subject_context: str = ''):
        from .base import ConformityResult
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
        response = self._client().chat.completions.create(
            model=model,
            max_tokens=1000,
            messages=[
                {'role': 'system', 'content': 'You are an educational quality-control assistant.'},
                {'role': 'user', 'content': self._build_conformity_prompt(student_text, teacher_text, subject_context)},
            ],
        )
        percentage, analysis = self._parse_conformity_response(response.choices[0].message.content)
        return ConformityResult(percentage=percentage, analysis=analysis, provider=self.name, model=model)

    def generate_quiz_questions(self, text: str, num_questions: int, difficulty: str) -> QuizResult:
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
        response = self._client().chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[
                {'role': 'system', 'content': 'You are an educational quiz creator. Return only valid JSON.'},
                {'role': 'user', 'content': self._build_quiz_prompt(text, num_questions, difficulty)},
            ],
        )
        questions = self._parse_quiz_response(response.choices[0].message.content)
        return QuizResult(questions=questions, provider=self.name, model=model)

    def generate_lesson_suggestions(self, plan_text: str, subject_context: str = '') -> LessonSuggestionResult:
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
        response = self._client().chat.completions.create(
            model=model,
            max_tokens=1500,
            messages=[
                {'role': 'system', 'content': 'You are an expert educational consultant.'},
                {'role': 'user', 'content': self._build_lesson_suggestions_prompt(plan_text, subject_context)},
            ],
        )
        return LessonSuggestionResult(
            suggestions=response.choices[0].message.content.strip(),
            provider=self.name,
            model=model,
        )

    def generate_image(self, prompt: str, **kwargs) -> ImageResult:
        model = getattr(settings, 'OPENAI_IMAGE_MODEL', 'dall-e-3')
        size = kwargs.get('size', '1024x1024')
        quality = kwargs.get('quality', 'standard')

        response = self._client().images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )
        item = response.data[0]
        return ImageResult(
            url=item.url,
            provider=self.name,
            model=model,
            revised_prompt=getattr(item, 'revised_prompt', '') or '',
        )
