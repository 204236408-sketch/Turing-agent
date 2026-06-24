"""
OCR 识别接口（Mock/占位接口）

功能：
- POST /api/ocr/upload   — 上传图片进行 OCR 识别（委托 ocr_service）
- POST /api/ocr/analyze  — 分析 OCR 识别文本（调用 mistake_agent 做错题分析）

状态：Mock/占位接口。upload 依赖外部 OCR 服务（save_and_recognize_upload 需第三方 API），
      analyze 复用 mistake_agent 逻辑。本地开发环境需要至少一个可用 OCR API 才能正常工作。
"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session
from agents.mistake_agent import analyze_ocr_text
from database import get_db
from dependencies import get_current_user
from schemas import OcrAnalyzeRequest
from services.ocr_service import save_and_recognize_upload
from models import User
from utils.response import success


router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    return success(await save_and_recognize_upload(file))


@router.post("/analyze")
def analyze(payload: OcrAnalyzeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = analyze_ocr_text(
        db,
        user.id,
        payload.text,
        payload.subject,
        payload.knowledge_point,
        payload.user_answer,
    )
    db.commit()
    return success(data)
