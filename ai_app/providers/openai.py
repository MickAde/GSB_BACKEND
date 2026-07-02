from django.conf import settings
from .base import AIProvider, ConformityResult, ImageResult, LessonDocumentResult, LessonSuggestionResult, QuizResult, SummaryResult


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

    def generate_embedding(self, text: str) -> list[float]:
        response = self._client().embeddings.create(
            model='text-embedding-3-small',
            input=text[:8000],
        )
        return response.data[0].embedding

    def compare_notes(self, student_text: str, teacher_text: str, subject_context: str = '') -> ConformityResult:
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
        response = self._client().chat.completions.create(
            model=model,
            max_tokens=2000,
            messages=[
                {'role': 'system', 'content': 'You are an educational quality-control assistant.'},
                {'role': 'user', 'content': self._build_conformity_prompt(student_text, teacher_text, subject_context)},
            ],
        )
        percentage, analysis, matched_section = self._parse_conformity_response(response.choices[0].message.content)
        return ConformityResult(percentage=percentage, analysis=analysis, matched_section=matched_section, provider=self.name, model=model)

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

    def generate_lesson_document(
        self, doc_type, curriculum_type, subject, topic, subtopic,
        class_level, term, week, additional_context='',
    ) -> LessonDocumentResult:
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
        prompt = self._build_lesson_document_prompt(
            doc_type, curriculum_type, subject, topic, subtopic,
            class_level, term, week, additional_context,
        )
        response = self._client().chat.completions.create(
            model=model,
            max_tokens=16000,
            messages=[
                {'role': 'system', 'content': 'You are an expert curriculum designer. Return only valid JSON.'},
                {'role': 'user', 'content': prompt},
            ],
        )
        data = self._parse_lesson_document_response(response.choices[0].message.content)
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
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
        prompt = self._build_section_regeneration_prompt(
            full_markdown, section_heading, curriculum_type,
            subject, topic, class_level, instruction,
        )
        response = self._client().chat.completions.create(
            model=model,
            max_tokens=2048,
            messages=[
                {'role': 'system', 'content': 'You are an expert curriculum designer.'},
                {'role': 'user', 'content': prompt},
            ],
        )
        return (response.choices[0].message.content or '').strip()

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
