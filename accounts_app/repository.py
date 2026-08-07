"""
accounts_app: DB dan faol assistant va ularning studentlarini oladi.
Bu modul workflow uchun "data provider" vazifasini bajaradi.
"""
from shared.db import get_connection
from shared.local_db import get_assistant_tg_info
from shared.models import (
    AssistantInfo,
    StudentInfo,
    GroupProgressSnapshot,
    GroupProgressInfo,
    StudentProgressInfo,
    StudentProblem,
    AssistantStudentTarget,
)
from shared.config import app_config
from shared.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# Progress-tekshirish bosqichi: guruhlarni group_id bo'yicha
# sahifalab (pagination) o'qish + har guruh uchun studentlar progressi.
# ============================================================

_QUERY_ALL_GROUP_IDS_SORTED = """
SELECT id AS group_id, name AS group_name
FROM "group"
ORDER BY id;
"""

_QUERY_GROUP_IDS_BY_IDS_SORTED = """
SELECT id AS group_id, name AS group_name
FROM "group"
WHERE id = ANY(%s)
ORDER BY id;
"""

# Guruhning hozirgi turgan modul/dars holati -- module_id shu yerdan olinadi
# va keyin homework progress query'siga uzatiladi.
_QUERY_GROUP_CURRENT_PROGRESS = """
SELECT
  g.id as group_id,
  g."name" group_name,
  hl.title current_lesson,
  hl."order" current_lesson_number,
  hl.module_id as module_id,
  cl."name" tool,
  ml."name" module
FROM group_progress gp
LEFT JOIN "group" g ON g.id = gp.group_id
LEFT JOIN homework_lesson hl ON hl.id = gp.current_lesson_id
LEFT JOIN module_lesson ml ON ml.id = hl.module_id
LEFT JOIN category_lesson cl ON cl.id = ml.category_id
WHERE gp.group_id = %s;
"""

# Bitta guruhning barcha studentlari uchun JORIY MODULDAGI homework progress:
_QUERY_GROUP_STUDENTS_PROGRESS = """
WITH homeworks_for_module AS (
    SELECT id, title
    FROM homework_lesson
    WHERE module_id = %(module_id)s
    AND "order" <= (
    	select hl."order"  from group_progress gp 
		left join homework_lesson hl 
		on gp.current_lesson_id = hl.id 
		where gp.group_id = %(group_id)s	
    	) 
),
students_with_name AS (
    SELECT
        s.id AS id,
        u.first_name,
        u.last_name,
        s.group_id
    FROM student s
    LEFT JOIN "user" u
        ON s.user_id = u.id
    WHERE s.group_id = %(group_id)s
      AND s.status = 'active'
),
module_uploads AS (
    SELECT
        hu.student_id,
        hm.title,
        hu.uploaded_at
    FROM homework_upload hu
    INNER JOIN homeworks_for_module hm
        ON hu.homework_id = hm.id
    WHERE hu.ai_assistant_score > 0
)
SELECT
    s.id AS student_id,
    COUNT(DISTINCT mu.title) AS uploaded_homeworks_count,
    to_char(MAX(mu.uploaded_at), 'DD-MM-YYYY') AS last_upload_date
FROM students_with_name s
LEFT JOIN module_uploads mu
    ON mu.student_id = s.id
GROUP BY
    s.id
ORDER BY
    uploaded_homeworks_count DESC,
    last_upload_date DESC;
"""


def fetch_all_group_ids() -> list[tuple[int, str]]:
    """
    Barcha guruhlarni group_id bo'yicha tartiblab qaytaradi (id, name).
    Progress-tekshirish bosqichida pagination (N tadan bo'lib) shu ro'yxat
    ustidan yuriladi.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_QUERY_ALL_GROUP_IDS_SORTED)
        rows = cursor.fetchall()
    return [(row.group_id, row.group_name) for row in rows]


def fetch_group_ids_by_ids(group_ids: list[int]) -> list[tuple[int, str]]:
    """
    Berilgan group_id lar ro'yxati bo'yicha guruhlarni (id, name) qaytaradi,
    id bo'yicha tartiblangan holda. So'rovda kelmagan / bazada topilmagan
    group_id'lar natijada bo'lmaydi.
    """
    if not group_ids:
        return []

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_QUERY_GROUP_IDS_BY_IDS_SORTED, (list(group_ids),))
        rows = cursor.fetchall()
    return [(row.group_id, row.group_name) for row in rows]


_QUERY_GROUP_STUDENTS_DISPLAY_INFO = """
SELECT
    s.id                                                  AS student_id,
    CONCAT_WS(' ', u.first_name, u.last_name)             AS full_name
FROM student s
JOIN "user" u ON s.user_id = u.id
WHERE s.status = 'active' AND s.group_id = %s
ORDER BY s.id;
"""


def fetch_group_students_display_info(group_id: int) -> dict[int, str]:
    """
    Bitta guruhning barcha faol studentlari uchun {student_id: full_name}
    lug'atini qaytaradi. Bu faqat FRONTEND'da ko'rsatish uchun -- AI'ga
    yuboriladigan progress snapshot'iga (StudentProgressInfo) ism
    qo'shilmaydi, anonimlik saqlanadi.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_QUERY_GROUP_STUDENTS_DISPLAY_INFO, (group_id,))
        rows = cursor.fetchall()
    return {row.student_id: row.full_name for row in rows}


def fetch_group_current_progress(group_id: int, group_name: str) -> GroupProgressInfo:
    """
    Guruhning hozirgi turgan modul/dars holatini oladi (current_lesson,
    current_lesson_number, tool, module). Bu ma'lumot faqat FRONTEND'da
    ko'rsatish uchun -- module_id undan homework progress query'siga
    uzatiladi, lekin GroupProgressInfo'ning o'zi AI'ga yuborilmaydi.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_QUERY_GROUP_CURRENT_PROGRESS, (group_id,))
        row = cursor.fetchone()

    if not row:
        return GroupProgressInfo(group_id=group_id, group_name=group_name)

    return GroupProgressInfo(
        group_id=group_id,
        group_name=group_name,
        current_lesson=row.current_lesson,
        current_lesson_number=row.current_lesson_number,
        tool=row.tool,
        module=row.module,
    )


def _fetch_group_current_module_id(group_id: int):
    """Guruhning hozirgi turgan darsi tegishli bo'lgan module_id qiymatini oladi."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_QUERY_GROUP_CURRENT_PROGRESS, (group_id,))
        row = cursor.fetchone()
    return row.module_id if row else None


def fetch_group_progress_snapshot(group_id: int, group_name: str) -> GroupProgressSnapshot:
    """
    Bitta guruhning barcha studentlari uchun JORIY MODULDAGI homework progress
    holatini oladi (uploaded_homeworks_count, last_upload_date), shuningdek
    guruhning hozirgi dars/modul holatini (progress_info, faqat frontend uchun).
    """
    progress_info = fetch_group_current_progress(group_id, group_name)
    module_id = _fetch_group_current_module_id(group_id)

    students: list[StudentProgressInfo] = []
    if module_id is not None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                _QUERY_GROUP_STUDENTS_PROGRESS,
                {"module_id": module_id, "group_id": group_id},
            )
            rows = cursor.fetchall()
        students = [
            StudentProgressInfo(
                student_id=row.student_id,
                uploaded_homeworks_count=row.uploaded_homeworks_count or 0,
                last_upload_date=row.last_upload_date,
            )
            for row in rows
        ]
    else:
        logger.warning(
            f"group={group_id}: joriy modul (module_id) aniqlanmadi, "
            "student progress bo'sh ro'yxat sifatida qaytariladi."
        )

    return GroupProgressSnapshot(
        group_id=group_id,
        group_name=group_name,
        students=students,
        progress_info=progress_info,
    )


def fetch_group_progress_snapshots(group_ids: list[int]) -> list[GroupProgressSnapshot]:
    """
    Berilgan group_id'larning barchasi uchun progress snapshot'ini bitta
    ro'yxat sifatida qaytaradi (batch'larga bo'lmasdan, hammasi bir yo'la).
    """
    id_name_pairs = fetch_group_ids_by_ids(group_ids)
    snapshots = [
        fetch_group_progress_snapshot(group_id, group_name)
        for group_id, group_name in id_name_pairs
    ]
    logger.info(f"{len(snapshots)} ta guruh olindi.")
    return snapshots


def fetch_group_progress_batches(
    group_ids: list[int] | None = None,
) -> list[list[GroupProgressSnapshot]]:
    """
    Guruhlarni group_id bo'yicha tartiblab, konfiguratsiyadagi
    `progress_group_batch_size` (masalan 3) tadan bo'lib qaytaradi.

    group_ids berilsa -- faqat shu guruhlar olinadi (so'rovda kelgan
    group_id'lar bo'yicha). Berilmasa (None) -- bazadagi barcha guruhlar
    olinadi (eski xatti-harakat, orqaga moslik uchun saqlangan).
    """
    id_name_pairs = (
        fetch_group_ids_by_ids(group_ids) if group_ids is not None else fetch_all_group_ids()
    )
    batch_size = app_config.progress_group_batch_size

    batches: list[list[GroupProgressSnapshot]] = []
    for i in range(0, len(id_name_pairs), batch_size):
        chunk = id_name_pairs[i : i + batch_size]
        snapshots = [
            fetch_group_progress_snapshot(group_id, group_name)
            for group_id, group_name in chunk
        ]
        batches.append(snapshots)

    logger.info(
        f"{len(id_name_pairs)} ta guruh, {len(batches)} ta batch'ga bo'lindi "
        f"(batch_size={batch_size})."
    )
    return batches


# ============================================================
# Muammoli studentlarni ularning assistenti bilan bog'lash
# ============================================================

_QUERY_ASSISTANT_AND_STUDENT_FOR_TARGET = """
SELECT
    g.assistant_id                                        AS assistant_id,
    CONCAT_WS(' ', a_usr.first_name, a_usr.last_name)     AS assistant_name,
    s.id                                                  AS student_id,
    CONCAT_WS(' ', s_usr.first_name, s_usr.last_name)     AS student_name,
    COALESCE(s_usr.first_name, '')                       AS student_first_name,
    COALESCE(s_usr.last_name, '')                        AS student_last_name,
    s_usr.user_id_number                                  AS student_user_id_number
FROM "group" g
JOIN "user" a_usr ON g.assistant_id = a_usr.id AND a_usr.role = 'mentor_assistant'
JOIN student s ON s.group_id = g.id AND s.id = %s
JOIN "user" s_usr ON s.user_id = s_usr.id
WHERE g.id = %s;
"""

# assistant_id DB'dan emas, chaqiruvchidan (so'rovdan) beriladigan holat uchun --
# faqat student ma'lumotini guruh ichidan olamiz, assistentga bog'lamaymiz.
_QUERY_STUDENT_FOR_TARGET = """
SELECT
    s.id                                                  AS student_id,
    CONCAT_WS(' ', s_usr.first_name, s_usr.last_name)     AS student_name,
    COALESCE(s_usr.first_name, '')                       AS student_first_name,
    COALESCE(s_usr.last_name, '')                        AS student_last_name,
    s_usr.user_id_number                                  AS student_user_id_number
FROM student s
JOIN "user" s_usr ON s.user_id = s_usr.id
WHERE s.group_id = %s AND s.id = %s;
"""

_QUERY_ASSISTANT_NAME_BY_ID = """
SELECT
    u.id                                       AS assistant_id,
    CONCAT_WS(' ', u.first_name, u.last_name)  AS assistant_name
FROM "user" u
WHERE u.id = %s AND u.role = 'mentor_assistant';
"""


def resolve_leader_targets_for_problems(
    problems: list[StudentProblem],
) -> list[AssistantStudentTarget]:
    """
    Progress bosqichida muammo aniqlangan studentlarni ularning guruhi
    orqali assistenti bilan bog'laydi.
    """
    targets: list[AssistantStudentTarget] = []

    with get_connection() as conn:
        cursor = conn.cursor()
        for problem in problems:
            cursor.execute(
                _QUERY_ASSISTANT_AND_STUDENT_FOR_TARGET,
                (problem.student_id, problem.group_id),
            )
            row = cursor.fetchone()
            if not row:
                logger.warning(
                    f"student={problem.student_id} group={problem.group_id}: "
                    "assistant/student topilmadi, o'tkazib yuborildi."
                )
                continue

            tg_info = get_assistant_tg_info(row.assistant_id)
            if not tg_info or not tg_info["is_active"]:
                logger.warning(
                    f"assistant={row.assistant_id} student={problem.student_id}: "
                    "faol Telegram sessiyasi (assistant_tg_info) topilmadi, o'tkazib yuborildi."
                )
                continue

            assistant = AssistantInfo(
                assistant_id=row.assistant_id,
                full_name=row.assistant_name,
                tg_user_id=tg_info["tg_user_id"],
                tg_session_name=tg_info["session_name"],
            )
            student = StudentInfo(
                student_id=row.student_id,
                full_name=row.student_name,
                first_name=row.student_first_name,
                last_name=row.student_last_name,
                group_id=problem.group_id,
                user_id_number=row.student_user_id_number,
            )
            targets.append(
                AssistantStudentTarget(assistant=assistant, student=student, problem=problem.problem)
            )

    logger.info(f"{len(targets)} ta muammoli student bilan assistent bog'langan.")
    return targets


resolve_assistant_targets_for_problems = resolve_leader_targets_for_problems


def resolve_targets_for_problems_with_assistant(
    problems: list[StudentProblem],
    assistant_id: int,
) -> list[AssistantStudentTarget]:
    """
    resolve_leader_targets_for_problems bilan bir xil ishni bajaradi, lekin
    assistentni guruh orqali (g.assistant_id) DB'dan aniqlash o'rniga,
    so'rovdan (request) kelgan `assistant_id`ni har bir target uchun ishlatadi.

    Bu /run-stream endpoint'i endi so'rovda group_ids + assistant_id qabul
    qilgani uchun kerak: pipeline shu ikkalasi bilan ishlashi kerak, bazadagi
    guruh->assistant bog'lanishiga qaramasdan.
    """
    targets: list[AssistantStudentTarget] = []

    tg_info = get_assistant_tg_info(assistant_id)
    if not tg_info or not tg_info["is_active"]:
        logger.warning(
            f"assistant={assistant_id}: faol Telegram sessiyasi (assistant_tg_info) "
            "topilmadi, hech qanday target yaratilmadi."
        )
        return targets

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(_QUERY_ASSISTANT_NAME_BY_ID, (assistant_id,))
        assistant_row = cursor.fetchone()
        if not assistant_row:
            logger.warning(
                f"assistant={assistant_id}: 'mentor_assistant' roli bilan topilmadi, "
                "hech qanday target yaratilmadi."
            )
            return targets

        assistant = AssistantInfo(
            assistant_id=assistant_row.assistant_id,
            full_name=assistant_row.assistant_name,
            tg_user_id=tg_info["tg_user_id"],
            tg_session_name=tg_info["session_name"],
        )

        for problem in problems:
            cursor.execute(
                _QUERY_STUDENT_FOR_TARGET,
                (problem.group_id, problem.student_id),
            )
            row = cursor.fetchone()
            if not row:
                logger.warning(
                    f"student={problem.student_id} group={problem.group_id}: "
                    "student topilmadi, o'tkazib yuborildi."
                )
                continue

            student = StudentInfo(
                student_id=row.student_id,
                full_name=row.student_name,
                first_name=row.student_first_name,
                last_name=row.student_last_name,
                group_id=problem.group_id,
                user_id_number=row.student_user_id_number,
            )
            targets.append(
                AssistantStudentTarget(assistant=assistant, student=student, problem=problem.problem)
            )

    return targets

