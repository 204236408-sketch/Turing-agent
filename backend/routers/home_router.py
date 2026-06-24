"""
首页大盘接口（半成品需要深化）

功能：
- GET /api/home/overview — 获取首页大屏数据，包含：
  · today_plan：今日学习计划（优先攻克知识点）
  · countdown：考研倒计时
  · recommendations：智能推荐列表
  · stats：本周答题数、正确率、薄弱点统计
  · knowledge_graph：四科知识图谱（含掌握状态着色）
  · memories：长期记忆摘要
  · initial_state：新用户初始引导状态

状态：半成品需要深化。业务逻辑较完整，但存在大量硬编码回退值（操作系统/页面置换算法），
      乱码清理表不全面，知识点状态计算逻辑需要验证。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import AnswerRecord, KnowledgeMastery, KnowledgePoint, Mistake, User, UserMemory, UserProfile
from services.mastery_service import synchronize_user_mastery
from services.recommendation_service import build_smart_recommendations, choose_today_plan as choose_recommended_plan
from utils.response import success


router = APIRouter(prefix="/api/home", tags=["home"])


SUBJECTS = ["数据结构", "计算机组成原理", "操作系统", "计算机网络"]
DEFAULT_TARGET_DATE = "2026-12-19"
STATUS_ORDER = ["薄弱点", "不会", "不熟", "掌握", "未学"]
STATUS_STYLE = {
    "未学": {"color": "#9aa5b1", "class_name": "unlearned", "label": "未学"},
    "掌握": {"color": "#27a978", "class_name": "mastered", "label": "掌握"},
    "不熟": {"color": "#d9a441", "class_name": "unfamiliar", "label": "不熟"},
    "不会": {"color": "#e17843", "class_name": "unknown", "label": "不会"},
    "薄弱点": {"color": "#e95f52", "class_name": "weak", "label": "薄弱点"},
}

KNOWLEDGE_FALLBACK = {
    "数据结构": ["线性表", "栈和队列", "树与二叉树", "图", "查找与排序"],
    "计算机组成原理": ["数据表示与运算", "存储系统", "指令系统", "中央处理器", "总线与 I/O"],
    "操作系统": ["进程与线程", "同步与互斥", "死锁", "内存管理", "文件系统"],
    "计算机网络": ["体系结构", "数据链路层", "网络层", "传输层", "应用层"],
}
GRAPH_ALIASES = {
    ("数据结构", "查找与排序"): ["查找与排序", "查找", "排序"],
    ("操作系统", "内存管理"): ["内存管理", "页面置换算法", "分页管理", "虚拟内存"],
}
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

MOJIBAKE_MAP = {
    "���ݽṹ": "数据结构",
    "��������ԭ��": "计算机组成原理",
    "����ϵͳ": "操作系统",
    "���������": "计算机网络",
    "���Ա�": "线性表",
    "ջ�Ͷ���": "栈和队列",
    "���������": "树与二叉树",
    "ͼ": "图",
    "����": "查找",
    "���ݱ�ʾ������": "数据表示与运算",
    "�洢ϵͳ": "存储系统",
    "ҳ���û��㷨": "页面置换算法",
    "????": "操作系统",
    "??????": "页面置换算法",
    "δѧ": "未学",
    "����": "掌握",
    "���": "掌握",
    "������": "薄弱点",
    "钖勫急鐐?": "薄弱点",
    "涓嶇啛": "不熟",
    "涓嶄細": "不会",
    "鏈": "未学",
    "鎺屾彙": "掌握",
}


def clean_text(value: str | None, fallback: str = "") -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    if text in MOJIBAKE_MAP:
        return MOJIBAKE_MAP[text]
    if "?" in text or "�" in text:
        return fallback or "待识别知识点"
    return text


def normalize_status(value: str | None, row: KnowledgeMastery | None = None) -> str:
    raw = clean_text(value, "")
    if raw in STATUS_STYLE:
        return raw
    if row:
        total = row.total_answer_count or 0
        wrong = row.wrong_count or 0
        correct = row.correct_count or 0
        weak_score = row.weak_score or 0
        if total == 0 and weak_score <= 0:
            return "未学"
        if wrong >= 3 or weak_score >= 10:
            return "薄弱点"
        if row.unknown_count or (total >= 2 and correct == 0):
            return "不会"
        if row.unfamiliar_count or wrong in (1, 2):
            return "不熟"
        if total >= 3 and correct / max(total, 1) >= 0.8 and wrong <= 1 and weak_score <= 2:
            return "掌握"
        return "不熟"
    return "未学"


def target_datetime(profile: UserProfile | None) -> datetime:
    raw = (profile.target_date if profile else "") or DEFAULT_TARGET_DATE
    try:
        return datetime.combine(date.fromisoformat(raw[:10]), time.min, tzinfo=SHANGHAI_TZ)
    except ValueError:
        return datetime.combine(date.fromisoformat(DEFAULT_TARGET_DATE), time.min, tzinfo=SHANGHAI_TZ)


def countdown_payload(profile: UserProfile | None) -> dict:
    target = target_datetime(profile)
    now = datetime.now(SHANGHAI_TZ)
    diff = max(target - now, timedelta())
    days = diff.days
    seconds = diff.seconds
    return {
        "target_date": target.date().isoformat(),
        "target_label": f"{target.year} 年 {target.month} 月 {target.day} 日",
        "days": days,
        "hours": seconds // 3600,
        "minutes": (seconds % 3600) // 60,
        "seconds": seconds % 60,
        "expired": target <= now,
    }


def current_week_range() -> tuple[datetime, datetime]:
    today = datetime.now()
    start = datetime.combine((today - timedelta(days=today.weekday())).date(), time.min)
    return start, start + timedelta(days=7)


def mastery_map(rows: list[KnowledgeMastery]) -> dict[tuple[str, str], KnowledgeMastery]:
    result: dict[tuple[str, str], KnowledgeMastery] = {}
    for row in rows:
        key = (clean_text(row.subject), clean_text(row.knowledge_point))
        existing = result.get(key)
        if not existing:
            result[key] = row
            continue
        row_status = normalize_status(row.final_status, row)
        existing_status = normalize_status(existing.final_status, existing)
        row_rank = STATUS_ORDER.index(row_status)
        existing_rank = STATUS_ORDER.index(existing_status)
        if row_rank < existing_rank or (row_rank == existing_rank and (row.weak_score or 0) > (existing.weak_score or 0)):
            result[key] = row
    return result


def compute_point_status(subject: str, point: str, rows: dict[tuple[str, str], KnowledgeMastery]) -> tuple[str, KnowledgeMastery | None]:
    row = rows.get((subject, point))
    return normalize_status(row.final_status if row else None, row), row


def sorted_mastery_candidates(rows: list[KnowledgeMastery]) -> list[KnowledgeMastery]:
    return sorted(
        rows,
        key=lambda r: (
            STATUS_ORDER.index(normalize_status(r.final_status, r)) if normalize_status(r.final_status, r) in STATUS_ORDER else 99,
            -(r.weak_score or 0),
            -(r.wrong_count or 0),
            -((r.qa_count or 0) + (r.forum_count or 0)),
        ),
    )


def choose_today_plan(rows: list[KnowledgeMastery], mistakes: list[Mistake], points: list[KnowledgePoint]) -> dict:
    candidate = next((r for r in sorted_mastery_candidates(rows) if normalize_status(r.final_status, r) != "未学"), None)
    if not candidate and mistakes:
        latest = mistakes[0]
        subject = clean_text(latest.subject, "操作系统")
        point = clean_text(latest.knowledge_point, "页面置换算法")
        return {
            "subject": subject,
            "knowledge_point": point,
            "title": f"今天优先攻克\n{point}",
            "reason": f"最近错题集中在「{point}」，建议先用 3 道同类题把错误模式拆开。",
            "mode": "最近错题复练",
            "difficulty": "中等",
            "question_type": "选择题",
            "count": 3,
            "empty_state": False,
        }
    if candidate:
        subject = clean_text(candidate.subject, "操作系统")
        point = clean_text(candidate.knowledge_point, "页面置换算法")
        status = normalize_status(candidate.final_status, candidate)
        reason_bits = []
        if candidate.wrong_count:
            reason_bits.append(f"累计错 {candidate.wrong_count} 次")
        if candidate.unknown_count:
            reason_bits.append(f"标记不会 {candidate.unknown_count} 次")
        if candidate.unfamiliar_count:
            reason_bits.append(f"标记不熟 {candidate.unfamiliar_count} 次")
        if candidate.weak_score:
            reason_bits.append(f"薄弱权重 {candidate.weak_score:g}")
        reason = " · ".join(reason_bits) or f"当前状态为「{status}」，适合进行一次短训练校验。"
        return {
            "subject": subject,
            "knowledge_point": point,
            "title": f"今天优先攻克\n{point}",
            "reason": f"{reason}。Agent 将按 PDF 的薄弱点强化逻辑生成专项题。",
            "mode": "薄弱点强化" if status in {"薄弱点", "不会", "不熟"} else "已改善知识点复测",
            "difficulty": "中等" if status in {"薄弱点", "不会", "不熟"} else "较难",
            "question_type": "选择题",
            "count": 3,
            "empty_state": False,
        }
    first = next((p for p in points if p.is_high_frequency), None) or (points[0] if points else None)
    subject = clean_text(first.subject if first else "", "操作系统")
    point = clean_text(first.name if first else "", "页面置换算法")
    return {
        "subject": subject,
        "knowledge_point": point,
        "title": "先完成一次\n408 基线诊断",
        "reason": "你当前还没有稳定的错题和答题记录。系统会先从高频知识点生成诊断题，答题后再自动形成薄弱点和长期记忆。",
        "mode": "四科随机综合",
        "difficulty": "中等",
        "question_type": "选择题",
        "count": 3,
        "empty_state": True,
    }


def build_recommendations(rows: list[KnowledgeMastery], mistakes: list[Mistake], memories: list[UserMemory], points: list[KnowledgePoint]) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(mode: str, subject: str, point: str, reason: str, difficulty: str = "中等"):
        key = (mode, subject, point)
        if key in seen or len(items) >= 5:
            return
        seen.add(key)
        items.append(
            {
                "mode": mode,
                "subject": subject,
                "knowledge_point": point,
                "reason": reason,
                "difficulty": difficulty,
                "question_type": "选择题",
                "count": 3,
            }
        )

    for row in sorted_mastery_candidates(rows):
        status = normalize_status(row.final_status, row)
        if status in {"薄弱点", "不会", "不熟"}:
            add(
                "薄弱点强化",
                clean_text(row.subject, "操作系统"),
                clean_text(row.knowledge_point, "页面置换算法"),
                f"{status} · 错 {row.wrong_count} 次 · 薄弱权重 {row.weak_score:g}",
            )
    for mistake in mistakes[:3]:
        add(
            "最近错题复练",
            clean_text(mistake.subject, "操作系统"),
            clean_text(mistake.knowledge_point, "页面置换算法"),
            "来自最近错题记录，建议做同知识点变式题。",
        )
    for memory in memories[:3]:
        add(
            "长期记忆复习",
            clean_text(memory.subject, "操作系统"),
            clean_text(memory.knowledge_point, "页面置换算法"),
            "来自 active 长期记忆，适合转化为训练题。",
        )
    for point in points:
        if point.is_high_frequency:
            add("高频考点诊断", clean_text(point.subject, "操作系统"), clean_text(point.name, "页面置换算法"), "高频知识点，适合作为今日补齐训练。")
    if not items:
        add("新手基线诊断", "操作系统", "页面置换算法", "暂无学习行为，先用高频基础题建立初始画像。")
        add("新手基线诊断", "数据结构", "树与二叉树", "暂无错题记录，先覆盖 408 高频考点。")
        add("新手基线诊断", "计算机网络", "传输层", "暂无问答记录，先检查概念理解。")
    return items[:3]


def build_stats(rows: list[KnowledgeMastery], memories: list[UserMemory], all_answers: list[AnswerRecord], weekly_answers: list[AnswerRecord]) -> dict:
    total_answers = len(weekly_answers)
    weekly_correct = sum(1 for item in weekly_answers if item.is_correct)
    all_total = len(all_answers)
    all_correct = sum(1 for item in all_answers if item.is_correct)
    accuracy = round((all_correct / all_total) * 100) if all_total else 0
    unique_rows = list(mastery_map(rows).values())
    weak_count = sum(1 for r in unique_rows if normalize_status(r.final_status, r) in {"薄弱点", "不会", "不熟"})
    mastered_count = sum(1 for r in unique_rows if normalize_status(r.final_status, r) == "掌握")
    return {
        "weekly_answers": total_answers,
        "weekly_correct": weekly_correct,
        "accuracy": accuracy,
        "weak_points": weak_count,
        "mastered_points": mastered_count,
        "memory_entries": len(memories),
        "cards": [
            {"label": "本周答题", "value": total_answers, "delta": f"{weekly_correct} 道正确" if total_answers else "开始答题后自动统计"},
            {"label": "综合正确率", "value": f"{accuracy}%" if all_total else "待生成", "delta": f"累计 {all_total} 次答题" if all_total else "暂无答题记录"},
            {"label": "长期薄弱点", "value": weak_count, "delta": "按 weak_score 与错题同步"},
            {"label": "记忆条目", "value": len(memories), "delta": "问答、错题和反馈会写入这里"},
        ],
    }


def build_memory_list(memories: list[UserMemory], rows: list[KnowledgeMastery]) -> list[dict]:
    items = [
        {
            "title": clean_text(m.knowledge_point, "待复习知识点"),
            "content": clean_text(m.content, "系统已记录一个需要复习的长期记忆条目。"),
            "subject": clean_text(m.subject, "408"),
        }
        for m in memories[:4]
    ]
    if items:
        return items
    touched = [r for r in sorted_mastery_candidates(rows) if normalize_status(r.final_status, r) != "未学"]
    if touched:
        return [
            {
                "title": clean_text(row.knowledge_point, "已学习知识点"),
                "content": f"当前状态：{normalize_status(row.final_status, row)}；答题 {row.total_answer_count} 次，错 {row.wrong_count} 次。",
                "subject": clean_text(row.subject, "408"),
            }
            for row in touched[:3]
        ]
    return [
        {
            "title": "还没有长期学习记忆",
            "content": "完成一次出题训练、问答或错题确认后，系统会把薄弱点、错因和复习偏好写入这里。",
            "subject": "初始化",
        }
    ]


def build_graph(points: list[KnowledgePoint], rows: list[KnowledgeMastery]) -> dict:
    by_mastery = mastery_map(rows)
    grouped: dict[str, list[dict]] = {subject: [] for subject in SUBJECTS}
    for subject, fallback_points in KNOWLEDGE_FALLBACK.items():
        for idx, name in enumerate(fallback_points):
            aliases = GRAPH_ALIASES.get((subject, name), [name])
            alias_rows = [by_mastery[(subject, alias)] for alias in aliases if (subject, alias) in by_mastery]
            row = min(
                alias_rows,
                key=lambda item: STATUS_ORDER.index(normalize_status(item.final_status, item)),
                default=None,
            )
            status = normalize_status(row.final_status if row else None, row)
            grouped[subject].append(
                {
                    "id": f"{subject}-{idx}",
                    "subject": subject,
                    "name": name,
                    "parent_name": subject,
                    "level": 2,
                    "is_high_frequency": idx in {1, 2, 3},
                    "status": status,
                    "weak_score": row.weak_score if row else 0,
                    "total_answer_count": row.total_answer_count if row else 0,
                    "style": STATUS_STYLE[status],
                }
            )
    summary = {status: 0 for status in STATUS_STYLE}
    for items in grouped.values():
        for item in items:
            summary[item["status"]] += 1
    return {"subjects": grouped, "summary": summary, "status_style": STATUS_STYLE}


@router.get("/overview")
def home_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    points = db.query(KnowledgePoint).order_by(KnowledgePoint.subject, KnowledgePoint.id).all()
    synchronize_user_mastery(db, user.id, [(point.subject, point.name) for point in points])
    db.flush()
    mastery_rows = db.query(KnowledgeMastery).filter(KnowledgeMastery.user_id == user.id).all()
    memories = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user.id, UserMemory.status == "active")
        .order_by(desc(UserMemory.update_time))
        .all()
    )
    mistakes = (
        db.query(Mistake)
        .filter(Mistake.user_id == user.id, Mistake.status == "active")
        .order_by(desc(Mistake.create_time))
        .all()
    )
    week_start, week_end = current_week_range()
    weekly_answers = (
        db.query(AnswerRecord)
        .filter(AnswerRecord.user_id == user.id, AnswerRecord.create_time >= week_start, AnswerRecord.create_time < week_end)
        .all()
    )
    all_answers = db.query(AnswerRecord).filter(AnswerRecord.user_id == user.id).all()
    answer_count = len(all_answers)
    today_plan = choose_recommended_plan(db, user.id)
    raw_recommendations = build_smart_recommendations(db, user.id)
    recommendations = sorted(raw_recommendations, key=lambda item: (not item["available"], raw_recommendations.index(item)))
    stats = build_stats(mastery_rows, memories, all_answers, weekly_answers)
    graph = build_graph(points, mastery_rows)
    db.commit()
    return success(
        {
            "today_plan": today_plan,
            "countdown": countdown_payload(profile),
            "recommendations": recommendations,
            "stats": stats,
            "knowledge_graph": graph,
            "memories": build_memory_list(memories, mastery_rows),
            "initial_state": {
                "has_answers": answer_count > 0,
                "has_mistakes": bool(mistakes),
                "has_memories": bool(memories),
                "message": "当前还没有足够学习记录，先完成一次基线诊断，系统会自动建立你的 408 学习画像。",
            },
        }
    )
