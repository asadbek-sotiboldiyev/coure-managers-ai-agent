"""
Modullar orasida ma'lumot uzatish uchun umumiy data-class'lar (DTO).
Bu 4 ta modulni bir-biriga "yumshoq" bog'laydi -- faqat shu tiplar orqali gaplashadi.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

@dataclass
class AssistantInfo:
    assistant_id: int
    full_name: str
    tg_session_name: str  # assistant_tg_info dan -> pyrogram session nomi
    tg_user_id: Optional[int] = None


@dataclass
class StudentInfo:
    student_id: int
    full_name: str
    first_name: str
    last_name: str
    group_id: int
    tg_user_id: Optional[int] = None
    user_id_number: Optional[str] = None  # user.user_id_number -- Telegram dialoglarida studentni topish uchun kod


@dataclass
class AssistantWithStudents:
    assistant: AssistantInfo
    students: list[StudentInfo] = field(default_factory=list)


@dataclass
class ChatMessage:
    sender_role: str        # "assistant" | "student"
    text: str
    sent_at: datetime


@dataclass
class ScrubbedChatHistory:
    """
    chat_history_app dan chiqadigan, shaxsiy ma'lumotlar tozalangan natija.
    """
    assistant_id: int
    student_id: int
    messages: list[ChatMessage] = field(default_factory=list)
    last_check_date: Optional[datetime] = None
    problem: Optional[str] = None  # accounts_app bosqichida shu student uchun aniqlangan progress muammosi

    def to_prompt_text(self) -> str:
        """AI modeliga yuboriladigan formatga o'giradi (ismlar o'rniga ID)."""
        lines = []
        for m in self.messages:
            speaker = f"assistant_{self.assistant_id}" if m.sender_role == "assistant" or m.sender_role == "leader" else f"student_{self.student_id}"
            lines.append(f"[{m.sent_at.isoformat()}] {speaker}: {m.text}")
        return "\n".join(lines)


@dataclass
class InteractionReport:
    """
    ai_agent_app ning yakuniy strukturaviy natijasi.
    """
    assistant_id: int
    student_id: int
    support_quality_score: int          # 1-10
    addressed_issues: bool
    discussed_flagged_problem: bool
    summary: str
    recommendations: str
    problem: Optional[str] = None       # accounts_app bosqichida aniqlangan progress muammosi
    raw_model_response: Optional[dict] = None
    last_contacted_date: Optional[str] = None


# ============================================================
# Progress-tekshirish oqimi uchun DTO'lar (accounts_app)
# ============================================================

@dataclass
class StudentProgressInfo:
    """
    Bitta studentning joriy progress holati -- AI'ga progress-tahlil
    uchun yuboriladigan xom (lekin allaqachon anonim -- faqat ID'lar) ma'lumot.

    uploaded_homeworks_count -- joriy moduldagi vazifalardan nechtasini
    (ai_assistant_score > 0 bo'lgan holda) topshirgani.
    last_upload_date -- oxirgi topshirilgan vazifa sanasi (DD-MM-YYYY, bo'lmasa None).
    """
    student_id: int
    uploaded_homeworks_count: int = 0
    last_upload_date: Optional[str] = None


@dataclass
class GroupProgressInfo:
    """
    Guruhning hozirgi turgan modul/dars holati haqida to'liq ma'lumot
    (frontendda ko'rsatish uchun). Bu obyekt AI'ga YUBORILMAYDI --
    faqat progress_analyzer tashqarisida, frontend uchun preview
    natijasiga qo'shiladi.
    """
    group_id: int
    group_name: str
    current_lesson: Optional[str] = None
    current_lesson_number: Optional[int] = None
    tool: Optional[str] = None
    module: Optional[str] = None


@dataclass
class GroupProgressSnapshot:
    """
    Bitta guruhning barcha studentlari progress holati bilan --
    AI'ga "guruh ichida solishtirish" imkonini beradi (kim ko'proq orqada qolgan).

    group_name faqat frontendda ko'rsatish uchun saqlanadi -- AI'ga
    yuboriladigan payload'ga (progress_analyzer.analyze_group_progress)
    group_name QO'SHILMAYDI, faqat student_id + progress raqamlari ketadi.
    """
    group_id: int
    group_name: str
    students: list[StudentProgressInfo] = field(default_factory=list)
    progress_info: Optional[GroupProgressInfo] = None


@dataclass
class StudentProblem:
    """
    accounts_app bosqichida AI progress-tahlili natijasida bitta student uchun
    chiqadigan xulosa. problem=None bo'lsa, muammo aniqlanmagan (keyingi
    bosqichga yuborilmaydi).
    """
    student_id: int
    group_id: int
    problem: Optional[str]


@dataclass
class AssistantStudentTarget:
    """
    Progress bosqichida muammo aniqlangan studentni o'z assistenti bilan
    bog'lab, keyingi (chat_history_app) bosqichga yuborish uchun to'liq nishon.
    """
    assistant: AssistantInfo
    student: StudentInfo
    problem: str


@dataclass
class AIReport:
    """
    ai_reports jadvaliga yoziladigan yakuniy yozuv:
    progress muammosi + chat tahlili xulosasi + AI'dan kelgan to'liq raw JSON.
    """
    student_id: int
    assistant_id: int
    problem: Optional[str]
    ai_summary: Optional[str]
    raw_json: Optional[str]


class SendCodeRequest(BaseModel):
    assistant_id: int = Field(..., description="Assistant (user) ID")
    phone_number: str = Field(..., example="+998901234567", description="Xalqaro formatdagi telefon raqam")

class VerifyCodeRequest(BaseModel):
    phone_number: str = Field(..., example="+998901234567", description="Xalqaro formatdagi telefon raqam")
    code: str = Field(..., example="12345", description="Telegramdan kelgan tasdiqlash kodi")

class VerifyPasswordRequest(BaseModel):
    phone_number: str = Field(..., example="+998901234567", description="Xalqaro formatdagi telefon raqam")
    password: str = Field(..., description="2FA (Ikki bosqichli tasdiqlash) paroli")


class GroupsCheckRequest(BaseModel):
    assistant_id: int
    group_ids: list[int]


class PreviewCheckRequest(BaseModel):
    """
    /api/check_groups/preview uchun so'rov: guruhlar ro'yxati va assistent.
    Bu bosqichda hali chat/AI-summary ishlamaydi -- faqat DB'dan olingan
    xom student ma'lumotlari (hw_count va h.k.) + progress-AI natijasi
    (has_problem/problem) frontendga ko'rsatiladi.
    """
    assistant_id: int
    group_ids: list[int]


class ContinueCheckRequest(BaseModel):
    """
    /api/check_groups/preview orqali qaytarilgan preview_id va foydalanuvchi
    tasdiqlagan (yoki hammasi) student_id'lar ro'yxati bilan pipeline'ning
    ikkinchi (chat + AI summary) bosqichini davom ettirish uchun so'rov.
    """
    preview_id: str
    student_ids: Optional[list[int]] = None  # None bo'lsa -- barcha muammoli studentlar