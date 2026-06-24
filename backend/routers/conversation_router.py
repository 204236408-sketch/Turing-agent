"""
会话管理接口（半成品需要深化）

功能：
- GET  /api/conversation/list              — 获取当前用户所有会话列表
- GET  /api/conversation/detail/{id}       — 获取会话详情及消息列表
- POST /api/conversation/{id}/summary      — 生成会话摘要（当前为简单拼接前 30 字）

状态：半成品需要深化。列表/详情功能可用；摘要生成仅做文字拼接，未接入 AI，
      无新建会话、删除会话、修改标题等基础接口。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Conversation, ConversationMessage, User
from utils.response import AppError, success


router = APIRouter(prefix="/api/conversation", tags=["conversation"])


@router.get("/list")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.update_time.desc()).all()
    return success({"items": [{"id": row.id, "title": row.title, "summary": row.summary} for row in rows]})


@router.get("/detail/{conversation_id}")
def detail(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not row:
        raise AppError("CONVERSATION_NOT_FOUND", "会话不存在", status_code=404)
    messages = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == row.id).all()
    return success({"conversation": {"id": row.id, "title": row.title, "summary": row.summary}, "messages": [{"role": m.role, "content": m.content} for m in messages]})


@router.post("/{conversation_id}/summary")
def summarize(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not row:
        raise AppError("CONVERSATION_NOT_FOUND", "会话不存在", status_code=404)
    messages = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == row.id).order_by(ConversationMessage.id.desc()).limit(8).all()
    row.summary = "；".join([m.content[:30] for m in messages[::-1]]) or "暂无摘要"
    db.commit()
    return success({"summary": row.summary})
