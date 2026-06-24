"""
问答聊天接口（半成品需要深化）

功能：
- POST /api/qa/chat    — 发起问答对话（创建/追加会话 → 调用 qa_agent → 更新掌握度）
- GET  /api/qa/history — 获取问答历史会话列表

状态：半成品需要深化。基本问答流程可用，但功能较简单：无流式响应、无上下文管理优化、
      无会话删除功能、无消息删除/编辑支持。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from agents.qa_agent import answer_question
from database import get_db
from dependencies import get_current_user
from models import Conversation, ConversationMessage, KnowledgeMastery, User
from schemas import QaChatRequest
from services.mastery_service import get_or_create_mastery, recalculate_mastery
from utils.response import success


router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("/chat")
def chat(payload: QaChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = None
    if payload.conversation_id:
        conversation = db.query(Conversation).filter(Conversation.id == payload.conversation_id, Conversation.user_id == user.id).first()
    if not conversation:
        conversation = Conversation(user_id=user.id, title=payload.question[:30] or "408 问答")
        db.add(conversation)
        db.flush()
    db.add(ConversationMessage(conversation_id=conversation.id, role="user", content=payload.question))
    db.commit()
    conversation_id = conversation.id

    result = answer_question(db, user.id, payload.question)
    db.add(ConversationMessage(conversation_id=conversation_id, role="assistant", content=result["answer"]))
    mastery = get_or_create_mastery(db, user.id, result["subject"], result["knowledge_point"])
    mastery.qa_count += 1
    recalculate_mastery(db, user.id, result["subject"], result["knowledge_point"])
    db.commit()
    return success({"conversation_id": conversation_id, **result})


@router.get("/history")
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.update_time.desc()).all()
    return success({"items": [{"id": row.id, "title": row.title, "summary": row.summary, "update_time": row.update_time.isoformat()} for row in rows]})
