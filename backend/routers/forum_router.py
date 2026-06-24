"""
论坛社区接口（半成品需要深化）

功能：
- GET    /api/forum/categories               — 获取论坛分类列表
- GET    /api/forum/posts                    — 搜索/筛选帖子列表
- POST   /api/forum/posts                    — 创建帖子
- GET    /api/forum/posts/{id}               — 帖子详情
- PUT    /api/forum/posts/{id}               — 更新帖子（仅作者）
- DELETE /api/forum/posts/{id}               — 删除帖子（软删除）
- POST   /api/forum/posts/{id}/like          — 点赞
- POST   /api/forum/posts/{id}/unlike        — 取消点赞
- GET    /api/forum/posts/{id}/comments      — 获取评论列表
- POST   /api/forum/posts/{id}/comments      — 添加评论
- POST   /api/forum/comments/{id}/reply      — 回复评论
- POST   /api/forum/posts/{id}/ai-answer     — AI 回答帖子
- POST   /api/forum/posts/{id}/ai-followup   — AI 追问回答
- GET    /api/forum/hot                      — 热门帖子（按热度排序）
- GET    /api/forum/checkin/status           — 打卡状态
- POST   /api/forum/checkin                  — 执行打卡
- GET    /api/forum/my-posts                 — 我的帖子列表

状态：半成品需要深化。CRUD 完整，AI 回答/追问有基本实现；无分页，AI 追问仅用简单提示词 + fallback。
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from agents.forum_agent import ai_answer_for_post
from database import get_db
from dependencies import get_current_user
from models import ForumCategory, ForumCheckin, ForumComment, ForumPost, User
from schemas import ForumCommentRequest, ForumPostRequest
from services.llm_service import chat_completion
from utils.response import AppError, success

router = APIRouter(prefix="/api/forum", tags=["forum"])


def relative_time(dt: datetime) -> str:
    delta = datetime.utcnow() - dt
    if delta.days > 7:
        return dt.strftime("%m-%d")
    if delta.days > 0:
        return f"{delta.days} 天前"
    if delta.seconds >= 3600:
        return f"{delta.seconds // 3600} 小时前"
    if delta.seconds >= 60:
        return f"{delta.seconds // 60} 分钟前"
    return "刚刚"


def post_to_dict(post: ForumPost, user: User | None = None) -> dict:
    is_hot = post.like_count >= 15 and post.comment_count >= 3
    if user is None:
        user_nick = post.author_nickname if hasattr(post, 'author_nickname') else "匿名"
        user_avatar = post.author_avatar if hasattr(post, 'author_avatar') else "匿"
    else:
        user_nick = user.nickname
        user_avatar = user.nickname[0] if user.nickname else "匿"
    return {
        "id": post.id,
        "category": post.category,
        "subject": post.subject,
        "knowledge_point": post.knowledge_point,
        "title": post.title,
        "content": post.content,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "is_top": post.is_top,
        "is_hot": is_hot,
        "author": user_nick,
        "avatar": user_avatar,
        "time": relative_time(post.create_time),
        "create_time": post.create_time.isoformat(),
    }


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.query(ForumCategory).order_by(ForumCategory.sort_order).all()
    return success({"items": [{"id": r.id, "name": r.name, "description": r.description} for r in rows]})


@router.get("/posts")
def posts(
    search: str = Query(default=""),
    category: str = Query(default=""),
    db: Session = Depends(get_db),
):
    query = (
        db.query(ForumPost, User)
        .join(User, ForumPost.user_id == User.id)
        .filter(ForumPost.status == "normal")
    )
    if search:
        like = f"%{search}%"
        query = query.filter(
            ForumPost.title.ilike(like) | ForumPost.content.ilike(like)
        )
    if category and category != "全部":
        query = query.filter(ForumPost.category == category)
    rows = query.order_by(ForumPost.create_time.desc()).all()
    items = []
    for post, user in rows:
        d = post_to_dict(post, user)
        items.append(d)
    return success({"items": items})


@router.post("/posts")
def create_post(
    payload: ForumPostRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    post = ForumPost(user_id=user.id, **payload.model_dump())
    db.add(post)
    db.commit()
    db.refresh(post)
    return success({"post": post_to_dict(post, user)})


@router.get("/posts/{post_id}")
def post_detail(post_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(ForumPost, User)
        .join(User, ForumPost.user_id == User.id)
        .filter(ForumPost.id == post_id)
        .first()
    )
    if not row:
        raise AppError("POST_NOT_FOUND", "帖子不存在", status_code=404)
    post, user = row
    return success({"post": post_to_dict(post, user)})


@router.put("/posts/{post_id}")
def update_post(
    post_id: int,
    payload: ForumPostRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(ForumPost)
        .filter(ForumPost.id == post_id, ForumPost.user_id == user.id)
        .first()
    )
    if not row:
        raise AppError("POST_NOT_FOUND", "帖子不存在或无权限", status_code=404)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return success({"post": post_to_dict(row, user)})


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(ForumPost)
        .filter(ForumPost.id == post_id, ForumPost.user_id == user.id)
        .first()
    )
    if not row:
        raise AppError("POST_NOT_FOUND", "帖子不存在或无权限", status_code=404)
    row.status = "deleted"
    db.commit()
    return success({"deleted": True})


@router.post("/posts/{post_id}/like")
def like(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not row:
        raise AppError("POST_NOT_FOUND", "帖子不存在", status_code=404)
    row.like_count += 1
    db.commit()
    return success({"like_count": row.like_count})


@router.post("/posts/{post_id}/unlike")
def unlike(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not row:
        raise AppError("POST_NOT_FOUND", "帖子不存在", status_code=404)
    row.like_count = max(0, row.like_count - 1)
    db.commit()
    return success({"like_count": row.like_count})


@router.get("/posts/{post_id}/comments")
def comments(post_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(ForumComment, User)
        .join(User, ForumComment.user_id == User.id)
        .filter(ForumComment.post_id == post_id)
        .order_by(ForumComment.create_time)
        .all()
    )
    return success({
        "items": [
            {
                "id": c.id,
                "content": c.content,
                "parent_id": c.parent_id,
                "author": u.nickname,
                "avatar": u.nickname[0] if u.nickname else "匿",
                "create_time": relative_time(c.create_time),
            }
            for c, u in rows
        ]
    })


@router.post("/posts/{post_id}/comments")
def add_comment(
    post_id: int,
    payload: ForumCommentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise AppError("POST_NOT_FOUND", "帖子不存在", status_code=404)
    comment = ForumComment(
        post_id=post_id,
        user_id=user.id,
        parent_id=payload.parent_id,
        content=payload.content,
    )
    post.comment_count += 1
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return success({
        "comment_id": comment.id,
        "comment_count": post.comment_count,
        "author": user.nickname,
        "avatar": user.nickname[0] if user.nickname else "匿",
        "content": comment.content,
        "create_time": "刚刚",
    })


@router.post("/comments/{comment_id}/reply")
def reply(
    comment_id: int,
    payload: ForumCommentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parent = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
    if not parent:
        raise AppError("COMMENT_NOT_FOUND", "评论不存在", status_code=404)
    comment = ForumComment(
        post_id=parent.post_id,
        user_id=user.id,
        parent_id=comment_id,
        content=payload.content,
    )
    db.add(comment)
    db.commit()
    return success({"comment_id": comment.id})


@router.post("/posts/{post_id}/ai-answer")
def ai_answer(post_id: int, db: Session = Depends(get_db)):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise AppError("POST_NOT_FOUND", "帖子不存在", status_code=404)
    return success(ai_answer_for_post(post.title, post.content, post.subject, post.knowledge_point))


@router.post("/posts/{post_id}/ai-followup")
def ai_followup(
    post_id: int,
    payload: ForumCommentRequest,
    db: Session = Depends(get_db),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise AppError("POST_NOT_FOUND", "帖子不存在", status_code=404)
    fallback = (
        f"<p>可以继续从定义、流程、边界条件三个角度拆解 <b>{post.title}</b>，"
        f"并用一道同类题验证。你提到「{payload.content}」，建议先定位题目中发生状态变化的时刻。</p>"
    )
    llm = chat_completion(
        [
            {
                "role": "system",
                "content": "你是考研 408 学习论坛 AI 小助手，回答要友好、具体、可执行，可使用简单 HTML。",
            },
            {
                "role": "user",
                "content": (
                    f"帖子标题：{post.title}\n帖子内容：{post.content}\n"
                    f"科目：{post.subject}\n知识点：{post.knowledge_point}\n"
                    f"用户追问：{payload.content}\n请给出进一步回答。"
                ),
            },
        ],
        fallback,
    )
    return success({
        "answer": llm.content.replace("\n", "<br>"),
        "llm_used": llm.used_llm,
        "llm_error": llm.error,
    })


@router.get("/hot")
def hot(db: Session = Depends(get_db)):
    rows = (
        db.query(ForumPost, User)
        .join(User, ForumPost.user_id == User.id)
        .filter(ForumPost.status == "normal")
        .order_by(
            (ForumPost.like_count * 2 + ForumPost.comment_count * 3).desc(),
            ForumPost.create_time.desc(),
        )
        .limit(5)
        .all()
    )
    items = []
    for post, user in rows:
        d = post_to_dict(post, user)
        d["heat_score"] = post.like_count * 2 + post.comment_count * 3
        items.append(d)
    return success({"items": items, "rule": "按 点赞数×2 + 评论数×3 降序排列，取前5"})


@router.get("/checkin/status")
def checkin_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    checked_today = (
        db.query(ForumCheckin)
        .filter(ForumCheckin.user_id == user.id, ForumCheckin.checkin_date == today)
        .first()
        is not None
    )
    week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    week_begin = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_count = (
        db.query(func.count(func.distinct(ForumCheckin.user_id)))
        .filter(ForumCheckin.create_time >= week_begin)
        .scalar()
        or 0
    )
    consecutive_days = 0
    for offset in range(365):
        d = (datetime.utcnow() - timedelta(days=offset)).strftime("%Y-%m-%d")
        exists = (
            db.query(ForumCheckin)
            .filter(ForumCheckin.user_id == user.id, ForumCheckin.checkin_date == d)
            .first()
        )
        if exists:
            consecutive_days += 1
        else:
            break
    return success({
        "checked_today": checked_today,
        "weekly_count": weekly_count,
        "consecutive_days": consecutive_days,
    })


@router.post("/checkin")
def checkin(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    existing = (
        db.query(ForumCheckin)
        .filter(ForumCheckin.user_id == user.id, ForumCheckin.checkin_date == today)
        .first()
    )
    week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    week_begin = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    if existing:
        weekly_count = (
            db.query(func.count(func.distinct(ForumCheckin.user_id)))
            .filter(ForumCheckin.create_time >= week_begin)
            .scalar()
            or 0
        )
        return success({
            "checked": True,
            "already_checked": True,
            "weekly_count": weekly_count,
            "message": "今天已打卡",
        })

    db.add(ForumCheckin(user_id=user.id, checkin_date=today))
    db.commit()
    weekly_count = (
        db.query(func.count(func.distinct(ForumCheckin.user_id)))
        .filter(ForumCheckin.create_time >= week_begin)
        .scalar()
        or 0
    )
    return success({
        "checked": True,
        "already_checked": False,
        "weekly_count": weekly_count,
        "message": "今日论坛学习打卡成功",
    })


@router.get("/my-posts")
def my_posts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(ForumPost)
        .filter(ForumPost.user_id == user.id, ForumPost.status == "normal")
        .all()
    )
    return success({"items": [post_to_dict(p, user) for p in rows]})



