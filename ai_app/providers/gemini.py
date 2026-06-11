from django.conf import settings
from .base import AIProvider, SummaryResult


class GeminiProvider(AIProvider):
    """Google Gemini — multimodal, Google Workspace integration."""

    name = 'gemini'

    def is_available(self) -> bool:
        return bool(getattr(settings, 'GEMINI_API_KEY', ''))

    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        import google.generativeai as genai

        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-pro-latest')
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name)

        response = model.generate_content(self._build_summary_prompt(text, subject_context))
        paragraph, bullets, key_points = self._parse_summary_response(response.text)
        return SummaryResult(
            paragraph=paragraph,
            bullets=bullets,
            key_points=key_points,
            provider=self.name,
            model=model_name,
        )
