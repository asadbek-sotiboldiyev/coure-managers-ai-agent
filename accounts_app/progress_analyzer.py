"""
accounts_app: guruh progress snapshot'larini LangChain + Gemini orqali
tahlil qilib, muammoli studentlarni (StudentProblem) ajratib beradi.

Bu bosqich pipeline'ning birinchi AI-chaqiruvi: chat tarixi hali o'qilmagan,
faqat DB'dagi lesson/homework raqamlari asosida "kim orqada qolgan"ligini
aniqlaydi. Natija (muammoli studentlar) keyingi bosqichga (chat_history_app)
yo'naltiriladi.
"""
import asyncio
import json
from dataclasses import asdict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from shared.config import ai_config
from shared.models import GroupProgressSnapshot, StudentProblem
from shared.logger import get_logger
from accounts_app.progress_prompts import PROGRESS_SYSTEM_PROMPT, build_progress_user_prompt
from accounts_app.progress_schema import GroupProgressAnalysis

logger = get_logger(__name__)

_llm = ChatGoogleGenerativeAI(
    model=ai_config.model,
    google_api_key=ai_config.google_api_key,
    temperature=ai_config.temperature,
    max_output_tokens=ai_config.max_tokens,
)

# Gemini javobini majburiy ravishda GroupProgressAnalysis strukturasiga moslaydi
_structured_llm = _llm.with_structured_output(GroupProgressAnalysis)


async def analyze_group_progress(snapshot: GroupProgressSnapshot) -> list[StudentProblem]:
    """
    Bitta guruhning progress snapshot'ini AI'ga yuborib, har bir student uchun
    StudentProblem qaytaradi. AI chaqiruvi xato bo'lsa, shu guruh uchun bo'sh
    ro'yxat qaytariladi (pipeline to'xtamasligi uchun -- fault isolation).
    """
    await asyncio.sleep(0)
    
    if not snapshot.students:
        return []

    # DIQQAT: group_name (va boshqa har qanday nom) AI'ga QASDDAN yuborilmaydi --
    # faqat group_id (anonim identifikator) va studentlarning progress raqamlari ketadi.
    payload = {
        "group_id": snapshot.group_id,
        "students": [asdict(s) for s in snapshot.students],
    }
    group_json = json.dumps(payload, ensure_ascii=False)

    print("--- [stream] accounts_app/progress_analyzer: Progress tahlili uchun AI chaqiruvi ---")
    print(payload)

    messages = [
        SystemMessage(content=PROGRESS_SYSTEM_PROMPT),
        HumanMessage(content=build_progress_user_prompt(group_json)),
    ]

    try:
        result: GroupProgressAnalysis = await _structured_llm.ainvoke(messages)
        problems = [
            StudentProblem(
                student_id=r.student_id,
                group_id=snapshot.group_id,
                problem=r.problem.strip() if r.has_problem and r.problem.strip() else None,
            )
            for r in result.results
        ]
        found = sum(1 for p in problems if p.problem)
        logger.info(
            f"group={snapshot.group_id}: {found}/{len(problems)} ta studentda progress muammosi topildi."
        )
        return problems
    except Exception as e:
        logger.error(f"Progress tahlilida xato: group={snapshot.group_id}: {e}")
        return []


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
