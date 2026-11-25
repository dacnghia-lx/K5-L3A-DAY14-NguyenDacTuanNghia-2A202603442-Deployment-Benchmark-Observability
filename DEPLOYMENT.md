# Deployment — Day 14 Lab

## Nền tảng: Railway

**URL public:** `https://k5-l3a-day14-nguyendactuannghia-2a202603442-productio-f58e5fca.up.railway.app`

---

## 4 lệnh kiểm thử (CP6) và kết quả thực tế

```bash
# 1. Health check → 200 OK
curl -s https://k5-l3a-day14-nguyendactuannghia-2a202603442-productio-f58e5fca.up.railway.app/health
# {"status":"ok","environment":"production"}

# 2. Readiness → 200 OK (khi Redis kết nối thành công)
curl -s https://k5-l3a-day14-nguyendactuannghia-2a202603442-productio-f58e5fca.up.railway.app/ready
# {"ready":true}

# 3. Không có API key → 401
curl -s -X POST https://k5-l3a-day14-nguyendactuannghia-2a202603442-productio-f58e5fca.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "hello"}'
# {"detail":"Missing or invalid API key"}

# 4. Có API key đúng → 200
curl -s -X POST https://k5-l3a-day14-nguyendactuannghia-2a202603442-productio-f58e5fca.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: day14-lab-key" \
  -d '{"question": "What is an AI agent?"}'
# {"question":"What is an AI agent?","answer":"Agent đang hoạt động tốt! (mock response)...","cost_usd":1.71e-05}
```

---

## Biến môi trường đặt trên Railway

| Biến | Giá trị | Ghi chú |
|---|---|---|
| `AGENT_API_KEY` | `day14-lab-key` | Đặt trên Railway Dashboard (không ghi trong code) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Railway reference variable — tự inject từ Redis service |
| `ENVIRONMENT` | `production` | |
| `AGENT_VERSION` | `v2` | |
| `LLM_MODEL` | `mock-llm-small` | |

> ⚠️ Không có giá trị secret nào được ghi trong repo hay lịch sử commit.

---

## Cấu hình deploy

- **Platform:** Railway
- **Root Directory:** `06-lab-complete`
- **Builder:** Dockerfile (`06-lab-complete/Dockerfile`, multi-stage, non-root, HEALTHCHECK)
- **Platform config:** `06-lab-complete/railway.toml` (healthcheckPath: /health)
- **Redis:** Railway Redis add-on trong cùng project (inject `REDIS_URL` tự động)

---

## Screenshots

- `screenshots/dashboard.png` — Railway dashboard hiển thị 2 services (agent + redis) Active
- `screenshots/running.png` — Deployment logs (startup + request logs)
- `screenshots/test.png` — Output 4 lệnh curl kiểm thử ở trên
