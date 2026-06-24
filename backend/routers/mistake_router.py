"""
错题本接口（半成品需要深化）

功能：
- GET  /api/mistakes                  — 错题列表（含关联题目与 OCR 还原）
- GET  /api/mistakes/notebook         — 错题本（按掌握状态筛选，含详细字段）
- GET  /api/mistakes/{id}             — 错题详情
- POST /api/mistakes/cause-confirm    — 确认错题原因（调用 mistake_agent）
- POST /api/mistakes/retrain          — 生成同类训练建议（当前为桩，返回固定值）
- POST /api/mistakes/{id}/mastery     — 设置错题掌握状态

状态：半成品需要深化。错题列表/本/详情结构良好，cause-confirm 有 Agent 支撑；
      retrain 接口仅返回固定 mock 值，detail 返回字段偏少，缺少错题统计分析接口。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from agents.mistake_agent import confirm_cause
from database import get_db
from dependencies import get_current_user
from models import AnswerRecord, Mistake, Question, User
from schemas import CauseConfirmRequest, MasteryFeedbackRequest
from services.mastery_service import apply_manual_feedback
from utils.response import AppError, success


router = APIRouter(prefix="/api/mistakes", tags=["mistakes"])


def _ocr_question_text(error_reason: str) -> str:
    if not error_reason:
        return ""
    marker = "从图片识别到题目："
    if marker not in error_reason:
        return ""
    text = error_reason.split(marker, 1)[1]
    for stop in ("\n用户答案：", "\nAgent 推断标准答案：", "\n答案解析：", "\n错因分析："):
        if stop in text:
            text = text.split(stop, 1)[0]
    return text.strip()


@router.get("")
def list_mistakes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Mistake).filter(Mistake.user_id == user.id).order_by(Mistake.create_time.desc()).all()
    items = []
    for r in rows:
        q = db.query(Question).filter(Question.id == r.question_id).first()
        items.append({
            "id": r.id,
            "subject": r.subject,
            "knowledge_point": r.knowledge_point,
            "error_type": r.error_type,
            "suggestion": r.suggestion,
            "question_text": q.question_text if q else "",
            "question_id": r.question_id,
        })
    return success({"items": items})


@router.get("/notebook")
def notebook(status: str = Query("不熟,不会"), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    status_list = [s.strip() for s in status.split(",")]
    mistakes = (
        db.query(Mistake)
        .filter(
            Mistake.user_id == user.id,
            Mistake.status == "active",
            Mistake.mastery_status.in_(status_list),
        )
        .order_by(Mistake.create_time.desc())
        .all()
    )
    result = []
    for m in mistakes:
        q = db.query(Question).filter(Question.id == m.question_id).first()
        rec = None
        if m.answer_record_id:
            rec = db.query(AnswerRecord).filter(AnswerRecord.id == m.answer_record_id).first()
        question_text = q.question_text if q else _ocr_question_text(m.error_reason)
        standard_answer = q.standard_answer if q else ""
        explanation = q.explanation if q else ""
        if not standard_answer and "Agent 推断标准答案：" in (m.error_reason or ""):
            standard_answer = m.error_reason.split("Agent 推断标准答案：", 1)[1].split("\n", 1)[0].strip()
        if not explanation and "答案解析：" in (m.error_reason or ""):
            explanation = m.error_reason.split("答案解析：", 1)[1].split("\n", 1)[0].strip()
        result.append({
            "id": m.id,
            "subject": m.subject,
            "knowledge_point": m.knowledge_point,
            "mastery_status": m.mastery_status,
            "error_type": m.error_type,
            "error_reason": m.error_reason,
            "suggestion": m.suggestion,
            "input_type": m.input_type,
            "create_time": m.create_time.isoformat() if m.create_time else None,
            "question_id": m.question_id,
            "question_text": question_text,
            "options_json": q.options_json if q else "[]",
            "standard_answer": standard_answer,
            "explanation": explanation,
            "user_answer": rec.user_answer if rec else "",
            "is_correct": rec.is_correct if rec else False,
            "mastery_feedback": rec.mastery_feedback if rec else "",
        })
    return success({
        "items": result,
        "stats": {
            "unfamiliar": sum(1 for r in result if r["mastery_status"] == "不熟"),
            "unknown": sum(1 for r in result if r["mastery_status"] == "不会"),
            "total": len(result),
        }
    })


@router.get("/{mistake_id}")
def detail(mistake_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Mistake).filter(Mistake.id == mistake_id, Mistake.user_id == user.id).first()
    if not row:
        raise AppError("MISTAKE_NOT_FOUND", "错题不存在", status_code=404)
    return success({"item": {"id": row.id, "error_reason": row.error_reason, "suggestion": row.suggestion}})


@router.post("/cause-confirm")
def cause_confirm(payload: CauseConfirmRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = confirm_cause(db, user.id, payload.answer_record_id, payload.error_types, payload.user_note, payload.evidence_source)
    db.commit()
    return success(data)


@router.post("/retrain")
def retrain():
    return success({"message": "已根据错题生成同类训练建议", "count": 3})


@router.post("/{mistake_id}/mastery")
def set_mistake_mastery(mistake_id: int, payload: MasteryFeedbackRequest, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    m = db.query(Mistake).filter(Mistake.id == mistake_id, Mistake.user_id == user.id).first()
    if not m:
        raise AppError("MISTAKE_NOT_FOUND", "错题不存在", status_code=404)
    item = apply_manual_feedback(db, user.id, m.subject, m.knowledge_point, payload.status, mistake_id)
    db.commit()
    return success({"status": item.final_status, "weak_score": item.weak_score})
