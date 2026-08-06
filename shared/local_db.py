"""
Lokal SQLite ma'lumotlar bazasi.

Quyidagi jadvallar shu yerda saqlanadi (asosiy PostgreSQL bazadan mustaqil,
tarmoqqa bog'liq bo'lmagan tezkor lokal saqlash uchun):
  - chats_last_check  -- leader-student chatlarini oxirgi tekshirish sanasi
  - ai_reports        -- AI tahlili natijalari
  - leader_tg_info    -- leaderning Telegram sessiya ma'lumotlari (login orqali to'ldiriladi)

Fayl joyi: shared.config.local_db_config.path (odatda loyiha ildizida
`local_data.sqlite3`).
"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from shared.config import local_db_config
from shared.logger import get_logger

logger = get_logger(__name__)


@contextmanager
def get_local_connection() -> Iterator[sqlite3.Connection]:
    """
    Context manager: SQLite ulanishini ochadi, oxirida albatta yopadi.
    Xatolik bo'lsa rollback qiladi.

    row_factory = sqlite3.Row -> qatorlarga ham index, ham nom orqali
    (row["assistant_id"] yoki row.assistant_id kabi emas, faqat row["assistant_id"])
    murojaat qilish mumkin. Chaqiruvchi kodda `.attr` shakli ishlatilgan
    joylarda mos moslashtirish qilingan (pastga qarang: repository/tracking
    va reports_repository yangilanishlarida `row["..."]` ishlatiladi).
    """
    conn = None
    try:
        conn = sqlite3.connect(local_db_config.path, timeout=10)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"SQLite ulanish xatosi: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def ensure_tracking_table_exists() -> None:
    """
    chats_last_check jadvali (lokal SQLite).
    Mavjud bo'lmasa yaratadi (idempotent).
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS chats_last_check (
        assistant_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        last_check_date TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (assistant_id, student_id)
    )
    """
    with get_local_connection() as conn:
        conn.execute(ddl)
        conn.commit()
    logger.info("chats_last_check jadvali (SQLite) tekshirildi/yaratildi.")


def ensure_ai_reports_table_exists() -> None:
    """
    ai_reports jadvali (lokal SQLite).
    Mavjud bo'lmasa yaratadi (idempotent).
    Progress bo'yicha aniqlangan `problem`, chat tahlili `ai_summary`,
    va AI'dan kelgan to'liq `raw_json` javobini saqlaydi.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS ai_reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        assistant_id INTEGER NOT NULL,
        problem TEXT,
        ai_summary TEXT,
        raw_json TEXT,
        last_contacted_date TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """
    with get_local_connection() as conn:
        conn.execute(ddl)
        conn.commit()
    logger.info("ai_reports jadvali (SQLite) tekshirildi/yaratildi.")


def ensure_assistant_tg_info_table_exists() -> None:
    """
    assistant_tg_info jadvali (lokal SQLite).
    Mavjud bo'lmasa yaratadi (idempotent).

    Har bir assistant uchun Pyrogram session ma'lumotlarini saqlaydi:
    - assistant_id: user (PostgreSQL) jadvalidagi id (role='mentor_assistant')
    - session_name: Pyrogram session fayl nomi (masalan 'assistant_3')
    - phone: login qilingan telefon raqami
    - tg_user_id: Telegram foydalanuvchi ID'si (login vaqtida saqlanadi)
    - is_active: session hozir yaroqlimi (0/1)
    - created_at: yozuv birinchi marta yaratilgan vaqt
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS assistant_tg_info (
        assistant_id INTEGER PRIMARY KEY,
        session_name TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL,
        tg_user_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """
    with get_local_connection() as conn:
        conn.execute(ddl)
        conn.commit()
    logger.info("assistant_tg_info jadvali (SQLite) tekshirildi/yaratildi.")


def upsert_assistant_tg_info(
    assistant_id: int,
    session_name: str,
    phone: str,
    tg_user_id: int | None = None,
    is_active: bool = True,
) -> None:
    """
    assistant_tg_info jadvaliga (SQLite) yozuvni qo'shadi yoki mavjud bo'lsa
    yangilaydi (upsert, assistant_id bo'yicha).
    """
    query = """
    INSERT INTO assistant_tg_info (assistant_id, session_name, phone, tg_user_id, is_active)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (assistant_id) DO UPDATE SET
        session_name = excluded.session_name,
        phone = excluded.phone,
        tg_user_id = excluded.tg_user_id,
        is_active = excluded.is_active
    """
    with get_local_connection() as conn:
        conn.execute(query, (assistant_id, session_name, phone, tg_user_id, int(is_active)))
        conn.commit()
    logger.info(f"assistant_tg_info yangilandi: assistant_id={assistant_id}, session_name={session_name}")


upsert_leader_tg_info = upsert_assistant_tg_info


def get_assistant_tg_info(assistant_id: int) -> sqlite3.Row | None:
    """Berilgan assistant_id uchun assistant_tg_info yozuvini qaytaradi (topilmasa None)."""
    query = "SELECT * FROM assistant_tg_info WHERE assistant_id = ?"
    with get_local_connection() as conn:
        cursor = conn.execute(query, (assistant_id,))
        return cursor.fetchone()


get_leader_tg_info = get_assistant_tg_info


def get_active_assistant_tg_infos() -> list[sqlite3.Row]:
    """Barcha is_active=1 bo'lgan assistant_tg_info yozuvlarini qaytaradi."""
    query = "SELECT * FROM assistant_tg_info WHERE is_active = 1"
    with get_local_connection() as conn:
        cursor = conn.execute(query)
        return cursor.fetchall()


get_active_leader_tg_infos = get_active_assistant_tg_infos


def ensure_group_check_logs_table_exists() -> None:
    """
    group_check_logs jadvali (lokal SQLite).
    Mavjud bo'lmasa yaratadi (idempotent).

    Har bir /group-check pipeline ishga tushishining "pasporti":
    qaysi guruh, qaysi assistant, qachon tekshirilgan, nechta muammoli
    student topilgan va tekshiruv holati (success / error turi).
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS group_check_logs (
        check_id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        assistant_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL DEFAULT (datetime('now')),
        flagged_count INTEGER NOT NULL DEFAULT 0,
        check_status TEXT NOT NULL DEFAULT 'success'
    )
    """
    with get_local_connection() as conn:
        conn.execute(ddl)
        conn.commit()
    logger.info("group_check_logs jadvali (SQLite) tekshirildi/yaratildi.")


def ensure_student_issues_log_table_exists() -> None:
    """
    student_issues_log jadvali (lokal SQLite).
    Mavjud bo'lmasa yaratadi (idempotent).

    Har bir group_check_logs yozuviga (check_id orqali) bog'langan,
    o'sha tekshiruvda aniqlangan har bir studentning muammosi haqida
    batafsil yozuv. is_resolved keyingi tekshiruvlarda shu muammo
    hal qilingandan keyin True qilinadi.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS student_issues_log (
        issue_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        issue_category TEXT NOT NULL,
        issue_details TEXT,
        is_resolved INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (check_id) REFERENCES group_check_logs (check_id)
    )
    """
    with get_local_connection() as conn:
        conn.execute(ddl)
        conn.commit()
    logger.info("student_issues_log jadvali (SQLite) tekshirildi/yaratildi.")


# ============================================================
# group_check_logs / student_issues_log uchun CRUD funksiyalari
# ============================================================

def insert_group_check_log(
    group_id: int,
    assistant_id: int,
    flagged_count: int,
    check_status: str = "success",
) -> int:
    """
    group_check_logs jadvaliga bitta tekshiruv sessiyasining "pasporti"ni
    yozadi va yaratilgan check_id ni qaytaradi.

    check_status: "success" yoki xatolik turi tavsifi
    (masalan "error: FloodWait", "error: <exception message>").
    Jadval hali yaratilmagan bo'lsa (masalan birinchi ishga tushirishda),
    avtomatik ravishda yaratiladi (idempotent).
    """
    ensure_group_check_logs_table_exists()
    query = """
    INSERT INTO group_check_logs (group_id, assistant_id, flagged_count, check_status)
    VALUES (?, ?, ?, ?)
    """
    with get_local_connection() as conn:
        cursor = conn.execute(query, (group_id, assistant_id, flagged_count, check_status))
        conn.commit()
        check_id = cursor.lastrowid
    logger.info(
        f"group_check_logs ga yozildi: check_id={check_id} group_id={group_id} "
        f"assistant_id={assistant_id} flagged_count={flagged_count} status={check_status}"
    )
    return check_id


_HOMEWORK_KEYWORDS = ("vazifa", "topshir", "uy ishi", "homework")
_ATTENDANCE_KEYWORDS = ("dars", "orqada", "qatnash", "kelmagan", "lesson", "faol emas")


def categorize_issue(problem_text: str | None) -> str:
    """
    AI'dan keladigan erkin matnli (o'zbek tilidagi) 'problem' ta'rifini
    kelajakdagi dashboard filtri uchun standart kategoriyaga tushiradi:
    'homework_missing' | 'low_attendance' | 'other'.

    Sodda kalit-so'z (keyword) evristikasi -- aniqroq taksonomiya kerak
    bo'lsa, keyinchalik AI structured-output bilan almashtirilishi mumkin.
    """
    text = (problem_text or "").lower()
    if any(k in text for k in _HOMEWORK_KEYWORDS):
        return "homework_missing"
    if any(k in text for k in _ATTENDANCE_KEYWORDS):
        return "low_attendance"
    return "other"


def insert_student_issues(check_id: int, issues: list[tuple[int, str]]) -> int:
    """
    Bitta tekshiruv sessiyasida (check_id) aniqlangan barcha muammoli
    studentlarni student_issues_log jadvaliga yozadi.

    issues: (student_id, issue_details) juftliklari ro'yxati.
    issue_category har bir yozuv uchun `categorize_issue` orqali avtomatik
    aniqlanadi. Har bir yozuv mustaqil try/except bilan saqlanadi (fault
    isolation) -- bittasi xato bersa, qolganlari yozilishda davom etadi.
    Yaratilgan (saqlangan) yozuvlar soni qaytariladi.
    """
    ensure_student_issues_log_table_exists()
    query = """
    INSERT INTO student_issues_log (check_id, student_id, issue_category, issue_details)
    VALUES (?, ?, ?, ?)
    """
    saved = 0
    with get_local_connection() as conn:
        for student_id, issue_details in issues:
            try:
                category = categorize_issue(issue_details)
                conn.execute(query, (check_id, student_id, category, issue_details))
                saved += 1
            except sqlite3.Error as e:
                logger.error(
                    f"student_issues_log ga yozishda xato: check_id={check_id} "
                    f"student_id={student_id}: {e}"
                )
                continue
        conn.commit()
    logger.info(f"student_issues_log: {saved}/{len(issues)} ta muammo check_id={check_id} uchun yozildi.")
    return saved


def resolve_student_issues(student_id: int, issue_category: str | None = None) -> int:
    """
    Berilgan student uchun hali is_resolved=0 bo'lgan (ochiq) muammolarni
    "hal qilindi" deb belgilaydi (is_resolved=1).

    Bu, masalan, keyingi tekshiruvda AI chat tahlili natijasida
    (InteractionReport.addressed_issues=True) assistant muammoni
    muvaffaqiyatli hal qilgani aniqlanganda chaqiriladi.

    issue_category berilsa -- faqat o'sha kategoriyadagi ochiq muammolar
    yopiladi; berilmasa -- studentning barcha ochiq muammolari yopiladi.
    Yangilangan qatorlar soni qaytariladi.
    """
    ensure_student_issues_log_table_exists()
    if issue_category:
        query = """
        UPDATE student_issues_log
        SET is_resolved = 1
        WHERE student_id = ? AND is_resolved = 0 AND issue_category = ?
        """
        params = (student_id, issue_category)
    else:
        query = """
        UPDATE student_issues_log
        SET is_resolved = 1
        WHERE student_id = ? AND is_resolved = 0
        """
        params = (student_id,)

    with get_local_connection() as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        updated = cursor.rowcount

    if updated:
        logger.info(
            f"student_issues_log: student_id={student_id} uchun {updated} ta muammo hal qilindi deb belgilandi."
        )
    return updated


def ensure_inactive_assistants_table_exists() -> None:
    """
    inactive_assistants jadvali (lokal SQLite).
    Mavjud bo'lmasa yaratadi (idempotent).

    /settings sahifasidan o'chirilgan (deaktivatsiya qilingan) assistentlar
    shu jadvalda saqlanadi. /api/assistants ularni natijadan chiqarib
    tashlaydi.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS inactive_assistants (
        assistant_id INTEGER PRIMARY KEY,
        deactivated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """
    with get_local_connection() as conn:
        conn.execute(ddl)
        conn.commit()
    logger.info("inactive_assistants jadvali (SQLite) tekshirildi/yaratildi.")


def add_inactive_assistant(assistant_id: int) -> None:
    """Assistantni inactive_assistants jadvaliga qo'shadi (o'chirilgan deb belgilaydi)."""
    ensure_inactive_assistants_table_exists()
    query = """
    INSERT INTO inactive_assistants (assistant_id)
    VALUES (?)
    ON CONFLICT (assistant_id) DO NOTHING
    """
    with get_local_connection() as conn:
        conn.execute(query, (assistant_id,))
        conn.commit()
    logger.info(f"inactive_assistants ga qo'shildi: assistant_id={assistant_id}")


def remove_inactive_assistant(assistant_id: int) -> None:
    """Assistantni inactive_assistants jadvalidan olib tashlaydi (qayta faollashtirish)."""
    ensure_inactive_assistants_table_exists()
    query = "DELETE FROM inactive_assistants WHERE assistant_id = ?"
    with get_local_connection() as conn:
        conn.execute(query, (assistant_id,))
        conn.commit()
    logger.info(f"inactive_assistants dan o'chirildi: assistant_id={assistant_id}")


def get_inactive_assistant_ids() -> list[int]:
    """Barcha o'chirilgan (inactive) assistant_id lar ro'yxatini qaytaradi."""
    ensure_inactive_assistants_table_exists()
    query = "SELECT assistant_id FROM inactive_assistants"
    with get_local_connection() as conn:
        cursor = conn.execute(query)
        return [row["assistant_id"] for row in cursor.fetchall()]


def get_open_issues_for_student(student_id: int) -> list[sqlite3.Row]:
    """Berilgan student uchun hali is_resolved=0 bo'lgan barcha yozuvlarni qaytaradi."""
    ensure_student_issues_log_table_exists()
    query = (
        "SELECT * FROM student_issues_log "
        "WHERE student_id = ? AND is_resolved = 0 ORDER BY created_at DESC"
    )
    with get_local_connection() as conn:
        cursor = conn.execute(query, (student_id,))
        return cursor.fetchall()

