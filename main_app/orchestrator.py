"""
main_app: to'liq pipeline'ni ketma-ket ishga tushiradigan orchestrator.

Pipeline endi ikki bosqichga bo'lingan:
  1) PREVIEW  -- run_preview_stage(): DB'dan barcha studentlarni (progress
     snapshot) oladi, progress-AI tahlilini o'tkazadi va har bir guruh uchun
     TO'LIQ student ro'yxatini (muammoli/muammosiz belgisi bilan) qaytaradi.
     Bu bosqich frontend'da ko'rsatiladi va foydalanuvchi "Davom etish"
     tugmasini bosguncha pipeline shu yerda TO'XTAB TURADI.
  2) CONTINUE -- run_continue_stream(): foydalanuvchi tasdiqlagan
     student_id'lar bo'yicha chat tarixini oladi va AI tahlili (summary)
     bosqichini bajaradi, natijalarni streaming tarzda qaytaradi.

Ikkala bosqich orasidagi holat (preview natijasi) main_app.preview_store
orqali xotirada (in-memory) saqlanadi (preview_id bilan).
"""
import asyncio
import uuid
from dataclasses import asdict
from typing import AsyncGenerator

from shared.local_db import (
    ensure_tracking_table_exists,
    ensure_ai_reports_table_exists,
    ensure_assistant_tg_info_table_exists,
    ensure_group_check_logs_table_exists,
    ensure_student_issues_log_table_exists,
    insert_group_check_log,
    insert_student_issues,
    resolve_student_issues,
    categorize_issue,
)
from shared.models import InteractionReport, AssistantStudentTarget, StudentProblem
from shared.logger import get_logger
from accounts_app.repository import (
    fetch_group_progress_snapshots,
    fetch_group_students_display_info,
    resolve_targets_for_problems_with_assistant,
)
from accounts_app.progress_analyzer import analyze_group_progress_batch, only_with_problem
from chat_history_app.fetcher import fetch_all_histories_for_leader
from ai_agent_app.analyzer import analyze_chat_history
from ai_agent_app.reports_repository import save_reports_batch
from main_app.preview_store import save_preview, get_preview

logger = get_logger(__name__)


def _assistant_student_target_to_dict(target: AssistantStudentTarget) -> dict:
    """AssistantStudentTarget'ni frontend uchun tekis (flat) dict'ga o'giradi."""
    return {
        "student_id": target.student.student_id,
        "full_name": target.student.full_name,
        "group_id": target.student.group_id,
        "problem": target.problem,
        "assistant": {
            "assistant_id": target.assistant.assistant_id,
            "full_name": target.assistant.full_name,
        },
    }


# ============================================================
# 1-BOSQICH: PREVIEW -- progress + progress-AI, pipeline shu yerda to'xtaydi
# ============================================================

async def run_preview_stage(group_ids: list[int], assistant_id: int) -> dict:
    """
    Berilgan guruhlar uchun:
      1) DB'dan barcha (faol) studentlarning progress snapshot'ini oladi
         (hw_count va h.k. -- AI'ga yuborilmasdan oldingi xom data).
      2) Progress-AI tahlilini ishga tushiradi (has_problem/problem).
      3) Har bir guruh uchun ALOHIDA jadval sifatida to'liq student
         ro'yxatini (muammoli bo'lganlari belgilangan holda) qaytaradi.

    Natija xotirada (preview_store) `preview_id` bilan saqlanadi -- keyinchalik
    /api/check_groups/continue shu id orqali progress bosqichini QAYTA
    ISHLAMASDAN, to'g'ridan-to'g'ri chat+AI-summary bosqichiga o'tadi.

    Pipeline bu yerda TO'XTAYDI -- chat tarixi hali olinmaydi, AI-summary
    hali chaqirilmaydi. Davom etish uchun alohida so'rov (continue) kerak.
    """
    logger.info(
        f"=== Preview bosqichi boshlandi (group_ids={group_ids}, assistant_id={assistant_id}) ==="
    )

    snapshots = fetch_group_progress_snapshots(group_ids)
    if not snapshots:
        return {
            "status": "error",
            "message": "Hech qanday guruh topilmadi.",
            "groups": [],
        }

    # Progress-AI tahlili -- har bir student uchun has_problem/problem.
    try:
        problems = await analyze_group_progress_batch(snapshots)
    except Exception as e:
        logger.error(f"[preview] progress tahlilida xato: {e}")
        return {
            "status": "error",
            "message": str(e),
            "groups": [],
        }

    problems_by_student: dict[int, StudentProblem] = {p.student_id: p for p in problems}

    # Har bir guruh uchun "pasport" yozuvini saqlaymiz (audit/trend uchun) --
    # xuddi avvalgi oqimdagidek, lekin endi bu preview bosqichida qilinadi.
    problems_by_group: dict[int, list[StudentProblem]] = {}
    for p in problems:
        problems_by_group.setdefault(p.group_id, []).append(p)

    for snapshot in snapshots:
        group_problems = problems_by_group.get(snapshot.group_id, [])
        flagged = [p for p in group_problems if p.problem]
        try:
            check_id = insert_group_check_log(
                group_id=snapshot.group_id,
                assistant_id=assistant_id,
                flagged_count=len(flagged),
                check_status="success",
            )
            if flagged:
                insert_student_issues(
                    check_id=check_id,
                    issues=[(p.student_id, p.problem) for p in flagged],
                )
        except Exception as e:
            logger.error(f"group_check_logs/student_issues_log yozishda xato: group_id={snapshot.group_id}: {e}")

    # Har bir guruh uchun to'liq (muammoli + muammosiz) student jadvalini yasaymiz.
    groups_out = []
    for snapshot in snapshots:
        display_names = fetch_group_students_display_info(snapshot.group_id)
        students_out = []
        for s in snapshot.students:
            problem_info = problems_by_student.get(s.student_id)
            has_problem = bool(problem_info and problem_info.problem)
            students_out.append({
                "student_id": s.student_id,
                "full_name": display_names.get(s.student_id, f"Student #{s.student_id}"),
                "uploaded_homeworks_count": s.uploaded_homeworks_count,
                "last_upload_date": s.last_upload_date,
                "has_problem": has_problem,
                "problem": problem_info.problem if problem_info else None,
            })

        # Guruhning hozirgi modul/dars holati -- faqat frontendda ko'rsatish uchun,
        # tahlilga (AI'ga) yuborilmaydi.
        progress = snapshot.progress_info
        progress_out = {
            "current_lesson": progress.current_lesson if progress else None,
            "current_lesson_number": progress.current_lesson_number if progress else None,
            "tool": progress.tool if progress else None,
            "module": progress.module if progress else None,
        }

        groups_out.append({
            "group_id": snapshot.group_id,
            "group_name": snapshot.group_name,
            "progress": progress_out,
            "students": students_out,
        })

    problematic = only_with_problem(problems)

    preview_id = str(uuid.uuid4())
    save_preview(preview_id, {
        "assistant_id": assistant_id,
        "group_ids": group_ids,
        "problematic": problematic,  # list[StudentProblem], faqat muammolilar
    })

    total_students = sum(len(g["students"]) for g in groups_out)
    logger.info(
        f"=== Preview bosqichi tugadi: {len(groups_out)} ta guruh, {total_students} ta student, "
        f"{len(problematic)} ta muammoli. preview_id={preview_id} ==="
    )

    return {
        "status": "success",
        "preview_id": preview_id,
        "groups": groups_out,
        "problematic_count": len(problematic),
    }


# ============================================================
# 2-BOSQICH: CONTINUE -- chat tarixi + AI-summary (streaming)
# ============================================================

async def run_continue_stream(
    preview_id: str,
    student_ids: list[int] | None = None,
) -> AsyncGenerator[dict, None]:
    """
    run_preview_stage orqali saqlangan preview natijasidan foydalanib,
    pipeline'ning ikkinchi bosqichini (chat tarixini olish -> AI tahlili)
    ishga tushiradi. Progress-AI tahlili QAYTA ISHLAMAYDI -- preview'da
    aniqlangan muammoli studentlar ro'yxati to'g'ridan-to'g'ri ishlatiladi.

    student_ids berilsa -- faqat shu ID'lar bo'yicha davom etiladi
    (foydalanuvchi ba'zi studentlarni bekor qilishi mumkin). berilmasa
    (None) -- preview'dagi barcha muammoli studentlar bilan davom etiladi.
    """
    preview = get_preview(preview_id)
    if preview is None:
        yield {
            "state": "error",
            "data": {"stage": "continue", "message": "Preview topilmadi yoki muddati o'tgan (preview_id noto'g'ri)."},
        }
        yield {"state": "done", "data": {"total_reports": 0}}
        return

    assistant_id: int = preview["assistant_id"]
    problematic: list[StudentProblem] = preview["problematic"]

    if student_ids is not None:
        wanted = set(student_ids)
        problematic = [p for p in problematic if p.student_id in wanted]

    logger.info(
        f"=== Continue bosqichi boshlandi (preview_id={preview_id}, "
        f"assistant_id={assistant_id}, students={[p.student_id for p in problematic]}) ==="
    )

    total_reports = 0

    if not problematic:
        yield {"state": "done", "data": {"total_reports": total_reports}}
        return

    # Muammoli studentlarni so'rovdan kelgan assistant_id bilan bog'laymiz.
    targets = resolve_targets_for_problems_with_assistant(problematic, assistant_id)

    def get_student_fullname(student_id: int) -> str:
        for t in targets:
            if t.student.student_id == student_id:
                return t.student.full_name
        return str(student_id)

    # print("TARGETS:", targets)
    yield {
        "state": "accounts",
        "data": {
            "group_ids": list({p.group_id for p in problematic}),
            "students": [_assistant_student_target_to_dict(t) for t in targets],
        },
    }

    if not targets:
        yield {"state": "done", "data": {"total_reports": total_reports}}
        return

    # Assistant bo'yicha guruhlab chatlarni tekshiramiz
    targets_by_assistant: dict[int, list[AssistantStudentTarget]] = {}
    for target in targets:
        targets_by_assistant.setdefault(target.assistant.assistant_id, []).append(target)

    for assistant_targets in targets_by_assistant.values():
        assistant = assistant_targets[0].assistant
        students = [t.student for t in assistant_targets]
        problems_by_student = {t.student.student_id: t.problem for t in assistant_targets}

        try:
            histories = await fetch_all_histories_for_leader(assistant, students, problems_by_student)
        except Exception as e:
            logger.error(f"[continue] assistant={assistant.assistant_id}: chat olishda xato: {e}")
            yield {
                "state": "error",
                "data": {
                    "stage": "chat_history_checking",
                    "assistant_id": assistant.assistant_id,
                    "message": str(e),
                },
            }
            continue

        histories_by_student = {h.student_id: h for h in histories}

        for target in assistant_targets:
            history = histories_by_student.get(target.student.student_id)
            if history is None:
                yield {
                    "state": "error",
                    "data": {
                        "stage": "chat_history_checking",
                        "assistant_id": assistant.assistant_id,
                        "student_id": target.student.student_id,
                        "student_name": target.student.full_name,
                        "message": "Chat tarixini olishda xato yuz berdi, o'tkazib yuborildi.",
                    },
                }
                continue

            if len(history.messages) == 0:
                logger.info(
                    f"[continue] assistant={assistant.assistant_id} student={target.student.student_id}: "
                    f"yangi xabar yo'q, AI tahliliga yuborilmadi."
                )
                yield {
                    "state": "chat_history_checking",
                    "data": {
                        "student": {
                            "student_id": history.student_id,
                            "student_name": target.student.full_name,
                            "assistant_id": history.assistant_id,
                            "problem": history.problem,
                            "message_count": 0,
                            "messages": [],
                            "skipped_reason": "no_new_messages",
                        }
                    },
                }
                continue

            yield {
                "state": "chat_history_checking",
                "data": {
                    "student": {
                        "student_id": history.student_id,
                        "student_name": target.student.full_name,
                        "assistant_id": history.assistant_id,
                        "problem": history.problem,
                        "message_count": len(history.messages),
                        "messages": [
                            {
                                "sender_role": m.sender_role,
                                "text": m.text,
                                "sent_at": m.sent_at.isoformat(),
                            }
                            for m in history.messages
                        ],
                    }
                },
            }

            # AI tahlili -> "summary" state.
            try:
                report = await analyze_chat_history(history)
            except Exception as e:
                logger.error(
                    f"[continue] AI tahlilida xato: assistant={history.assistant_id} "
                    f"student={history.student_id}: {e}"
                )
                yield {
                    "state": "error",
                    "data": {
                        "stage": "summary",
                        "assistant_id": history.assistant_id,
                        "student_id": history.student_id,
                        "message": str(e),
                    },
                }
                continue

            try:
                save_reports_batch([report])
            except Exception as e:
                logger.error(f"[continue] Reportni saqlashda xato: {e}")

            if getattr(report, "addressed_issues", False):
                try:
                    category = categorize_issue(report.problem) if report.problem else None
                    resolve_student_issues(report.student_id, issue_category=category)
                except Exception as e:
                    logger.error(
                        f"student_issues_log yangilashda xato: student_id={report.student_id}: {e}"
                    )

            total_reports += 1
            yield {"state": "summary", "data": asdict(report)}

    logger.info(f"=== Continue bosqichi tugadi. Jami {total_reports} ta report yaratildi. ===")
    yield {
        "state": "done",
        "data": {"total_reports": total_reports},
    }


# ============================================================
# ESKI (bir yaxlit) STREAMING PIPELINE -- orqaga moslik uchun saqlangan.
# Endi frontend preview -> continue ikki bosqichini ishlatadi, lekin bu
# funksiya boshqa chaqiruvchilar buzilmasligi uchun saqlab qolindi.
# ============================================================

async def run_full_pipeline_stream(
    group_ids: list[int],
    assistant_id: int,
) -> AsyncGenerator[dict, None]:
    """
    Eski xatti-harakat: progress tahlili + chat + AI-summary bosqichlarini
    bitta uzluksiz stream sifatida (pauzasiz) bajaradi.
    """
    logger.info(
        f"=== Streaming pipeline boshlandi (group_ids={group_ids}, "
        f"assistant_id={assistant_id}) ==="
    )

    preview = await run_preview_stage(group_ids, assistant_id)
    if preview["status"] != "success":
        yield {
            "state": "error",
            "data": {"stage": "accounts", "message": preview.get("message", "Noma'lum xato")},
        }
        yield {"state": "done", "data": {"total_reports": 0}}
        return

    if preview["problematic_count"] == 0:
        yield {
            "state": "accounts_batches",
            "data": {"group_ids": group_ids, "students": []},
        }
        yield {"state": "done", "data": {"total_reports": 0}}
        return

    async for event in run_continue_stream(preview["preview_id"], student_ids=None):
        yield event
