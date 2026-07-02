import json
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
    matched_section: str  # the N_t' portion of teacher note actually used for scoring
    provider: str
    model: str


@dataclass
class QuizResult:
    """List of question dicts ready to bulk-create as QuizQuestion records."""
    questions: list[dict]
    provider: str
    model: str


@dataclass
class LessonSuggestionResult:
    suggestions: str
    provider: str
    model: str


@dataclass
class LessonDocumentResult:
    """Full AI-generated lesson document with diagnostic + resource cards."""
    title:            str
    content_markdown: str
    board_summary:    str
    diagnostic_cards: list[dict]
    resource_cards:   list[dict]
    provider:         str
    model:            str


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

    def generate_embedding(self, text: str) -> list[float]:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support embedding generation. '
            f'Use "openai" (text-embedding-3-small) or "gemini" (text-embedding-004) instead.'
        )

    def compare_notes(self, student_text: str, teacher_text: str, subject_context: str = '') -> ConformityResult:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support conformity analysis. '
            f'Use "anthropic", "openai", or "gemini" instead.'
        )

    def generate_quiz_questions(self, text: str, num_questions: int, difficulty: str) -> QuizResult:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support quiz generation. '
            f'Use "anthropic", "openai", or "gemini" instead.'
        )

    def generate_lesson_suggestions(self, plan_text: str, subject_context: str = '') -> LessonSuggestionResult:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support lesson plan suggestions. '
            f'Use "anthropic", "openai", or "gemini" instead.'
        )

    def generate_lesson_document(
        self,
        doc_type: str,
        curriculum_type: str,
        subject: str,
        topic: str,
        subtopic: str,
        class_level: str,
        term: int,
        week: int,
        additional_context: str = '',
    ) -> LessonDocumentResult:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support lesson document generation. '
            f'Use "anthropic", "openai", or "gemini" instead.'
        )

    def regenerate_section(
        self,
        full_markdown: str,
        section_heading: str,
        curriculum_type: str,
        subject: str,
        topic: str,
        class_level: str,
        instruction: str = '',
    ) -> str:
        raise NotImplementedError(
            f'Provider "{self.name}" does not support section regeneration.'
        )

    # ── Lesson document prompt builders ──────────────────────────

    _CURRICULUM_RULES = {
        'nerdc': (
            'NERDC (Nigerian Educational Research and Development Council) curriculum.\n'
            '- Use Bloom\'s taxonomy action verbs ONLY for objectives: identify, state, list, name, describe, '
            'explain, define, compare, contrast, demonstrate, solve, apply, calculate, evaluate, analyse, synthesise, predict, justify.\n'
            '- Each learning objective must begin with a Bloom\'s verb and be measurable.\n'
            '- Use Nigerian currency ₦ in all money examples.\n'
            '- Use Nigerian names (e.g. Amaka, Emeka, Bola, Chidi, Ngozi, Yusuf) and local contexts.\n'
            '- Reference Nigerian foods (jollof rice, eba, egusi, yam), cities (Lagos, Abuja, Kano, Port Harcourt).\n'
        ),
        'british': (
            'British / Cambridge National Curriculum.\n'
            '- Reference KS3/KS4/KS5 key stages as appropriate for the class level.\n'
            '- Use British spellings (colour, analyse, practise, programme).\n'
            '- Include SEN/EAL differentiation strategies in lesson plans.\n'
            '- Use the KSU framework (Knowledge, Skills, Understanding) for objectives.\n'
            '- Reference Ofsted inspection criteria for lesson quality.\n'
            '- Include starter, main activity, and plenary structure.\n'
        ),
        'american': (
            'American Common Core Standards curriculum.\n'
            '- Align objectives to Common Core or NGSS standards where applicable.\n'
            '- Include formative assessment checkpoints throughout the lesson.\n'
            '- Use DOK (Depth of Knowledge) levels for differentiation.\n'
            '- Include bell-ringer/warm-up, instruction, guided practice, independent practice, closure.\n'
            '- Use American spellings and cultural references.\n'
        ),
        'blend_ng_uk': (
            'Nigeria-British Blend curriculum (NERDC base + British Cambridge elements).\n'
            '- Follow NERDC section structure and Nigerian context (names, ₦, local examples).\n'
            '- Also include dual assessment: WAEC-style questions AND IGCSE-style structured questions.\n'
            '- Use Bloom\'s verbs per NERDC, but also reference Cambridge Assessment Objectives.\n'
            '- Include SEN differentiation note (British element).\n'
        ),
        'blend_ng_us': (
            'Nigeria-American Blend curriculum (NERDC base + Common Core elements).\n'
            '- Follow NERDC section structure and Nigerian context (names, ₦, local examples).\n'
            '- Also include dual assessment: WAEC-style questions AND Common Core aligned questions.\n'
            '- Include formative checkpoints throughout (American element).\n'
        ),
    }

    # Required Markdown section structure per doc type — AI must follow this exactly.
    _PLAN_SECTIONS = (
        '## Learning Objectives\n'
        '## Entry Behaviour\n'
        '## Instructional Materials\n'
        '## Set Induction\n'
        '## Presentation\n'
        '## Generalisation\n'
        '## Evaluation\n'
        '## Assignment\n'
    )

    _NOTE_SECTIONS = (
        '## Introduction\n'
        '## Main Content\n'
        '## Worked Examples\n'
        '## Practice Exercises\n'
        '## Key Points Summary\n'
        '## Further Reading\n'
    )

    def _build_lesson_document_prompt(
        self,
        doc_type: str,
        curriculum_type: str,
        subject: str,
        topic: str,
        subtopic: str,
        class_level: str,
        term: int,
        week: int,
        additional_context: str = '',
    ) -> str:
        curriculum_rules = self._CURRICULUM_RULES.get(curriculum_type, self._CURRICULUM_RULES['nerdc'])
        is_plan    = doc_type == 'plan'
        doc_label  = 'Lesson Plan' if is_plan else 'Lesson Note'
        term_label = f'{term}{"st" if term == 1 else "nd" if term == 2 else "rd"} Term'
        ctx = f'\n\nAdditional teacher notes:\n{additional_context}' if additional_context.strip() else ''
        required_sections = self._PLAN_SECTIONS if is_plan else self._NOTE_SECTIONS

        if is_plan:
            doc_instructions = (
                'This is a LESSON PLAN — a structured teaching guide for the teacher to follow in class.\n'
                'It describes HOW to teach the lesson, not the lesson content itself.\n'
                'Focus on: objectives, activities, timing, teacher actions, student interactions, assessment.\n\n'
                f'REQUIRED SECTIONS (use exactly these ## headings in this order):\n{required_sections}\n'
                'Section guidance:\n'
                '- Learning Objectives: 3-5 measurable objectives using Bloom\'s taxonomy verbs.\n'
                '- Entry Behaviour: What students already know / prerequisite concepts.\n'
                '- Instructional Materials: List all materials, charts, equipment needed.\n'
                '- Set Induction: Engaging opening hook (real-life story, question, or demonstration).\n'
                '- Presentation: Step-by-step teaching sequence. Each step has Teacher Activity and Student Activity.\n'
                '- Generalisation: Key conclusions / general principles students should derive.\n'
                '- Evaluation: 4-6 assessment questions to check understanding.\n'
                '- Assignment: Homework task for students to complete after class.\n'
            )
        else:
            doc_instructions = (
                'This is a LESSON NOTE — a detailed content document covering the subject matter.\n'
                'It explains the topic thoroughly, provides examples, and includes practice questions.\n'
                'Focus on: clear explanations, real-world examples, step-by-step workings, exercises.\n\n'
                f'REQUIRED SECTIONS (use exactly these ## headings in this order):\n{required_sections}\n'
                'Section guidance:\n'
                '- Introduction: Brief overview of the topic and why it matters to students.\n'
                '- Main Content: Detailed, thorough explanation of the topic with sub-sections (### headings) for each concept.\n'
                '- Worked Examples: 3-5 fully solved problems or scenarios showing the concept in action.\n'
                '- Practice Exercises: 8-12 varied questions (easy → hard) for students to attempt.\n'
                '- Key Points Summary: Bullet-point recap of the essential facts, formulas, or definitions.\n'
                '- Further Reading: Books, topics, or areas for students who want to learn more.\n'
            )

        return (
            f'You are an expert {curriculum_type.upper()} curriculum designer creating a professional {doc_label}.\n\n'
            f'CURRICULUM RULES:\n{curriculum_rules}\n\n'
            f'DOCUMENT DETAILS:\n'
            f'- Type: {doc_label}\n'
            f'- Subject: {subject}\n'
            f'- Topic: {topic}\n'
            f'- Sub-topic: {subtopic or "N/A"}\n'
            f'- Class Level: {class_level}\n'
            f'- Term: {term_label}, Week {week}{ctx}\n\n'
            f'{doc_instructions}\n'
            'DIAGNOSTIC CARDS: Generate 3–6 diagnostic cards reviewing your own output.\n'
            '  Red (urgency="red"): compliance failures — missing mandatory sections, unmeasurable objectives, wrong currency.\n'
            '  Yellow (urgency="yellow"): improvement opportunities — better localisation, stronger hooks, richer examples.\n'
            '  Each card MUST have: {id, urgency, title, description, section (the exact ## heading text this card refers to), '
            'suggestion (one sentence of advice), suggested_content (REQUIRED — write the full improved Markdown text for that section that the teacher can apply directly; never null)}.\n\n'
            'RESOURCE CARDS: Generate 2–4 resource suggestions.\n'
            '  Types: "video", "textbook", "past_questions", "website".\n'
            '  Each card: {id, type, title, description, relevance}.\n'
            '  Note: do NOT include actual URLs — just describe the resource.\n\n'
            'Respond ONLY with valid JSON matching exactly this schema:\n'
            '{\n'
            '  "title": "string — descriptive document title",\n'
            '  "content_markdown": "string — full Markdown document",\n'
            '  "board_summary": "string — 2-3 sentence summary for the board/screen",\n'
            '  "diagnostic_cards": [...],\n'
            '  "resource_cards": [...]\n'
            '}\n'
            'CRITICAL JSON RULES — violations will cause a parse error:\n'
            '- Escape all backslashes as \\\\ (double backslash)\n'
            '- Escape all double quotes inside string values as \\"\n'
            '- Use \\n for line breaks inside string values — never literal newlines\n'
            '- Do not include any text, markdown fences, or comments outside the JSON object\n'
            '- The entire response must be parseable by json.loads() with no pre-processing'
        )

    def _build_section_regeneration_prompt(
        self,
        full_markdown: str,
        section_heading: str,
        curriculum_type: str,
        subject: str,
        topic: str,
        class_level: str,
        instruction: str = '',
    ) -> str:
        curriculum_rules = self._CURRICULUM_RULES.get(curriculum_type, self._CURRICULUM_RULES['nerdc'])
        extra = f'\nSpecific instruction: {instruction}' if instruction.strip() else ''
        return (
            f'You are an expert {curriculum_type.upper()} curriculum designer.\n'
            f'CURRICULUM RULES:\n{curriculum_rules}\n'
            f'Context: {subject} — {topic}, {class_level}\n\n'
            f'The teacher wants to regenerate only the section: "{section_heading}"\n'
            f'Here is the full document for context:\n\n{full_markdown}\n\n'
            f'Rewrite ONLY the "{section_heading}" section with improved, curriculum-compliant content.{extra}\n'
            'Return ONLY the new Markdown content for that section (from the heading line onwards, '
            'up to but not including the next heading). No JSON wrapping, no preamble.'
        )

    def _parse_lesson_document_response(self, raw: str) -> dict:
        if not raw:
            raise json.JSONDecodeError('Empty response from AI provider', '', 0)

        # Strip outer whitespace and BOM (byte-order mark Gemini sometimes emits)
        cleaned = raw.strip().lstrip('﻿')

        # Strip markdown fences wherever they appear — not just at position 0.
        # Handles cases like "Here is the plan:\n```json\n{...}\n```"
        if '```' in cleaned:
            first = cleaned.find('```')
            last  = cleaned.rfind('```')
            if first != last:          # at least two fence markers found
                between = cleaned[first + 3: last]
                lines   = between.splitlines()
                # First line may be a language tag like "json" — drop it
                if lines and re.match(r'^\s*[a-z]+\s*$', lines[0]):
                    between = '\n'.join(lines[1:])
                cleaned = between.strip()

        # Extract the JSON object — handles any preamble or postamble text
        # and the case where Gemini emits double-opening braces or stray chars.
        start = cleaned.find('{')
        end   = cleaned.rfind('}')
        if start >= 0 and end > start:
            cleaned = cleaned[start: end + 1]

        # Fast path — well-formed JSON
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Repair 1: lone backslashes not part of a valid JSON escape sequence.
        # Markdown often contains \n, \t, \( etc. that the AI forgets to double.
        repaired = re.sub(r'\\(?!["\\/bfnrtu0-9])', r'\\\\', cleaned)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Repair 2: literal control characters (real tabs / newlines) inside
        # string values — replace them with their JSON escape equivalents.
        repaired = re.sub(
            r'(?<=[^\\])([\x00-\x1f])',
            lambda m: {'\n': '\\n', '\r': '\\r', '\t': '\\t'}.get(m.group(1), ''),
            repaired,
        )
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(
                f'AI lesson document JSON could not be repaired '
                f'(original error at char {exc.pos}): {exc.msg}',
                exc.doc, exc.pos,
            ) from exc

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
            'You are an educational quality-control assistant evaluating a student\'s notes.\n\n'
            'CRITICAL RULE: The student may have only written a PORTION of the teacher\'s full '
            'notes because the teacher may still be covering this topic in class. '
            'You MUST NOT penalise the student for content that appears in the teacher\'s notes '
            'beyond what the student has uploaded — they have not been taught that part yet.\n\n'
            'Your task:\n'
            '1. Identify the LAST concept or section that appears in the student\'s notes (their "stopping point").\n'
            '2. Extract from the teacher\'s notes ONLY the content from the beginning up to and '
            'including that stopping point. This subset is called N_t\'.\n'
            '3. Score the student\'s notes ONLY against N_t\'. Ignore everything in the teacher\'s '
            'notes that comes after the stopping point.\n'
            '   Score formula: (content accurately captured by student / total content in N_t\') × 100\n\n'
            f'{ctx}'
            '--- TEACHER\'S MASTER NOTES (full document) ---\n'
            f'{teacher_text}\n\n'
            '--- STUDENT\'S NOTES (partial upload) ---\n'
            f'{student_text}\n\n'
            'Respond using EXACTLY these four section headers in this order '
            '(no other text before the first header):\n\n'
            'STOPPING_POINT:\n'
            '<One sentence identifying the last concept/section the student covered.>\n\n'
            'RELEVANT_TEACHER_SECTION:\n'
            '<Copy the exact text from the teacher\'s notes covering from the beginning up to '
            'and including the stopping point. This is N_t\'.>\n\n'
            'CONFORMITY_PERCENTAGE:\n'
            '<A single integer from 0 to 100.>\n\n'
            'SIMILARITY_ANALYSIS:\n'
            '<3-5 sentences: what the student captured well from the relevant section, '
            'what key points are missing from the relevant section, '
            'and one specific actionable improvement suggestion.>'
        )

    def _build_quiz_prompt(self, text: str, num_questions: int, difficulty: str) -> str:
        difficulty_guidance = {
            'easy':      'straightforward recall and basic understanding',
            'moderate':  'application and some analysis',
            'difficult': 'critical thinking, analysis, and synthesis',
        }.get(difficulty, 'application and some analysis')

        return (
            f'You are an educational quiz creator. Generate exactly {num_questions} quiz questions '
            f'from the student notes below. Difficulty level: {difficulty} ({difficulty_guidance}).\n\n'
            f'Mix multiple-choice questions (type: "MCQ") and true/false questions (type: "TF").\n'
            f'Aim for roughly 70% MCQ and 30% TF.\n\n'
            f'Return ONLY a valid JSON array. Each element must have exactly these fields:\n'
            '{\n'
            '  "type": "MCQ" or "TF",\n'
            '  "question": "question text",\n'
            '  "option_a": "first option",\n'
            '  "option_b": "second option",\n'
            '  "option_c": "third option (empty string for TF)",\n'
            '  "option_d": "fourth option (empty string for TF)",\n'
            '  "correct": "A", "B", "C", or "D",\n'
            '  "explanation": "brief explanation of why this is the correct answer"\n'
            '}\n\n'
            'For TF questions: option_a = "True", option_b = "False", option_c = "", option_d = ""\n'
            'Do not include any text before or after the JSON array.\n\n'
            f'Student Notes:\n---\n{text}\n---'
        )

    def _parse_quiz_response(self, raw: str) -> list[dict]:
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith('```'):
            lines = cleaned.splitlines()
            cleaned = '\n'.join(lines[1:])
            if cleaned.strip().endswith('```'):
                cleaned = cleaned.strip()[:-3].strip()
        return json.loads(cleaned)

    def _build_lesson_suggestions_prompt(self, plan_text: str, subject_context: str = '') -> str:
        ctx = f'Subject context: {subject_context}\n\n' if subject_context else ''
        return (
            'You are an expert educational consultant reviewing a teacher\'s lesson plan.\n'
            f'{ctx}'
            'Review the following lesson plan and provide structured improvement suggestions.\n\n'
            f'{plan_text}\n\n'
            'Provide feedback using EXACTLY these section headers:\n\n'
            'STRENGTHS:\n'
            '<2-3 bullet points starting with - on what the plan does well>\n\n'
            'IMPROVEMENTS:\n'
            '<3-5 specific, actionable bullet points starting with - on what to improve>\n\n'
            'TIPS:\n'
            '<2-3 practical teaching tips starting with - relevant to this topic>\n\n'
            'Keep feedback constructive, specific, and actionable. Do not rewrite the plan.'
        )

    def _parse_conformity_response(self, text: str) -> tuple[float, str, str]:
        in_stopping  = False
        in_section   = False
        in_pct       = False
        in_analysis  = False

        stopping_lines: list[str] = []
        section_lines:  list[str] = []
        pct_lines:      list[str] = []
        analysis_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('STOPPING_POINT:') or stripped == 'STOPPING_POINT':
                in_stopping = True; in_section = in_pct = in_analysis = False
            elif stripped.startswith('RELEVANT_TEACHER_SECTION:') or stripped == 'RELEVANT_TEACHER_SECTION':
                in_section = True; in_stopping = in_pct = in_analysis = False
            elif stripped.startswith('CONFORMITY_PERCENTAGE:') or stripped == 'CONFORMITY_PERCENTAGE':
                in_pct = True; in_stopping = in_section = in_analysis = False
            elif stripped.startswith('SIMILARITY_ANALYSIS:') or stripped == 'SIMILARITY_ANALYSIS':
                in_analysis = True; in_stopping = in_section = in_pct = False
            elif in_stopping:
                if stripped:
                    stopping_lines.append(stripped)
            elif in_section:
                section_lines.append(line)  # preserve original spacing for teacher section
            elif in_pct:
                if stripped:
                    pct_lines.append(stripped)
            elif in_analysis:
                if stripped:
                    analysis_lines.append(stripped)

        pct_str = ' '.join(pct_lines).strip()
        match = re.search(r'(\d+(?:\.\d+)?)', pct_str)
        try:
            pct = float(match.group(1)) if match else 0.0
        except (ValueError, AttributeError):
            pct = 0.0
        pct = max(0.0, min(100.0, pct))

        matched_section = '\n'.join(section_lines).strip()
        analysis = ' '.join(analysis_lines).strip()
        return pct, analysis, matched_section
