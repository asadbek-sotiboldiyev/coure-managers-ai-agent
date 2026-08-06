"""
accounts_app: progress-tekshirish bosqichi uchun Pydantic schema.
Gemini javobi shu strukturaga majburiy moslanadi (with_structured_output orqali).
"""
from pydantic import BaseModel, Field


class StudentProblemResult(BaseModel):
    """Bitta student uchun progress tahlili natijasi."""

    student_id: int = Field(description="Talabaning student_id qiymati")
    has_problem: bool = Field(
        description="Talabada guruhdagi boshqalarga yoki lesson/homework nisbatiga qarab muammo bormi"
    )
    problem: str = Field(
        default="",
        description=(
            "has_problem=true bo'lsa, muammoning qisqa tavsifi "
            "(masalan: 'bajargan homeworklar lessonlardan sezilarli kam', "
            "yoki 'guruhdagilardan progress bo'yicha ancha orqada qolgan'). "
            "has_problem=false bo'lsa bo'sh qatur qoldiring."
        ),
    )


class GroupProgressAnalysis(BaseModel):
    """Bitta guruh ichidagi barcha studentlar bo'yicha progress tahlili natijasi."""

    results: list[StudentProblemResult] = Field(
        description="Guruhdagi har bir student uchun alohida tahlil natijasi"
    )
