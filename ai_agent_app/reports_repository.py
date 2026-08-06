"""
ai_agent_app: yakuniy InteractionReport natijalarini ai_reports jadvaliga
(lokal SQLite) yozish.
"""
import json

from shared.local_db import get_local_connection
from shared.models import InteractionReport
from shared.logger import get_logger

logger = get_logger(__name__)

_INSERT_AI_REPORT = """
INSERT INTO ai_reports (student_id, assistant_id, problem, ai_summary, raw_json, last_contacted_date)
VALUES (?, ?, ?, ?, ?, ?);
"""


def save_report(report: InteractionReport) -> None:
    """
    Bitta InteractionReport'ni ai_reports jadvaliga (SQLite) yozadi:
    - problem: accounts_app bosqichida aniqlangan progress muammosi
    - ai_summary: ushbu chat tahlili bo'yicha AI xulosasi
    - raw_json: AI'dan kelgan to'liq raw javob (JSON matn sifatida)
    """
    raw_json = json.dumps(report.raw_model_response, ensure_ascii=False) if report.raw_model_response else None

    with get_local_connection() as conn:
        conn.execute(
            _INSERT_AI_REPORT,
            (report.student_id, report.assistant_id, report.problem, report.summary, raw_json, report.last_contacted_date),
        )
        conn.commit()

    logger.debug(f"ai_reports ga yozildi: assistant={report.assistant_id} student={report.student_id}")


def save_reports_batch(reports: list[InteractionReport]) -> None:
    """Bir nechta reportni ketma-ket ai_reports jadvaliga yozadi.
    Bitta yozuvda xato bo'lsa, qolganlari yozilishda davom etadi (fault isolation)."""
    saved = 0
    for report in reports:
        try:
            save_report(report)
            saved += 1
        except Exception as e:
            logger.error(
                f"ai_reports ga yozishda xato: assistant={report.assistant_id} student={report.student_id}: {e}"
            )
            continue
    logger.info(f"{saved}/{len(reports)} ta report ai_reports jadvaliga yozildi.")

