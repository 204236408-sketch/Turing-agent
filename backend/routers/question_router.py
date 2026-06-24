"""
题目管理接口（半成品需要深化）

功能：
- POST /api/questions/generate              — 手动指定参数生成题目
- GET  /api/questions/recommendations        — 获取智能推荐题目列表
- POST /api/questions/generate-smart         — 按推荐模式智能生成题目
- GET  /api/questions/session/{id}           — 获取出题批次的详情
- GET  /api/questions/detail/{id}            — 题目详情
- GET  /api/questions/{id}/hints             — 获取题目提示
- GET  /api/questions/{id}/videos            — 获取推荐视频
- POST /api/questions/{id}/mastery           — 针对某题设置掌握状态
- POST /api/questions/mastery                — 通用设置掌握状态
- POST /api/questions/{id}/interaction       — 记录题目交互（空实现）

状态：半成品需要深化。出题、推荐、掌握度功能完整；交互接口为空实现，
      缺少题目编辑、删除、批量操作等功能。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from agents.question_agent import generate_questions
from database import get_db
from dependencies import get_current_user
from models import Question, QuestionGenerationSession, User, VideoResource
from schemas import MasteryFeedbackRequest, QuestionGenerateRequest, SmartQuestionGenerateRequest
from services.mastery_service import apply_manual_feedback
from services.recommendation_service import build_smart_recommendations, resolve_smart_recommendation
from services.serialization import question_to_dict
from utils.response import AppError, success


router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.post("/generate")
def generate(payload: QuestionGenerateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = generate_questions(db, user.id, payload.mode, payload.subject, payload.knowledge_point, payload.difficulty, payload.question_type, payload.count)
    db.commit()
    return success(data)


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return success({"items": build_smart_recommendations(db, user.id)})


@router.post("/generate-smart")
def generate_smart(payload: SmartQuestionGenerateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    recommendation = resolve_smart_recommendation(db, user.id, payload.recommend_mode)
    data = generate_questions(
        db,
        user.id,
        recommendation["mode"],
        recommendation["subject"],
        recommendation["knowledge_point"],
        recommendation["difficulty"],
        recommendation["question_type"],
        payload.count,
        recommendation_reason=recommendation["reason"],
    )
    db.commit()
    return success({**data, "recommendation": recommendation})


@router.get("/session/{session_id}")
def session_detail(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.query(QuestionGenerationSession).filter(QuestionGenerationSession.id == session_id, QuestionGenerationSession.user_id == user.id).first()
    if not session:
        raise AppError("SESSION_NOT_FOUND", "出题批次不存在", status_code=404)
    return success({"session_id": session.id, "questions": [question_to_dict(q) for q in session.questions]})


@router.get("/detail/{question_id}")
def detail(question_id: int, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise AppError("QUESTION_NOT_FOUND", "题目不存在", status_code=404)
    return success({"question": question_to_dict(question)})


@router.get("/{question_id}/hints")
def hints(question_id: int, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise AppError("QUESTION_NOT_FOUND", "题目不存在", status_code=404)
    return success({"hints": question_to_dict(question)["hints"]})


@router.get("/{question_id}/videos")
def videos(question_id: int, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise AppError("QUESTION_NOT_FOUND", "题目不存在", status_code=404)
    rows = db.query(VideoResource).filter(VideoResource.subject == question.subject).limit(5).all()
    return success({"items": [{"id": r.id, "title": r.title, "url": r.url, "reason": r.reason} for r in rows]})


@router.post("/{question_id}/mastery")
def mastery_by_question(question_id: int, payload: MasteryFeedbackRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise AppError("QUESTION_NOT_FOUND", "题目不存在", status_code=404)
    item = apply_manual_feedback(db, user.id, question.subject, question.knowledge_point, payload.status, payload.mistake_id, question.id)
    db.commit()
    return success({"status": item.final_status, "weak_score": item.weak_score})


@router.post("/mastery")
def mastery(payload: MasteryFeedbackRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = apply_manual_feedback(db, user.id, payload.subject, payload.knowledge_point, payload.status, payload.mistake_id, payload.question_id)
    db.commit()
    return success({"status": item.final_status, "weak_score": item.weak_score})


@router.post("/{question_id}/interaction")
def interaction(question_id: int):
    return success({"question_id": question_id, "logged": True})
