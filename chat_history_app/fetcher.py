"""
Pyrogram orqali assistant-student shaxsiy chat tarixini oladi.

Xavfsizlik: FloodWait exception'ni asyncio bilan to'g'ri qayta ishlaydi
(exponential-ish kutish + max retries).
"""
import asyncio
import builtins
import re
from datetime import datetime
from typing import Optional

from pyrogram.client import Client
from pyrogram.errors import FloodWait

from shared.config import tg_config, app_config
from shared.models import (
    AssistantInfo,
    StudentInfo,
    ChatMessage,
    ScrubbedChatHistory
)
from shared.logger import get_logger
from chat_history_app.tracking import get_last_check_date, update_last_check_date
from chat_history_app.scrubber import build_name_patterns, scrub_text

logger = get_logger(__name__)

def stop_interactive_login(*args, **kwargs):
    raise ConnectionError("Pyrogram sessiyasi eskirgan! Pipeline'da login qilish taqiqlangan.")
builtins.input = stop_interactive_login


async def _safe_pyrogram_call(coro_factory, max_retries: int | None = None):
    """
    FloodWait uchun umumiy retry wrapper.
    """
    max_retries = max_retries or app_config.flood_wait_max_retries
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except FloodWait as e:
            attempt += 1
            if attempt > max_retries:
                logger.error(f"FloodWait: max_retries ({max_retries}) tugadi, voz kechildi.")
                raise
            wait_time = e.value + 1
            logger.warning(f"FloodWait: {wait_time}s kutilmoqda (urinish {attempt}/{max_retries})")
            await asyncio.sleep(wait_time)


async def _resolve_chat_id_for_student(client: Client, student: StudentInfo) -> int | str:
    """
    Student_TG_Info yo'qligi sababli Telegram chat dialoglaridan studentni topadi.

    Asosiy usul: user.user_id_number kodi orqali qidirish. Chat title/ism odatda
    "ism familiya user_id_number" (masalan "ali valiyev 123456") ko'rinishida
    bo'ladi -- shu kod chat first_name/last_name/title ichidan alohida so'z
    sifatida qidiriladi. Kod topilmasa yoki mos kelmasa, eski ism bo'yicha
    qidiruvga zaxira (fallback) sifatida o'tiladi.
    """
    if student.tg_user_id:
        return student.tg_user_id

    target_code = (student.user_id_number or "").strip().lower()
    target_first = (student.first_name or "").strip().lower()
    target_last = (student.last_name or "").strip().lower()
    target_full = (student.full_name or "").strip().lower()

    fallback_chat_id: int | str | None = None

    try:
        async for dialog in client.get_dialogs(limit=200):
            chat = dialog.chat
            chat_first = (chat.first_name or "").strip().lower()
            chat_last = (chat.last_name or "").strip().lower()
            chat_title = (chat.title or f"{chat_first} {chat_last}").strip().lower()
            combined_text = f"{chat_title} {chat_first} {chat_last}".strip()

            if target_code:
                code_words = re.findall(r"\S+", combined_text)
                if target_code in code_words:
                    return chat.id

            if fallback_chat_id is None:
                if target_first and chat_first == target_first:
                    if not target_last or (chat_last and chat_last == target_last):
                        fallback_chat_id = chat.id

                if target_full and (chat_title == target_full or f"{chat_first} {chat_last}".strip() == target_full):
                    fallback_chat_id = chat.id
    except Exception as e:
        logger.warning(f"Dialoglarni qidirishda xato: {e}")

    if fallback_chat_id is not None:
        return fallback_chat_id

    return 0


async def fetch_chat_history_for_student(
    client: Client,
    assistant: AssistantInfo,
    student: StudentInfo,
    problem: str | None = None,
) -> Optional[ScrubbedChatHistory]:
    """
    Bitta assistant-student jufti uchun private chat tarixini oladi,
    ismlarni scrub qiladi, va chats_last_check ni yangilaydi.
    """
    last_check = get_last_check_date(assistant.assistant_id, student.student_id)
    last_check_date_only = last_check.date()
    patterns = build_name_patterns(assistant, student)

    messages: list[ChatMessage] = []
    chat_target = await _resolve_chat_id_for_student(client, student)

    if chat_target == 0:
        logger.warning(
            f"assistant={assistant.assistant_id} student={student.student_id}: chat topilmadi, o'tkazib yuborildi."
        )
        return None

    async def _get_history():
        result = []
        async for msg in client.get_chat_history(chat_target, limit=200):
            if not msg.text:
                continue
            result.append(msg)
        return result

    raw_messages = await _safe_pyrogram_call(_get_history)

    for msg in reversed(raw_messages):
        await asyncio.sleep(0)
        if msg.date.date() < last_check_date_only:
            continue
        sender_role = "assistant" if msg.from_user and assistant.tg_user_id and msg.from_user.id == assistant.tg_user_id else ("student" if msg.from_user else "unknown")
        scrubbed_text = scrub_text(msg.text, patterns)
        messages.append(
            ChatMessage(sender_role=sender_role, text=scrubbed_text, sent_at=msg.date)
        )

    update_last_check_date(assistant.assistant_id, student.student_id, checked_at=datetime.now())

    logger.info(
        f"assistant={assistant.assistant_id} student={student.student_id}: {len(messages)} ta yangi xabar olindi."
    )
    return ScrubbedChatHistory(
        assistant_id=assistant.assistant_id,
        student_id=student.student_id,
        messages=messages,
        last_check_date=last_check,
        problem=problem,
    )


async def fetch_all_histories_for_leader(
    assistant: AssistantInfo,
    students: list[StudentInfo],
    problems_by_student: dict[int, str] | None = None,
) -> list[ScrubbedChatHistory]:
    """
    Bitta assistant session'ini ochib, unga tegishli barcha studentlar
    bilan chatni ketma-ket oladi.
    """
    problems_by_student = problems_by_student or {}
    histories = []
    session_path = f"{tg_config.sessions_dir}/{assistant.tg_session_name}"

    try:
        async with Client(session_path, api_id=tg_config.api_id, api_hash=tg_config.api_hash) as client:
            for student in students:
                await asyncio.sleep(0)
                try:
                    problem = problems_by_student.get(student.student_id)
                    history = await fetch_chat_history_for_student(client, assistant, student, problem=problem)
                    if history is None:
                        continue
                    histories.append(history)
                except FloodWait:
                    logger.error(
                        f"FloodWait limitidan oshdi: assistant={assistant.assistant_id} student={student.student_id}, o'tkazib yuborildi."
                    )
                    continue
                except Exception as e:
                    logger.error(
                        f"Kutilmagan xato: assistant={assistant.assistant_id} student={student.student_id}: {e}"
                    )
                    continue

        return histories
    except Exception as e:
        logger.error(f"Assistant session ochishda xato: assistant={assistant.assistant_id}: {e}")
        return []


fetch_all_histories_for_assistant = fetch_all_histories_for_leader


