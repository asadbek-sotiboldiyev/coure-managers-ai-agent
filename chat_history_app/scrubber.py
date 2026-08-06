"""
Maxfiylik uchun: xabarlar ichidagi haqiqiy ismlarni
assistant_id / student_id bilan almashtiradi.
"""
import re

from shared.models import AssistantInfo, StudentInfo


def build_name_patterns(assistant: AssistantInfo, student: StudentInfo) -> list[tuple[re.Pattern, str]]:
    """
    Ism qismlarini (ism, familiya alohida) topib almashtirish uchun pattern'lar.
    """
    patterns = []

    for name_part in assistant.full_name.split():
        if len(name_part) >= 2:
            patterns.append(
                (re.compile(rf"\b{re.escape(name_part)}\b", re.IGNORECASE), f"assistant_{assistant.assistant_id}")
            )

    for name_part in student.full_name.split():
        if len(name_part) >= 2:
            patterns.append(
                (re.compile(rf"\b{re.escape(name_part)}\b", re.IGNORECASE), f"student_{student.student_id}")
            )

    return patterns


def scrub_text(text: str, patterns: list[tuple[re.Pattern, str]]) -> str:
    """Matndagi barcha ism ko'rinishlarini ID bilan almashtiradi."""
    scrubbed = text
    for pattern, replacement in patterns:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed

