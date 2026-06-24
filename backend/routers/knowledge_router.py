"""
知识点接口（已完成可复用）

功能：
- GET /api/knowledge/graph           — 获取全量知识图谱（按科目分组，含知识点级别、高频标记）
- GET /api/knowledge/high-frequency  — 获取高频考点列表
- GET /api/knowledge/recommend       — 获取智能推荐知识点列表

状态：已完成可复用。查询逻辑简单清晰，推荐逻辑委托 recommendation_service 实现。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import KnowledgePoint, User
from services.recommendation_service import build_smart_recommendations
from utils.response import success


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/graph")
def graph(db: Session = Depends(get_db)):
    rows = db.query(KnowledgePoint).order_by(KnowledgePoint.subject, KnowledgePoint.id).all()
    subjects: dict[str, list] = {}
    for row in rows:
        subjects.setdefault(row.subject, []).append(
            {
                "id": row.id,
                "name": row.name,
                "parent_name": row.parent_name,
                "level": row.level,
                "is_high_frequency": row.is_high_frequency,
                "content": row.content,
            }
        )
    return success({"subjects": subjects})


@router.get("/high-frequency")
def high_frequency(db: Session = Depends(get_db)):
    rows = db.query(KnowledgePoint).filter(KnowledgePoint.is_high_frequency == True).all()
    return success({"items": [{"subject": r.subject, "knowledge_point": r.name, "content": r.content} for r in rows]})


@router.get("/recommend")
def recommend(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return success({"items": build_smart_recommendations(db, user.id)})
