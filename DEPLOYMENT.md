# Deployment — Day 14 Lab

## Nền tảng: Railway

**URL public:** *(điền URL sau khi deploy, ví dụ: https://your-app-name.up.railway.app)*

---

## 4 lệnh kiểm thử (CP6)

```bash
# 1. Health check — phải trả 200
curl -s https://<YOUR_URL>/health

# 2. Readiness — phải trả 200
curl -s https://<YOUR_URL>/ready

# 3. Không có API key — phải trả 401
curl -s -X POST https://<YOUR_URL>/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "hello"}'

# 4. Có API key đúng — phải trả 200
curl -s -X POST https://<YOUR_URL>/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -d '{"question": "What is an AI agent?"}'
```

---

## Biến môi trường đặt trên Railway

| Biến | Giá trị | Ghi chú |
|---|---|---|
| `AGENT_API_KEY` | *(secret, đặt trên platform)* | Dùng để xác thực request |
| `REDIS_URL` | `redis://default:<password>@<host>:<port>` | Redis add-on của Railway |
| `ENVIRONMENT` | `production` | |
| `AGENT_VERSION` | `v2` | |
| `LLM_MODEL` | `mock-llm-small` | |

> ⚠️ Không có giá trị secret nào được ghi trong repo hay lịch sử commit.

---

## Cấu hình deploy

- **Platform config:** `06-lab-complete/railway.toml` (builder: DOCKERFILE, healthcheckPath: /health)
- **Dockerfile:** `06-lab-complete/Dockerfile` (multi-stage, non-root, HEALTHCHECK)
- **Redis:** Railway Redis add-on (inject `REDIS_URL` tự động)

---

## Screenshots

- `screenshots/dashboard.png` — Railway dashboard hiển thị service Running
- `screenshots/running.png` — Logs service (startup + request logs)
- `screenshots/test.png` — Output 4 lệnh curl kiểm thử ở trên
