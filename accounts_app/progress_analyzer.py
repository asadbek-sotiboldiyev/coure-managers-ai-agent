"""
accounts_app: guruh progress snapshot'larini tahlil qilib, muammoli
studentlarni (StudentProblem) ajratib beradi.

Bu bosqich pipeline'ning birinchi tekshiruvi: chat tarixi hali o'qilmagan,
faqat DB'dagi lesson/homework raqamlari asosida "kim orqada qolgan"ligini
aniqlaydi. Qoida oddiy: hozirgi darsgacha (current_lesson_number) necha
ta homework berilishi kerak bo'lsa, shundan kamida 2 tasi yuklanmagan
bo'lsa -- student muammoli deb topiladi. Natija (muammoli studentlar)
keyingi bosqichga (chat_history_app) yo'naltiriladi.
"""
import asyncio

from shared.models import GroupProgressSnapshot, StudentProblem
from shared.logger import get_logger

logger = get_logger(__name__)

# Hozirgi darsgacha kamida shuncha homework yuklanmagan bo'lsa muammo deb topiladi
_MIN_MISSING_HOMEWORKS_FOR_PROBLEM = 2


async def analyze_group_progress(snapshot: GroupProgressSnapshot) -> list[StudentProblem]:
    """
    Bitta guruhning progress snapshot'ini qoida asosida tahlil qilib, har bir
    student uchun StudentProblem qaytaradi. AI ishlatilmaydi -- hozirgi
    darsgacha kerak bo'lgan homeworklar sonidan kamida
    `_MIN_MISSING_HOMEWORKS_FOR_PROBLEM` tasi kam yuklangan bo'lsa muammoli
    deb topiladi.
    """
    await asyncio.sleep(0)

    if not snapshot.students:
        return []

    current_lesson_number = (
        snapshot.progress_info.current_lesson_number if snapshot.progress_info else None
    )
    if not current_lesson_number:
        logger.warning(
            f"group={snapshot.group_id}: current_lesson_number aniqlanmadi, "
            "progress tekshiruvi o'tkazib yuborildi (bo'sh ro'yxat)."
        )
        return []

    problems: list[StudentProblem] = []
    for s in snapshot.students:
        missing_count = current_lesson_number - (s.uploaded_homeworks_count or 0)
        has_problem = missing_count >= _MIN_MISSING_HOMEWORKS_FOR_PROBLEM
        problems.append(
            StudentProblem(
                student_id=s.student_id,
                group_id=snapshot.group_id,
                problem=(
                    f"Hozirgi darsgacha ({current_lesson_number}) {missing_count} ta "
                    "uy vazifasi yuklanmagan."
                    if has_problem
                    else None
                ),
            )
        )

    found = sum(1 for p in problems if p.problem)
    logger.info(
        f"group={snapshot.group_id}: {found}/{len(problems)} ta studentda progress muammosi topildi."
    )
    return problems


async def analyze_group_progress_batch(
    snapshots: list[GroupProgressSnapshot],
) -> list[StudentProblem]:
    """Bir nechta guruh snapshot'ini parallel tahlil qiladi, natijalarni birlashtiradi."""

    all_problems: list[StudentProblem] = []
    for s in snapshots:
        problems = await analyze_group_progress(s)
        all_problems.extend(problems)
        await asyncio.sleep(4)
    return all_problems


def only_with_problem(problems: list[StudentProblem]) -> list[StudentProblem]:
    """Faqat aniq muammo topilgan (problem != None) studentlarni qoldiradi."""
    return [p for p in problems if p.problem]
