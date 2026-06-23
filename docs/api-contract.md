# API 契约清单

第一阶段优先冻结：

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/users/me`
- `GET /api/home/overview`
- `GET /api/knowledge/graph`
- `POST /api/qa/chat`
- `POST /api/questions/generate`
- `POST /api/answers/check`
- `POST /api/mistakes/cause-confirm`
- `GET /api/mistakes`
- `POST /api/ocr/upload`
- `POST /api/ocr/confirm`
- `POST /api/mistakes/analyze`
- `GET /api/reports/overview`
- `GET /api/forum/posts`
- `POST /api/forum/posts`
- `POST /api/forum/posts/{id}/comments`
- `POST /api/forum/posts/{id}/ai-answer`

统一响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

