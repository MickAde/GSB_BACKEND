import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SummaryResult:
    paragraph: str
    bullets: list[str]
    key_points: list[str]
    provider: str
    model: str


@dataclass
class ImageResult:
    url: str
    provider: str
    model: str
    revised_prompt: str = ''


@dataclass
class SearchResult:
    answer: str
    provider: str
    model: str
    citations: list[dict] = field(default_factory=list)


@dataclass
class ConformityResult:
    percentage: float
    analysis: str
    provider: str
    model: str


class AIProvider(ABC):
    """Abstract base for all AI provider implementations."""

    name: str = ''

    @abstractmethod
    def is_available(self) -> bool:
        """True when the required API key is present in settings."""
        ...

    @abstractmethod
    def generate_summary(self, text: str, subject_context: str = '') -> SummaryResult:
        """Produce a three-part educational summary (paragraph, bullets, key points)."""
        ...

    def generate_image(self, prompt: str, **kwargs) -> ImageResult:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support image generation. '
            f'Use "openai" (DALL-E 3) or "midjourney" instead.'
        )

    def search(self, query: str, **kwargs) -> SearchResult:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support web search. '
            f'Use "perplexity" for search tasks.'
        )

    def compare_notes(self, student_text: str, teacher_text: str, subject_context: str = '') -> ConformityResult:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support conformity analysis. '
            f'Use "anthropic", "openai", or "gemini" instead.'
        )

    # ── Shared utilities used by every text provider ──────────────

    def _build_summary_prompt(self, text: str, subject_context: str = '') -> str:
        ctx = f'Context — {subject_context}\n\n' if subject_context else ''
        return (
            'You are an expert educational assistant helping a student understand their notes.\n\n'
            f'{ctx}'
            'Analyse the following student notes and produce a structured summary with exactly three sections.\n\n'
            'Format your response using EXACTLY these section headers:\n\n'
            'PARAGRAPH_SUMMARY:\n'
            '<A single coherent paragraph of 3-5 sentences summarising the main ideas.>\n\n'
            'BULLET_SUMMARY:\n'
            '<5-10 bullet points, one per line, each starting with a dash (-).>\n\n'
            'KEY_LEARNING_POINTS:\n'
            '<3-7 core concepts the student must remember, one per line, each starting with a dash (-).>\n\n'
            f'Student Notes:\n---\n{text}\n---\n\n'
            'Important: Extract and summarise only what is in the notes. '
            'Do not add information not present in the notes.'
        )

    def _parse_summary_response(self, text: str) -> tuple[str, list[str], list[str]]:
        sections: dict[str, list[str]] = {
            'PARAGRAPH_SUMMARY': [],
            'BULLET_SUMMARY': [],
            'KEY_LEARNING_POINTS': [],
        }
        current = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            matched = False
            for key in sections:
                if stripped.startswith(key + ':') or stripped == key:
                    current = key
                    matched = True
                    break
            if not matched and current:
                sections[current].append(stripped)

        paragraph = ' '.join(sections['PARAGRAPH_SUMMARY']).strip()
        bullets = [l.lstrip('-').strip() for l in sections['BULLET_SUMMARY'] if l.lstrip('-').strip()]
        key_points = [l.lstrip('-').strip() for l in sections['KEY_LEARNING_POINTS'] if l.lstrip('-').strip()]
        return paragraph, bullets, key_points

    def _build_conformity_prompt(self, student_text: str, teacher_text: str, subject_context: str = '') -> str:
        ctx = f'Subject context: {subject_context}\n\n' if subject_context else ''
        return (
            'You are an educational quality-control assistant.\n'
            'Compare a student\'s notes against a teacher\'s reference material and evaluate '
            'how well the student captured the key information.\n\n'
            f'{ctx}'
            '--- TEACHER REFERENCE MATERIAL ---\n'
            f'{teacher_text}\n\n'
            '--- STUDENT NOTES ---\n'
            f'{student_text}\n\n'
            'Respond using EXACTLY these two section headers (no other text before them):\n\n'
            'CONFORMITY_PERCENTAGE:\n'
            '<A single integer from 0 to 100 — the conformity percentage.>\n\n'
            'SIMILARITY_ANALYSIS:\n'
            '<3-5 sentences: what the student captured well, what is missing, '
            'and one actionable improvement suggestion.>'
        )

    def _parse_conformity_response(self, text: str) -> tuple[float, str]:
        in_pct      = False
        in_analysis = False
        pct_lines: list[str]      = []
        analysis_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('CONFORMITY_PERCENTAGE:') or stripped == 'CONFORMITY_PERCENTAGE':
                in_pct      = True
                in_analysis = False
            elif stripped.startswith('SIMILARITY_ANALYSIS:') or stripped == 'SIMILARITY_ANALYSIS':
                in_pct      = False
                in_analysis = True
            elif in_pct:
                pct_lines.append(stripped)
            elif in_analysis:
                analysis_lines.append(stripped)

        pct_str = ' '.join(pct_lines).strip()
        match = re.search(r'(\d+(?:\.\d+)?)', pct_str)
        try:
            pct = float(match.group(1)) if match else 0.0
        except (ValueError, AttributeError):
            pct = 0.0
        pct = max(0.0, min(100.0, pct))

        analysis = ' '.join(analysis_lines).strip()
        return pct, analysis
