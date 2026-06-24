"""
掌握度追踪接口（半成品需要深化）

功能：
- GET /api/mastery/list         — 获取所有知识点掌握度（自动同步后返回）
- GET /api/mastery/detail       — 查询特定知识点掌握度详情
- POST /api/mastery/recalculate — 重算特定知识点的掌握度
- GET /api/mastery/summary      — 掌握度汇总统计（各状态数量）

状态：半成品需要深化。CRUD 存在但 detail/recalculate 有硬编码默认参数（操作系统/页面置换算法），
      掌握度五态分类逻辑在 mastery_service 中需要进一步验证合理性。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import KnowledgeMastery, KnowledgePoint, User
from services.mastery_service import recalculate_mastery, synchronize_user_mastery
from utils.response import success


router = APIRouter(prefix="/api/mastery", tags=["mastery"])


def payload(item: KnowledgeMastery) -> dict:
    return {
        "id": item.id,
        "subject": item.subject,
        "knowledge_point": item.knowledge_point,
        "final_status": item.final_status,
        "weak_score": item.weak_score,
        "total_answer_count": item.total_answer_count,
        "correct_count": item.correct_count,
        "wrong_count": item.wrong_count,
    }


@router.get("/list")
def list_mastery(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    points = db.query(KnowledgePoint).all()
    synchronize_user_mastery(db, user.id, [(point.subject, point.name) for point in points])
    db.commit()
    rows = db.query(KnowledgeMastery).filter(KnowledgeMastery.user_id == user.id).all()
    return success({"items": [payload(row) for row in rows]})


@router.get("/detail")
def detail(subject: str = Query("操作系统"), knowledge_point: str = Query("页面置换算法"), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = (
        db.query(KnowledgeMastery)
        .filter(KnowledgeMastery.user_id == user.id, KnowledgeMastery.subject == subject, KnowledgeMastery.knowledge_point == knowledge_point)
        .first()
    )
    return success({"item": payload(row) if row else None})


@router.post("/recalculate")
def recalculate(subject: str = "操作系统", knowledge_point: str = "页面置换算法", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = recalculate_mastery(db, user.id, subject, knowledge_point)
    db.commit()
    return success({"item": payload(item)})


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    points = db.query(KnowledgePoint).all()
    synchronize_user_mastery(db, user.id, [(point.subject, point.name) for point in points])
    db.commit()
    rows = db.query(KnowledgeMastery).filter(KnowledgeMastery.user_id == user.id).all()
    return success({"summary": {status: sum(1 for row in rows if row.final_status == status) for status in ["未学", "掌握", "不熟", "不会", "薄弱点"]}})
