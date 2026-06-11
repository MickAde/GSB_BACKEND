from django.conf import settings
from .base import AIProvider, SummaryResult, SearchResult

_BASE_URL = 'https://api.perplexity.ai'


class PerplexityProvider(AIProvider):
    """
    Perplexity AI — search + research with live citations.

    Uses the OpenAI-compatible client pointed at api.perplexity.ai.
    Also supports text summarisation via sonar models.
    """

    name = 'perplexity'

    def is_available(self) -> bool:
        return bool(getattr(settings, 'PERPLEXITY_API_KEY', ''))

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=settings.PERPLEXITY_API_KEY, base_url=_BASE_URL)

    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        model = getattr(settings, 'PERPLEXITY_MODEL', 'sonar')

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

    def search(self, query: str, **kwargs) -> SearchResult:
        """
        Run a grounded web search. Returns the answer with cited sources.

        Best used for: fact-checking, current-events questions, deep-dive research.
        The 'sonar' and 'sonar-pro' models include live web browsing.
        """
        model = getattr(settings, 'PERPLEXITY_MODEL', 'sonar')

        response = self._client().chat.completions.create(
            model=model,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are a precise research assistant. '
                        'Provide accurate, well-structured answers and cite every claim.'
                    ),
                },
                {'role': 'user', 'content': query},
            ],
        )
        answer = response.choices[0].message.content

        # Perplexity attaches citations on the response object when available
        citations = []
        raw_citations = getattr(response, 'citations', None)
        if raw_citations:
            citations = [{'url': url} for url in raw_citations]

        return SearchResult(
            answer=answer,
            citations=citations,
            provider=self.name,
            model=model,
        )
