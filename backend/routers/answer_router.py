"""
答案批改接口（已完成可复用）

功能：
- POST /api/answers/check   — 提交用户作答，调用 answer_check_agent 进行 AI 批改与反馈
- GET  /api/answers/history — 获取当前用户最近 100 条答题记录

状态：已完成可复用。核心流程完整，Agent 批改逻辑在 answer_check_agent 中实现。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from agents.answer_check_agent import check_answer
from database import get_db
from dependencies import get_current_user
from models import AnswerRecord, User
from schemas import AnswerCheckRequest
from utils.response import success


router = APIRouter(prefix="/api/answers", tags=["answers"])


@router.post("/check")
def check(payload: AnswerCheckRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = check_answer(db, user.id, payload.question_id, payload.user_answer)
    db.commit()
    return success(data)


@router.get("/history")
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(AnswerRecord).filter(AnswerRecord.user_id == user.id).order_by(AnswerRecord.create_time.desc()).limit(100).all()
    return success({"items": [{"id": r.id, "question_id": r.question_id, "knowledge_point": r.knowledge_point, "is_correct": r.is_correct, "feedback": r.feedback} for r in rows]})
