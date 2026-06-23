# 五人协作分工

## 第 1 人：后端

- 搭建 FastAPI、JWT、注册、登录和 Token 刷新。
- 汇总数据库、AI、Agent 能力并输出 REST API。
- 维护 Swagger、错误码、权限、日志和接口测试。

## 第 2 人：数据库

- 设计 MySQL 表、索引、外键和 Alembic 迁移。
- 重点完成 `conversation`、`conversation_message`、`user_memory`。
- 补充用户、知识点、题目、答题、错题、OCR、报告和论坛表。

## 第 3 人：模型与检索

- 封装外部大模型和 Embedding API。
- 建立 `knowledge_chunks`、`conversation_summaries`、`user_memories`、`mistake_summaries` Collection。
- 接入 PaddleOCR，输出文字、坐标和置信度。

## 第 4 人：Prompt 与 Agent

- 设计问答、出题、批改、错题分析、记忆更新 Prompt。
- 增加学习报告与论坛 AI 助手 Agent。
- 输出稳定 JSON Schema，并建立测试样例和版本记录。

## 第 5 人：前端

- 将 `prototype/` 重构为 Vue3 + Vite。
- 完成登录注册、首页、知识图谱、问答、出题、错题/OCR、报告、论坛和账号页面。
- 统一加载、失败、空数据、Token 失效和流式生成状态。

完整细则参见项目外部已形成的《重生之我是图灵-五人开发详细分工方案》。

