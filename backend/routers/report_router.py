"""
学习报告接口（半成品需要深化）

功能：
- GET /api/reports/overview    — 获取报告概览（统计数据、四科趋势、推荐计划、记忆权重、用户画像标签）
- GET /api/reports/summary     — 获取最新报告摘要
- POST /api/reports/generate   — 生成新学习报告（调用 report_agent）
- GET  /api/reports/history    — 历史报告列表
- GET  /api/reports/{id}       — 获取特定报告详情

状态：半成品需要深化。报告生成与概览逻辑较完整，但计算逻辑复杂（趋势分、记忆权重、画像标签），
      缺乏报告对比、导出、可视化数据接口。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from agents.report_agent import generate_report, report_to_dict
from database import get_db
from dependencies import get_current_user
from models import AnswerRecord, KnowledgeMastery, KnowledgePoint, Mistake, Report, User, UserMemory
from services.mastery_service import synchronize_user_mastery
from services.recommendation_service import build_smart_recommendations
from utils.response import AppError, success


router = APIRouter(prefix="/api/reports", tags=["reports"])

SUBJECTS = ["数据结构", "计算机组成原理", "操作系统", "计算机网络"]


def _valid_learning_point(subject: str, knowledge_point: str) -> bool:
    if subject not in SUBJECTS:
        return False
    value = (knowledge_point or "").strip()
    return bool(value) and value != "待生成" and "?" not in value


def _rate(part: int, total: int) -> int:
    return round(part * 100 / total) if total else 0


def _subject_payload(subject: str, answers: list[AnswerRecord], masteries: list[KnowledgeMastery]) -> dict:
    subject_answers = [item for item in answers if item.subject == subject]
    subject_masteries = [item for item in masteries if item.subject == subject]
    total = len(subject_answers)
    correct = sum(1 for item in subject_answers if item.is_correct)
    answer_rate = _rate(correct, total)
    touched = [item for item in subject_masteries if item.final_status != "未学"]
    mastered = sum(1 for item in subject_masteries if item.final_status == "掌握")
    weak = sum(1 for item in subject_masteries if item.final_status in {"薄弱点", "不会", "不熟"})
    avg_weak = sum(item.weak_score or 0 for item in subject_masteries) / max(len(subject_masteries), 1)
    mastery_rate = _rate(mastered, len(touched))
    if total or touched:
        score = max(0, min(100, round(answer_rate * 0.65 + mastery_rate * 0.35 - min(avg_weak, 30))))
    else:
        score = 0
    return {
        "subject": subject,
        "score": score,
        "answer_count": total,
        "correct_count": correct,
        "correct_rate": answer_rate,
        "mastered_count": mastered,
        "weak_count": weak,
        "note": f"答题 {total} 道，正确率 {answer_rate}%，薄弱点 {weak} 个" if total or touched else "暂无学习记录",
    }


def _memory_weights(masteries: list[KnowledgeMastery], memories: list[UserMemory]) -> list[dict]:
    memory_counts: dict[tuple[str, str], int] = {}
    for memory in memories:
        key = (memory.subject, memory.knowledge_point)
        memory_counts[key] = memory_counts.get(key, 0) + 1
    rows = []
    for item in masteries:
        if not _valid_learning_point(item.subject, item.knowledge_point):
            continue
        count = memory_counts.get((item.subject, item.knowledge_point), 0)
        weight = max(0, item.weak_score or 0) + count * 2 + (item.unknown_count or 0) * 2 + (item.unfamiliar_count or 0) + (item.ocr_mistake_count or 0) * 2
        if weight > 0:
            rows.append({
                "subject": item.subject,
                "knowledge_point": item.knowledge_point,
                "weight": round(weight, 1),
                "status": item.final_status,
                "reason": f"长期记忆 {count} 条 · 历史错题 {item.wrong_count} 次",
            })
    rows.sort(key=lambda x: (-x["weight"], x["subject"], x["knowledge_point"]))
    return rows[:6]


def _profile_tags(answers: list[AnswerRecord], masteries: list[KnowledgeMastery], memories: list[UserMemory], mistakes: list[Mistake]) -> list[str]:
    total = len(answers)
    correct = sum(1 for item in answers if item.is_correct)
    tags = []
    if total:
        tags.append(f"累计答题 {total} 道")
        rate = correct / total
        if rate >= 0.8:
            tags.append("高正确率学习者")
        elif rate >= 0.6:
            tags.append("稳定提升中")
        else:
            tags.append("需要基础巩固")
    else:
        tags.append("暂无答题画像")
    if masteries:
        strongest = max(SUBJECTS, key=lambda s: sum(1 for m in masteries if m.subject == s and m.final_status == "掌握"))
        if any(m.subject == strongest and m.final_status == "掌握" for m in masteries):
            tags.append(f"{strongest}优势")
        weak_rows = [m for m in masteries if m.final_status in {"薄弱点", "不会", "不熟"} and _valid_learning_point(m.subject, m.knowledge_point)]
        if weak_rows:
            weak = max(weak_rows, key=lambda m: (m.weak_score or 0, m.wrong_count or 0))
            tags.append(f"重点补强：{weak.knowledge_point}")
        qa_total = sum(m.qa_count or 0 for m in masteries)
        if qa_total >= 3:
            tags.append("问答驱动型学习")
        if any((m.ocr_mistake_count or 0) > 0 for m in masteries):
            tags.append("纸质错题已纳入复盘")
    if memories:
        tags.append(f"长期记忆 {len(memories)} 条")
    if mistakes:
        error_counts: dict[str, int] = {}
        for mistake in mistakes:
            if mistake.error_type:
                error_counts[mistake.error_type] = error_counts.get(mistake.error_type, 0) + 1
        if error_counts:
            tags.append(f"常见错因：{max(error_counts, key=error_counts.get)}")
    return tags[:8]


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    points = db.query(KnowledgePoint).all()
    if points:
        synchronize_user_mastery(db, user.id, [(point.subject, point.name) for point in points])
    answers = db.query(AnswerRecord).filter(AnswerRecord.user_id == user.id).all()
    masteries = db.query(KnowledgeMastery).filter(KnowledgeMastery.user_id == user.id).all()
    memories = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user.id, UserMemory.status == "active")
        .order_by(UserMemory.update_time.desc(), UserMemory.id.desc())
        .all()
    )
    mistakes = (
        db.query(Mistake)
        .filter(Mistake.user_id == user.id, Mistake.status == "active")
        .order_by(Mistake.create_time.desc(), Mistake.id.desc())
        .all()
    )
    total = len(answers)
    correct = sum(1 for item in answers if item.is_correct)
    wrong = total - correct
    recommendations = [item for item in build_smart_recommendations(db, user.id) if item.get("available")]
    if not recommendations:
        recommendations = build_smart_recommendations(db, user.id)
    return success({
        "stats": {
            "total": total,
            "correct": correct,
            "wrong": wrong,
            "accuracy": _rate(correct, total),
        },
        "subject_trends": [_subject_payload(subject, answers, masteries) for subject in SUBJECTS],
        "next_plan": recommendations[:3],
        "memory_weights": _memory_weights(masteries, memories),
        "profile": {
            "name": user.nickname or user.username,
            "avatar": (user.nickname or user.username or "图")[0],
            "target": "2026 计算机考研 · 408",
            "tags": _profile_tags(answers, masteries, memories, mistakes),
        },
        "rules": {
            "subject_trend": "四科掌握趋势综合答题正确率、已掌握知识点占比和薄弱状态生成。",
            "memory_weight": "长期记忆权重综合错题、不会/不熟标记、OCR错题和长期记忆条目生成。",
            "profile_tags": "学习画像标签由答题量、正确率、优势科目、最高薄弱点、问答次数、OCR错题、长期记忆和常见错因生成。",
        },
    })


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    latest = db.query(Report).filter(Report.user_id == user.id).order_by(Report.create_time.desc()).first()
    if not latest:
        return success({"summary": "暂无报告，点击生成即可创建。"})
    return success({"summary": latest.summary, "report": report_to_dict(latest)})


@router.post("/generate")
def generate(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = generate_report(db, user.id)
    db.commit()
    return success(data)


@router.get("/history")
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Report).filter(Report.user_id == user.id).order_by(Report.create_time.desc()).all()
    return success({"items": [report_to_dict(r) for r in rows]})


@router.get("/{report_id}")
def detail(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Report).filter(Report.id == report_id, Report.user_id == user.id).first()
    if not row:
        raise AppError("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    return success({"report": report_to_dict(row)})
