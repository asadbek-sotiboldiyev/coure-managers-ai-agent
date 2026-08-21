"""
main_app: Yakuniy AI reportlarni ko'rsatish va Assistant Telegram Login jarayonlarini 
boshqarish uchun FastAPI Web API.

Ishga tushirish: uvicorn main_app.api:app --reload
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, status, APIRouter
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

from shared.config import tg_config
from shared.db import get_connection
from shared.local_db import (
    ensure_assistant_tg_info_table_exists,
    get_local_connection,
    get_inactive_assistant_ids,
    add_inactive_assistant,
    remove_inactive_assistant,
)
from shared.logger import get_logger
from main_app.orchestrator import run_full_pipeline_stream, run_preview_stage, run_continue_stream
from main_app.preview_store import delete_preview
from shared.models import GroupsCheckRequest, PreviewCheckRequest, ContinueCheckRequest


logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ilova ishga tushganda assistant_tg_info (SQLite) jadvali mavjudligini kafolatlaydi --
    shu orqali /telegram/assistant/* endpoint'lari /run-stream chaqirilishidan oldin
    ham xatosiz ishlaydi."""
    ensure_assistant_tg_info_table_exists()
    yield

api_router = APIRouter(prefix="/api", tags=["Main API"])


# Oddiy in-memory cache
_last_reports_cache: list[dict] = []

# Telegram login jarayoni uchun aktiv vaqtinchalik sessiyalar kesh-xotirasi
active_login_sessions: Dict[str, Dict[str, Any]] = {}



# ==============================================================================
# 🚀 AI PIPELINE & REPORT ENDPOINTS
# ==============================================================================


@api_router.post("/check_groups", tags=["Pipeline & Reports"])
async def trigger_pipeline_stream(data: GroupsCheckRequest):
    """
    Pipeline'ni ishga tushiradi va natijalarni STREAMING (NDJSON) tarzida qaytaradi.
    """
    global _last_reports_cache

    async def _ndjson_generator():
        collected_reports: list[dict] = []
        try:
            async for event in run_full_pipeline_stream(
                group_ids=data.group_ids,
                assistant_id=data.assistant_id,
            ):
                if event.get("state") == "summary":
                    collected_reports.append(event["data"])
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
        except asyncio.CancelledError:
            logger.warning("Streaming mijoz tomonidan yoki Ctrl+C sababli bekor qilindi.")
            # Agar connection uzilsa yoki Ctrl+C bo'lsa, tozalash ishlari shu yerda qilinadi
            raise  # CancelledError'ni qaytadan ko'tarish muhim!
        except Exception as e:
            logger.error(f"Streaming pipeline'da kutilmagan xato: {e}")
            error_event = {"state": "error", "data": {"stage": "pipeline", "message": str(e)}}
            yield json.dumps(error_event, ensure_ascii=False) + "\n"
        finally:
            if collected_reports:
                _last_reports_cache = collected_reports

    return StreamingResponse(_ndjson_generator(), media_type="application/x-ndjson")


@api_router.post("/check_groups/preview", tags=["Pipeline & Reports"])
async def trigger_pipeline_preview(data: PreviewCheckRequest):
    """
    Pipeline'ning 1-bosqichi: DB'dan tanlangan guruhlarning BARCHA (faol)
    studentlarini progress ma'lumotlari (masalan hw_count) bilan oladi,
    progress-AI tahlilini o'tkazadi va har bir guruh uchun ALOHIDA jadval
    sifatida to'liq student ro'yxatini qaytaradi (muammoli studentlar
    has_problem=true bilan belgilanadi).

    Bu chaqiruv chat tarixini olmaydi va AI-summary chaqirmaydi -- pipeline
    shu yerda to'xtaydi. Frontend natijani jadval ko'rinishida ko'rsatib,
    foydalanuvchi tasdiqlagach /api/check_groups/continue ni chaqiradi.

    Javob: {status, preview_id, groups: [{group_id, group_name, students: [
      {student_id, full_name, hw_count, has_problem, problem}
    ]}], problematic_count}
    """
    try:
        result = await run_preview_stage(
            group_ids=data.group_ids,
            assistant_id=data.assistant_id,
        )
    except Exception as e:
        logger.error(f"Preview bosqichida kutilmagan xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if result["status"] != "success":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("message", "Xatolik"))

    return result


@api_router.post("/check_groups/continue", tags=["Pipeline & Reports"])
async def trigger_pipeline_continue(data: ContinueCheckRequest):
    """
    Pipeline'ning 2-bosqichi: preview_id orqali saqlangan muammoli
    studentlar ro'yxatidan (ixtiyoriy ravishda student_ids bilan
    filtrlangan holda) chat tarixini olib, AI-summary tahlilini STREAMING
    (NDJSON) tarzida bajaradi. Progress-AI tahlili QAYTA ISHLAMAYDI.
    """
    global _last_reports_cache

    async def _ndjson_generator():
        collected_reports: list[dict] = []
        try:
            async for event in run_continue_stream(
                preview_id=data.preview_id,
                student_ids=data.student_ids,
            ):
                if event.get("state") == "summary":
                    collected_reports.append(event["data"])
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
        except asyncio.CancelledError:
            logger.warning("Continue streaming mijoz tomonidan yoki Ctrl+C sababli bekor qilindi.")
            raise
        except Exception as e:
            logger.error(f"Continue pipeline'da kutilmagan xato: {e}")
            error_event = {"state": "error", "data": {"stage": "pipeline", "message": str(e)}}
            yield json.dumps(error_event, ensure_ascii=False) + "\n"
        finally:
            if collected_reports:
                _last_reports_cache = collected_reports
            delete_preview(data.preview_id)

    return StreamingResponse(_ndjson_generator(), media_type="application/x-ndjson")


@api_router.get("/reports", tags=["Pipeline & Reports"])
async def get_last_reports():
    """Oxirgi ishga tushirilgan pipeline natijalarini qaytaradi (cache'dan)."""
    if not _last_reports_cache:
        return {"status": "empty", "message": "Hali hech qanday pipeline ishga tushirilmagan."}
    return {"status": "success", "count": len(_last_reports_cache), "reports": _last_reports_cache}


# ==============================================================================
# 👥 ASSISTANTS & AI REPORTS ENDPOINTS
# ==============================================================================

def fetch_assistant_tg_status_map() -> dict[int, dict]:
    """Lokal SQLite'dagi assistant_tg_info jadvalidan barcha assistentlar uchun
    Telegram ulanish holatini bitta so'rovda oladi.
    Qaytadi: {assistant_id: {tg_connected: bool, session_name, phone, tg_user_id}}.
    is_active=1 bo'lgan yozuv "ulangan" (connected) deb hisoblanadi."""
    ensure_assistant_tg_info_table_exists()
    try:
        with get_local_connection() as conn:
            cursor = conn.execute(
                "SELECT assistant_id, session_name, phone, tg_user_id, is_active FROM assistant_tg_info"
            )
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"assistant_tg_info holatini olishda xato: {e}")
        return {}

    return {
        row["assistant_id"]: {
            "tg_connected": bool(row["is_active"]),
            "tg_session_name": row["session_name"],
            "tg_phone": row["phone"],
            "tg_user_id": row["tg_user_id"],
        }
        for row in rows
    }


@api_router.get("/assistants", tags=["Assistants"])
async def get_assistants():
    """
    PostgreSQL'dan barcha assistentlarni (role='mentor_assistant') ularning
    biriktirilgan guruhlari bilan birga qaytaradi.

    Har bir assistent uchun:
    - assistant_id, full_name, phone_number, username
    - groups: [{ group_id, group_name, status, is_active }]
    - tg_connected: Telegram sessiyasi ulanganmi (true/false)
    - tg_session_name, tg_phone, tg_user_id: ulangan bo'lsa tafsilotlar
    """
    query = """
    SELECT
        u.id            AS assistant_id,
        CONCAT_WS(' ', u.first_name, u.last_name) AS full_name,
        u.first_name,
        u.last_name,
        u.phone_number,
        u.username,
        u.is_active     AS user_is_active,
        g.id            AS group_id,
        g.name          AS group_name,
        g.status        AS group_status,
        g.is_active     AS group_is_active
    FROM app_user u
    LEFT JOIN study_group g ON g.assistant_id = u.id
    WHERE u.role = 'mentor_assistant' and g.status = 'active'
    ORDER BY u.id, g.id;
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"Assistentlarni olishda xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Assistentlarni guruhlar bilan guruhlab chiqish
    assistants_map: dict[int, dict] = {}
    for row in rows:
        aid = row.assistant_id
        if aid not in assistants_map:
            assistants_map[aid] = {
                "assistant_id": aid,
                "full_name": row.full_name,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "phone_number": row.phone_number,
                "username": row.username,
                "is_active": row.user_is_active,
                "groups": [],
            }
        if row.group_id is not None:
            assistants_map[aid]["groups"].append({
                "group_id": row.group_id,
                "group_name": row.group_name,
                "status": row.group_status,
                "is_active": row.group_is_active,
            })

    # /settings sahifasidan o'chirilgan (inactive) deb belgilangan assistentlarni
    # natijadan chiqarib tashlaymiz.
    inactive_ids = set(get_inactive_assistant_ids())
    assistants_list = [a for a in assistants_map.values() if a["assistant_id"] not in inactive_ids]

    # Har bir assistentga Telegram ulanish holatini (lokal SQLite) qo'shamiz
    tg_status_map = fetch_assistant_tg_status_map()
    for assistant in assistants_list:
        tg_status = tg_status_map.get(assistant["assistant_id"])
        assistant["tg_connected"] = bool(tg_status and tg_status["tg_connected"])
        assistant["tg_session_name"] = tg_status["tg_session_name"] if tg_status else None
        assistant["tg_phone"] = tg_status["tg_phone"] if tg_status else None
        assistant["tg_user_id"] = tg_status["tg_user_id"] if tg_status else None

    return {"status": "success", "count": len(assistants_list), "assistants": assistants_list}


_QUERY_STUDENT_INFO_BY_IDS = """
SELECT
    s.id                                                  AS student_id,
    CONCAT_WS(' ', s_usr.first_name, s_usr.last_name)    AS student_full_name,
    s_usr.first_name                                     AS student_first_name,
    s_usr.last_name                                      AS student_last_name,
    s.group_id                                           AS group_id,
    g.name                                                AS group_name
FROM student s
JOIN app_user s_usr ON s.user_id = s_usr.id
LEFT JOIN study_group g ON s.group_id = g.id
WHERE s.id = ANY(%s);
"""


def fetch_student_info_map(student_ids: list[int]) -> dict[int, dict]:
    """Berilgan student_id (ai_reports.student_id -> student.id) ro'yxati uchun
    PostgreSQL'dan full_name va group_name larni bitta so'rovda oladi.
    Qaytadi: {student_id: {full_name, first_name, last_name, group_id, group_name}}.
    Topilmagan student_id'lar natijada bo'lmaydi."""
    unique_ids = list({sid for sid in student_ids if sid is not None})
    if not unique_ids:
        return {}

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(_QUERY_STUDENT_INFO_BY_IDS, (unique_ids,))
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"Studentlar ma'lumotini olishda xato: {e}")
        return {}

    return {
        row.student_id: {
            "full_name": row.student_full_name,
            "first_name": row.student_first_name,
            "last_name": row.student_last_name,
            "group_id": row.group_id,
            "group_name": row.group_name,
        }
        for row in rows
    }


@api_router.get("/assistants/{assistant_id}/reports", tags=["Assistants"])
async def get_assistant_reports(assistant_id: int):
    """
    Lokal SQLite bazadagi ai_reports jadvalidan berilgan assistant_id ga
    tegishli barcha AI reportlarni qaytaradi (eng yangisi birinchi).

    Har bir report'ga PostgreSQL'dan olingan student_full_name va
    group_name maydonlari ham qo'shib beriladi.
    """
    from shared.local_db import get_local_connection, ensure_ai_reports_table_exists

    ensure_ai_reports_table_exists()

    query = """
    SELECT report_id, student_id, assistant_id, problem, ai_summary,
           raw_json, last_contacted_date, created_at
    FROM ai_reports
    WHERE assistant_id = ?
    ORDER BY created_at DESC;
    """
    try:
        with get_local_connection() as conn:
            cursor = conn.execute(query, (assistant_id,))
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"AI reportlarni olishda xato (assistant_id={assistant_id}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    reports = [dict(row) for row in rows]

    student_info_map = fetch_student_info_map([r["student_id"] for r in reports])
    for r in reports:
        info = student_info_map.get(r["student_id"], {})
        r["student_full_name"] = info.get("full_name") or f"Student #{r['student_id']}"
        r["group_id"] = info.get("group_id")
        r["group_name"] = info.get("group_name") or "Noma'lum guruh"

    return {"status": "success", "assistant_id": assistant_id, "count": len(reports), "reports": reports}


@api_router.get("/dashboard/overview", tags=["Dashboard"])
async def get_dashboard_overview():
    """
    Course Manager Dashboard uchun agregatsiya qilingan ma'lumotlar.

    Har bir assistant (mentor_assistant) uchun:
    - assistant_id, full_name, groups (nomlari)
    - coverage_pct: shu assistantga tegishli ai_reports orasida
      addressed_issues=true bo'lganlarning foizi (0-100)
    - avg_quality_score: support_quality_score o'rtachasi (0-10)
    - flagged_students_count: shu assistantga tegishli reportlardagi
      UNIKAL student_id lar soni
    - leader_summary: eng so'nggi report'dagi ai_summary matni
    - students: har bir flagged student uchun eng so'nggi report
      (student_id, problem, contacted (addressed_issues), help_offered
      (discussed_flagged_problem), ai_summary, recommendations,
      last_contacted_date)

    Shuningdek yuqori darajadagi summary statistikalarni ham qaytaradi:
    total_assistants, active_groups, total_flagged_students,
    avg_quality_score (umumiy), overall_coverage_rate.
    """
    from shared.local_db import get_local_connection, ensure_ai_reports_table_exists

    ensure_ai_reports_table_exists()

    # 1) PostgreSQL'dan assistentlar + guruhlar
    query = """
    SELECT
        u.id            AS assistant_id,
        CONCAT_WS(' ', u.first_name, u.last_name) AS full_name,
        u.is_active     AS user_is_active,
        g.id            AS group_id,
        g.name          AS group_name,
        g.is_active     AS group_is_active
    FROM app_user u
    LEFT JOIN study_group g ON g.assistant_id = u.id
    WHERE u.role = 'mentor_assistant' and g.status = 'active'
    ORDER BY u.id, g.id;
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"Dashboard uchun assistentlarni olishda xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # /settings sahifasidan o'chirilgan (inactive) deb belgilangan assistentlarni
    # natijadan chiqarib tashlaymiz.
    inactive_ids = set(get_inactive_assistant_ids())

    assistants_map: dict[int, dict] = {}
    for row in rows:
        aid = row.assistant_id
        if aid in inactive_ids:
            continue
        if aid not in assistants_map:
            assistants_map[aid] = {
                "assistant_id": aid,
                "full_name": row.full_name,
                "is_active": row.user_is_active,
                "groups": [],
            }
        if row.group_id is not None:
            assistants_map[aid]["groups"].append({
                "group_id": row.group_id,
                "group_name": row.group_name,
                "is_active": row.group_is_active,
            })



    # 2) SQLite'dan barcha AI reportlar (barcha assistentlar uchun).
    # Dashboard metrikalari (coverage, avg score) so'nggi 7 kunlik "rolling
    # window" bo'yicha agregatsiya qilinadi.
    rolling_window_days = 7
    rolling_window_start = datetime.now() - timedelta(days=rolling_window_days)
    try:
        with get_local_connection() as conn:
            cursor = conn.execute(
                """
                SELECT report_id, student_id, assistant_id, problem, ai_summary,
                       raw_json, last_contacted_date, created_at
                FROM ai_reports
                WHERE created_at >= ?
                ORDER BY created_at DESC
                """,
                (rolling_window_start.isoformat(),),
            )
            report_rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"Dashboard uchun AI reportlarni olishda xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Assistant bo'yicha guruhlab chiqish, har bir student uchun ENG SO'NGGI report
    reports_by_assistant: dict[int, list[dict]] = {}
    all_student_ids: list[int] = []
    for r in report_rows:
        row = dict(r)
        raw_json = row.get("raw_json")
        parsed: dict = {}
        if raw_json:
            try:
                parsed = json.loads(raw_json)
            except Exception:
                parsed = {}
        row["_parsed"] = parsed
        reports_by_assistant.setdefault(row["assistant_id"], []).append(row)
        all_student_ids.append(row["student_id"])

    # Barcha reportlardagi student_id'lar uchun full_name/group_name bitta so'rovda
    student_info_map = fetch_student_info_map(all_student_ids)

    def latest_reports_per_student(reports: list[dict]) -> list[dict]:
        """created_at bo'yicha DESC saralangan ro'yxatdan har bir
        student_id uchun birinchi (eng yangi) yozuvni oladi."""
        seen: set[int] = set()
        latest: list[dict] = []
        for r in reports:
            sid = r["student_id"]
            if sid in seen:
                continue
            seen.add(sid)
            latest.append(r)
        return latest

    total_flagged_students = 0
    all_quality_scores: list[float] = []
    all_coverage_flags: list[bool] = []
    total_active_groups = 0

    # Grace period: agar student oxirgi 3 kun ichida bog'lanilgan bo'lsa va
    # AI bahosi "good" (>= 7) bo'lsa, uni vaqtincha "flagged" ro'yxatidan
    # chiqarib turamiz -- assistant allaqachon yordam bergan.
    grace_period_days = 3
    grace_period_start = datetime.now() - timedelta(days=grace_period_days)
    good_score_threshold = 7

    def _in_grace_period(report_row: dict) -> bool:
        contacted_raw = report_row.get("last_contacted_date")
        if not contacted_raw:
            return False
        try:
            contacted_at = datetime.fromisoformat(contacted_raw)
        except (TypeError, ValueError):
            return False
        if contacted_at < grace_period_start:
            return False
        score = report_row["_parsed"].get("support_quality_score", 0) or 0
        return score >= good_score_threshold

    assistants_list = []
    for aid, info in assistants_map.items():
        assistant_reports = reports_by_assistant.get(aid, [])
        latest = latest_reports_per_student(assistant_reports)

        students_out = []
        quality_scores = []
        addressed_flags = []
        for r in latest:
            if _in_grace_period(r):
                # Student yaqinda (<=3 kun) bog'langan va AI bahosi "good" --
                # vaqtincha flagged ro'yxatidan chiqarib turamiz.
                continue

            parsed = r["_parsed"]
            score = parsed.get("support_quality_score", 0) or 0
            addressed = bool(parsed.get("addressed_issues", False))
            discussed = bool(parsed.get("discussed_flagged_problem", False))
            quality_scores.append(score)
            addressed_flags.append(addressed)

            student_info = student_info_map.get(r["student_id"], {})

            students_out.append({
                "student_id": r["student_id"],
                "student_full_name": student_info.get("full_name") or f"Student #{r['student_id']}",
                "group_id": student_info.get("group_id"),
                "group_name": student_info.get("group_name") or "Noma'lum guruh",
                "problem": r.get("problem") or parsed.get("problem"),
                "contacted": addressed,
                "help_offered": discussed,
                "ai_summary": r.get("ai_summary") or parsed.get("summary"),
                "recommendations": parsed.get("recommendations"),
                "support_quality_score": score,
                "last_contacted_date": r.get("last_contacted_date"),
                "created_at": r.get("created_at"),
            })

        avg_quality = round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else 0
        coverage_pct = round(100 * sum(1 for f in addressed_flags if f) / len(addressed_flags), 1) if addressed_flags else 0
        flagged_count = len(students_out)

        latest_summary = students_out[0]["ai_summary"] if students_out else None

        active_groups_count = sum(1 for g in info["groups"] if g["is_active"])
        total_active_groups += active_groups_count
        total_flagged_students += flagged_count
        all_quality_scores.extend(quality_scores)
        all_coverage_flags.extend(addressed_flags)

        assistants_list.append({
            "assistant_id": aid,
            "full_name": info["full_name"],
            "is_active": info["is_active"],
            "groups": info["groups"],
            "groups_count": len(info["groups"]),
            "coverage_pct": coverage_pct,
            "avg_quality_score": avg_quality,
            "flagged_students_count": flagged_count,
            "leader_summary": latest_summary,
            "students": students_out,
        })

    overall_avg_quality = round(sum(all_quality_scores) / len(all_quality_scores), 2) if all_quality_scores else 0
    overall_coverage_rate = round(100 * sum(1 for f in all_coverage_flags if f) / len(all_coverage_flags), 1) if all_coverage_flags else 0

    summary = {
        "total_assistants": len(assistants_list),
        "active_groups": total_active_groups,
        "total_flagged_students": total_flagged_students,
        "avg_quality_score": overall_avg_quality,
        "overall_coverage_rate": overall_coverage_rate,
    }

    return {"status": "success", "summary": summary, "assistants": assistants_list}


@api_router.get("/dashboard/recent_checks", tags=["Dashboard"])
async def get_recent_checks(limit: int = 20):
    """
    So'nggi group_check_logs yozuvlarini (eng yangisi birinchi) qaytaradi --
    "Oxirgi tekshiruvlar" bo'limi uchun.

    Har bir yozuv uchun:
    - check_id, group_id, group_name, assistant_id, assistant_full_name,
      checked_at, flagged_count, check_status
    """
    from shared.local_db import get_local_connection, ensure_group_check_logs_table_exists

    ensure_group_check_logs_table_exists()

    query = """
    SELECT check_id, group_id, assistant_id, checked_at, flagged_count, check_status
    FROM group_check_logs
    ORDER BY checked_at DESC
    LIMIT ?;
    """
    try:
        with get_local_connection() as conn:
            cursor = conn.execute(query, (limit,))
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"group_check_logs olishda xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    checks = [dict(row) for row in rows]

    # Guruh va assistant nomlarini PostgreSQL'dan bitta so'rovda olamiz
    group_ids = list({c["group_id"] for c in checks})
    assistant_ids = list({c["assistant_id"] for c in checks})

    group_name_map: dict[int, str] = {}
    assistant_name_map: dict[int, str] = {}

    if group_ids or assistant_ids:
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                if group_ids:
                    cursor.execute(
                        'SELECT id AS group_id, name AS group_name FROM study_group WHERE id = ANY(%s);',
                        (group_ids,),
                    )
                    for row in cursor.fetchall():
                        group_name_map[row.group_id] = row.group_name
                if assistant_ids:
                    cursor.execute(
                        'SELECT id AS assistant_id, CONCAT_WS(\' \', first_name, last_name) AS full_name '
                        'FROM app_user WHERE id = ANY(%s);',
                        (assistant_ids,),
                    )
                    for row in cursor.fetchall():
                        assistant_name_map[row.assistant_id] = row.full_name
        except Exception as e:
            logger.error(f"Oxirgi tekshiruvlar uchun guruh/assistant nomlarini olishda xato: {e}")

    for c in checks:
        c["group_name"] = group_name_map.get(c["group_id"]) or f"Guruh #{c['group_id']}"
        c["assistant_full_name"] = assistant_name_map.get(c["assistant_id"]) or f"Assistant #{c['assistant_id']}"

    return {"status": "success", "count": len(checks), "checks": checks}


@api_router.get("/dashboard/groups", tags=["Dashboard"])
async def get_dashboard_groups():
    """
    /dashboard sahifasidagi "Guruhlar" bo'limi uchun har bir aktiv guruh
    bo'yicha card ma'lumotlari. Statistikalar oxirgi 7 kunlik oyna
    (rolling window) bo'yicha group_check_logs / student_issues_log'dan
    hisoblanadi.

    Har bir guruh uchun:
    - group_id, group_name, assistant_id, assistant_full_name
    - checks_count: oxirgi 7 kunda shu guruh uchun nechta tekshiruv o'tkazilgani
    - last_checked_at: shu guruhning eng oxirgi tekshiruv vaqti (barcha vaqt, cheklovsiz)
    - last_check_status: eng oxirgi tekshiruv holati
    - flagged_students_total: oxirgi 7 kunda shu guruhdan chiqqan muammoli
      studentlar (issue) yozuvlari soni
    - resolved_count / open_count: shu oynadagi issue'lardan nechtasi
      hal qilingan (is_resolved=1) va nechtasi hali ochiq
    - resolve_rate_pct: resolved_count / flagged_students_total * 100
    """
    from shared.local_db import (
        get_local_connection,
        ensure_group_check_logs_table_exists,
        ensure_student_issues_log_table_exists,
    )

    ensure_group_check_logs_table_exists()
    ensure_student_issues_log_table_exists()

    # 1) PostgreSQL'dan aktiv guruhlar + ularning assistenti
    query = """
    SELECT
        g.id            AS group_id,
        g.name          AS group_name,
        g.assistant_id  AS assistant_id,
        CONCAT_WS(' ', u.first_name, u.last_name) AS assistant_full_name
    FROM study_group g
    LEFT JOIN app_user u ON u.id = g.assistant_id
    WHERE g.status = 'active'
    ORDER BY g.id;
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            group_rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"Dashboard guruhlarini olishda xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    groups_out = {
        row.group_id: {
            "group_id": row.group_id,
            "group_name": row.group_name,
            "assistant_id": row.assistant_id,
            "assistant_full_name": row.assistant_full_name or "Biriktirilmagan",
            "checks_count": 0,
            "last_checked_at": None,
            "last_check_status": None,
            "flagged_students_total": 0,
            "resolved_count": 0,
            "open_count": 0,
            "resolve_rate_pct": 0,
        }
        for row in group_rows
    }

    if not groups_out:
        return {"status": "success", "count": 0, "groups": []}

    rolling_window_days = 7
    rolling_window_start = datetime.now() - timedelta(days=rolling_window_days)

    # 2) Har bir guruh uchun eng so'nggi tekshiruv (barcha vaqt bo'yicha, cheklovsiz)
    try:
        with get_local_connection() as conn:
            last_check_rows = conn.execute(
                """
                SELECT group_id, checked_at, check_status
                FROM group_check_logs
                WHERE checked_at = (
                    SELECT MAX(checked_at) FROM group_check_logs gcl2
                    WHERE gcl2.group_id = group_check_logs.group_id
                )
                """
            ).fetchall()

            # 3) Oxirgi 7 kundagi tekshiruvlar soni (guruh bo'yicha)
            checks_count_rows = conn.execute(
                """
                SELECT group_id, COUNT(*) AS cnt
                FROM group_check_logs
                WHERE checked_at >= ?
                GROUP BY group_id
                """,
                (rolling_window_start.isoformat(),),
            ).fetchall()

            # 4) Oxirgi 7 kunda shu guruh uchun aniqlangan issue'lar
            # (check_id orqali group_check_logs bilan bog'lab, group_id chiqaramiz)
            issue_rows = conn.execute(
                """
                SELECT gcl.group_id AS group_id, sil.is_resolved AS is_resolved
                FROM student_issues_log sil
                JOIN group_check_logs gcl ON gcl.check_id = sil.check_id
                WHERE sil.created_at >= ?
                """,
                (rolling_window_start.isoformat(),),
            ).fetchall()
    except Exception as e:
        logger.error(f"Dashboard guruh statistikasini olishda xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    for row in last_check_rows:
        g = groups_out.get(row["group_id"])
        if g is not None:
            g["last_checked_at"] = row["checked_at"]
            g["last_check_status"] = row["check_status"]

    for row in checks_count_rows:
        g = groups_out.get(row["group_id"])
        if g is not None:
            g["checks_count"] = row["cnt"]

    for row in issue_rows:
        g = groups_out.get(row["group_id"])
        if g is not None:
            g["flagged_students_total"] += 1
            if row["is_resolved"]:
                g["resolved_count"] += 1
            else:
                g["open_count"] += 1

    for g in groups_out.values():
        if g["flagged_students_total"] > 0:
            g["resolve_rate_pct"] = round(100 * g["resolved_count"] / g["flagged_students_total"], 1)

    groups_list = list(groups_out.values())
    groups_list.sort(key=lambda g: g["flagged_students_total"], reverse=True)

    return {"status": "success", "count": len(groups_list), "groups": groups_list}


# ==============================================================================
# ⚙️ SETTINGS: ASSISTANTLARNI FAOLSIZLASHTIRISH (INACTIVE) ENDPOINTLARI
# ==============================================================================

@api_router.get("/settings/assistants", tags=["Settings"])
async def get_settings_assistants():
    """
    /settings sahifasi uchun BARCHA assistentlarni (inactive'lar ham) qaytaradi,
    har biriga is_disabled (inactive_assistants jadvalida bormi) belgisi bilan.
    """
    query = """
    SELECT
        u.id            AS assistant_id,
        CONCAT_WS(' ', u.first_name, u.last_name) AS full_name,
        u.phone_number,
        u.username,
        u.is_active     AS user_is_active
    FROM app_user u
    WHERE u.role = 'mentor_assistant' and u.is_active = TRUE
    ORDER BY u.id;
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"Settings uchun assistentlarni olishda xato: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    inactive_ids = set(get_inactive_assistant_ids())

    assistants_list = [
        {
            "assistant_id": row.assistant_id,
            "full_name": row.full_name,
            "phone_number": row.phone_number,
            "username": row.username,
            "is_active": row.user_is_active,
            "is_disabled": row.assistant_id in inactive_ids,
        }
        for row in rows
    ]

    return {"status": "success", "count": len(assistants_list), "assistants": assistants_list}


@api_router.post("/settings/assistants/{assistant_id}/disable", tags=["Settings"])
async def disable_assistant(assistant_id: int):
    """Assistantni inactive_assistants jadvaliga qo'shadi -- shundan so'ng
    u /api/assistants natijasida ko'rinmaydi."""
    try:
        add_inactive_assistant(assistant_id)
    except Exception as e:
        logger.error(f"Assistantni o'chirishda xato (assistant_id={assistant_id}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return {"status": "success", "assistant_id": assistant_id, "is_disabled": True}


@api_router.post("/settings/assistants/{assistant_id}/enable", tags=["Settings"])
async def enable_assistant(assistant_id: int):
    """Assistantni inactive_assistants jadvalidan olib tashlaydi (qayta faollashtirish)."""
    try:
        remove_inactive_assistant(assistant_id)
    except Exception as e:
        logger.error(f"Assistantni qayta faollashtirishda xato (assistant_id={assistant_id}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return {"status": "success", "assistant_id": assistant_id, "is_disabled": False}


@api_router.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

@api_router.post("/test", tags=["Test Endpoint"])
async def test_endpoint(payload: dict):
    """
    Test endpoint for debugging and development purposes.
    Simply echoes back the received JSON payload.
    """
    logger.debug(f"Received test payload: {payload}")
    return {"status": "success", "received_payload": payload}