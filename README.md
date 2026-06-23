# 重生之我是图灵（Turing 408 Agent）

面向计算机考研 408 的 AI 学习系统。项目依据现有前端 Demo 开发，包含知识问答、智能出题、错题本、PaddleOCR、知识图谱、学习报告、长期记忆和学习论坛。

## 仓库结构

```text
apps/
  web/                 Vue 3 前端（第 5 人）
  api/                 FastAPI 接口与 JWT（第 1 人）
services/
  ai/                  大模型、ChromaDB、OCR（第 3 人）
  agent/               Prompt 与 Agent 流程（第 4 人）
database/
  migrations/          MySQL/Alembic 迁移（第 2 人）
  seeds/               初始化数据（第 2 人）
  schemas/             ER 图和字段字典（第 2 人）
docs/                  接口、分工和协作文档
prototype/             最终前端 Demo，仅作为设计基准
tests/                 集成与端到端测试
```

## 五人模块

| 人员 | 主责目录 | 工作内容 |
|---|---|---|
| 第 1 人 | `apps/api/` | FastAPI、JWT、登录注册、业务 API |
| 第 2 人 | `database/` | MySQL、ORM 协作、迁移、索引、Seed |
| 第 3 人 | `services/ai/` | 大模型 API、ChromaDB、PaddleOCR |
| 第 4 人 | `services/agent/` | 问答、出题、批改、记忆 Prompt/Agent |
| 第 5 人 | `apps/web/` | Vue3、登录注册及全部业务页面 |

## 开发分支

- `develop`
- `feature/backend-api`
- `feature/database`
- `feature/llm-rag-ocr`
- `feature/agent-prompts`
- `feature/vue-frontend`

详细任务见 [团队分工](docs/team-division.md)。

## 当前状态

- [x] 建立五人协作仓库
- [x] 导入最终前端原型
- [ ] 初始化 Vue3 项目
- [ ] 初始化 FastAPI 项目
- [ ] 建立 MySQL 迁移
- [ ] 接入模型、ChromaDB 与 PaddleOCR
- [ ] 完成 Agent 工作流

