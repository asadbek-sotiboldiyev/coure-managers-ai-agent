"""
ai_agent_app: Formatlangan chat tarixini (va unga tegishli progress muammosini)
LangChain + Gemini orqali tahlil qilib, strukturaviy InteractionReport qaytaradi.
"""
import asyncio

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from shared.config import ai_config
from shared.models import ScrubbedChatHistory, InteractionReport
from shared.logger import get_logger
from ai_agent_app.prompts import SYSTEM_PROMPT, build_user_prompt
from ai_agent_app.schema import InteractionAnalysis

logger = get_logger(__name__)

_llm = ChatGoogleGenerativeAI(
    model=ai_config.model,
    google_api_key=ai_config.google_api_key,
    temperature=ai_config.temperature,
    max_output_tokens=ai_config.max_tokens,
)

# Gemini javobini majburiy ravishda InteractionAnalysis strukturasiga moslaydi
_structured_llm = _llm.with_structured_output(InteractionAnalysis)


async def analyze_chat_history(history: ScrubbedChatHistory) -> InteractionReport:
    """
    Bitta assistant-student chat tarixini (va unga biriktirilgan progress
    muammosini) LangChain/Gemini orqali tahlil qiladi.
    Xato bo'lsa, xavfsiz default report qaytaradi (pipeline to'xtamasligi uchun).
    """
    chat_text = history.to_prompt_text()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_user_prompt(chat_text, problem=history.problem)),
    ]

    try:
        result: InteractionAnalysis = await _structured_llm.ainvoke(messages)
        return InteractionReport(
            assistant_id=history.assistant_id,
            student_id=history.student_id,
            support_quality_score=result.support_quality_score,
            addressed_issues=result.addressed_issues,
            discussed_flagged_problem=result.discussed_flagged_problem,
            summary=result.summary,
            recommendations=result.recommendations,
            problem=history.problem,
            raw_model_response=result.model_dump(),
            last_contacted_date=result.last_contacted_date if result.last_contacted_date != "" else None
        )
    except Exception as e:
        logger.error(
            f"AI tahlilida xato: assistant={history.assistant_id} student={history.student_id}: {e}"
        )
        return InteractionReport(
            assistant_id=history.assistant_id,
            student_id=history.student_id,
            support_quality_score=0,
            addressed_issues=False,
            discussed_flagged_problem=False,
            summary="Tahlil amalga oshmadi (texnik xato).",
            recommendations="Iltimos, keyinroq qayta urinib ko'ring.",
            problem=history.problem,
            raw_model_response=None,
            last_contacted_date=None
        )


