"""
视频资源接口（Mock/占位接口）

功能：
- GET  /api/videos/recommend  — 推荐视频列表（等同于 /list）
- GET  /api/videos/list       — 视频列表（支持按科目、知识点筛选）
- POST /api/videos/crawl      — 爬取视频资源（显式 mock，仅返回开发提示）

状态：Mock/占位接口。视频列表读取本地数据库，爬虫接口显式声明为 mock；
      缺少视频上传、播放进度追踪等真正功能。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import VideoResource
from utils.response import success


router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("/recommend")
@router.get("/list")
def list_videos(subject: str = "", knowledge_point: str = "", db: Session = Depends(get_db)):
    query = db.query(VideoResource)
    if subject:
        query = query.filter(VideoResource.subject == subject)
    if knowledge_point:
        query = query.filter(VideoResource.knowledge_point == knowledge_point)
    rows = query.limit(20).all()
    return success({"items": [{"id": r.id, "title": r.title, "platform": r.platform, "url": r.url, "reason": r.reason} for r in rows]})


@router.post("/crawl")
def crawl():
    return success({"message": "开发版不爬取外站，已返回本地视频元数据。"})


