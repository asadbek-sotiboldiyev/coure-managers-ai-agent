"""
chats_last_check jadvali (lokal SQLite) bilan ishlash: oxirgi tekshiruv
sanasini o'qish va yangilash.
"""
from datetime import datetime, timedelta
from typing import Optional

from shared.local_db import get_local_connection
from shared.config import app_config
from shared.logger import get_logger

logger = get_logger(__name__)


def get_last_check_date(assistant_id: int, student_id: int) -> datetime:
    """
    Berilgan assistant-student jufti uchun oxirgi tekshiruv sanasini qaytaradi.
    Yozuv topilmasa, fallback sifatida N kun oldingi sanani qaytaradi.
    """
    query = """
    SELECT last_check_date FROM chats_last_check
    WHERE assistant_id = ? AND student_id = ?
    """
    with get_local_connection() as conn:
        cursor = conn.execute(query, (assistant_id, student_id))
        row = cursor.fetchone()

    if row and row["last_check_date"]:
        return datetime.fromisoformat(row["last_check_date"])

    fallback = datetime.now() - timedelta(days=app_config.fetch_days_fallback)
    logger.info(
        f"assistant={assistant_id} student={student_id} uchun tarix topilmadi, "
        f"fallback: {fallback.isoformat()}"
    )
    return fallback


def update_last_check_date(assistant_id: int, student_id: int, checked_at: Optional[datetime] = None) -> None:
    """
    Upsert: yozuv bor bo'lsa yangilaydi, yo'q bo'lsa qo'shadi
    (SQLite'ning INSERT ... ON CONFLICT DO UPDATE mexanizmi orqali).
    """
    checked_at = checked_at or datetime.now()
    query = """
    INSERT INTO chats_last_check (assistant_id, student_id, last_check_date)
    VALUES (?, ?, ?)
    ON CONFLICT (assistant_id, student_id)
    DO UPDATE SET last_check_date = excluded.last_check_date
    """
    with get_local_connection() as conn:
        conn.execute(query, (assistant_id, student_id, checked_at.isoformat()))
        conn.commit()
    logger.debug(f"last_check_date yangilandi: assistant={assistant_id} student={student_id}")

