"""
用户画像接口（已完成可复用）

功能：
- GET /api/profile/overview — 获取用户画像概览（基本信息 + 学习统计：答题数、正确率、掌握/薄弱数）
- PUT /api/profile/update   — 更新用户画像（昵称、每日学习时长、学习阶段、目标日期）

状态：已完成可复用。逻辑简单清晰，字段齐全。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import AnswerRecord, KnowledgeMastery, User, UserProfile
from schemas import ProfileUpdateRequest
from utils.response import success


router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    total = db.query(AnswerRecord).filter(AnswerRecord.user_id == user.id).count()
    correct = db.query(AnswerRecord).filter(AnswerRecord.user_id == user.id, AnswerRecord.is_correct == True).count()
    mastery = db.query(KnowledgeMastery).filter(KnowledgeMastery.user_id == user.id).all()
    return success(
        {
            "user": {"id": user.id, "nickname": user.nickname, "email": user.email},
            "profile": {
                "target_exam": profile.target_exam if profile else "考研 408",
                "target_date": profile.target_date if profile else "2026-12-19",
                "daily_minutes": profile.daily_minutes if profile else 90,
                "learning_stage": profile.learning_stage if profile else "强化复习",
            },
            "stats": {
                "total_answer_count": total,
                "correct_rate": round(correct / total * 100, 1) if total else 0,
                "mastered": sum(1 for item in mastery if item.final_status == "掌握"),
                "weak": sum(1 for item in mastery if item.final_status in ["薄弱点", "不会"]),
            },
        }
    )


@router.put("/update")
def update_profile(payload: ProfileUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.nickname:
        user.nickname = payload.nickname
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile:
        if payload.daily_minutes is not None:
            profile.daily_minutes = payload.daily_minutes
        if payload.learning_stage:
            profile.learning_stage = payload.learning_stage
        if payload.target_date:
            profile.target_date = payload.target_date[:10]
    db.commit()
    return success({"updated": True})
