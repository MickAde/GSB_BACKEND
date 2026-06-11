from django.conf import settings
from .base import AIProvider, SummaryResult, ImageResult


class MidjourneyProvider(AIProvider):
    """
    Midjourney — photorealistic and artistic image generation.

    STATUS: Midjourney does not yet have a stable public REST API.
    The official API is in closed alpha as of 2025.

    How to connect:
      Option A — Official alpha (invite only):
        Set MIDJOURNEY_API_BASE_URL to the endpoint they provide.

      Option B — Third-party proxy services (e.g. piapi.ai, useapi.net):
        Set MIDJOURNEY_API_BASE_URL to the proxy base URL.
        These services handle the Discord bot relay on your behalf.

    Both options use the same MIDJOURNEY_API_KEY + MIDJOURNEY_API_BASE_URL
    environment variables, so switching is a single env change.

    For image generation without Midjourney access, use:
        generate_image(..., provider_name='openai')   # DALL-E 3
    """

    name = 'midjourney'

    def is_available(self) -> bool:
        return bool(
            getattr(settings, 'MIDJOURNEY_API_KEY', '')
            and getattr(settings, 'MIDJOURNEY_API_BASE_URL', '')
        )

    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        raise NotImplementedError(
            'Midjourney is an image-generation model. '
            'Use "anthropic", "openai", "gemini", or "perplexity" for text tasks.'
        )

    def generate_image(self, prompt: str, **kwargs) -> ImageResult:
        """
        Submit an imagine request to the Midjourney API.

        Supported kwargs:
          aspect_ratio  str   e.g. '16:9', '1:1', '9:16'  (default '1:1')
          style         str   e.g. 'raw', 'expressive'     (default 'raw')
          quality       str   e.g. '1', '2'                (default '1')
        """
        import httpx

        base_url = settings.MIDJOURNEY_API_BASE_URL.rstrip('/')
        api_key = settings.MIDJOURNEY_API_KEY

        payload = {
            'prompt': prompt,
            'aspect_ratio': kwargs.get('aspect_ratio', '1:1'),
            'style': kwargs.get('style', 'raw'),
            'quality': kwargs.get('quality', '1'),
        }

        response = httpx.post(
            f'{base_url}/v1/imagine',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        url = data.get('url') or data.get('image_url') or data.get('imageUrl', '')
        return ImageResult(
            url=url,
            provider=self.name,
            model='midjourney',
            revised_prompt=data.get('revised_prompt', prompt),
        )
