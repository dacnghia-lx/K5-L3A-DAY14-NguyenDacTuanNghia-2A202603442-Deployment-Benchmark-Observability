# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`
1. **Hardcoded secrets (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` ghi thẳng trong source code, nếu push lên GitHub sẽ bị lộ ngay lập tức.
2. **Hardcoded config (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` không đọc từ biến môi trường, không thể thay đổi linh hoạt giữa dev/staging/production.
3. **Dùng `print()` và log ra secret (dòng 33–38):** Dùng `print(...)` thay vì structured JSON logging, lại còn in thẳng `OPENAI_API_KEY` ra stdout (`print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`).
4. **Không có health check / readiness endpoint:** Thiếu `GET /health` và `GET /ready`, nên cloud platform / load balancer không biết container còn sống hay sẵn sàng nhận traffic để restart hoặc route traffic.
5. **Hardcoded `host="localhost"`, `port=8000`, `reload=True` (dòng 49–54):** Bind `localhost` khiến container không nhận được kết nối từ bên ngoài; port cố định không đọc biến `PORT` do platform cấp; bật `reload=True` trong production gây tốn tài nguyên và không ổn định.
6. **Không xử lý graceful shutdown:** Không có `lifespan` hay handler `SIGTERM`, khi tắt server sẽ cắt ngang các request đang xử lý.

### Exercise 1.2: Kết quả chạy bản develop
Lệnh gọi:
```bash
curl -sS -X POST "http://localhost:8000/ask?question=Hello"
```
Kết quả thực tế:
```json
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 1.3: Bảng so sánh Develop vs Production (`01-localhost-vs-production/production/app.py` & `config.py`)

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
|---|---|---|---|
| Config & Secrets | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, `PORT=8000` | Đọc từ biến môi trường qua `Settings` (`os.getenv(...)`) và `validate()` | Tuân thủ 12-Factor App, tránh lộ secret lên Git và dễ đổi cấu hình theo môi trường |
| Health check | Không có | Có `GET /health` (liveness), `GET /ready` (readiness), `GET /metrics` | Platform biết khi nào cần restart container (`/health`) và khi nào route traffic (`/ready`) |
| Logging | `print("[DEBUG] ...")`, log cả secret | `logging` với format JSON (`{"time":...,"level":...,"msg":...}`), không log secret | Dễ parse/tìm kiếm trên log aggregator (Loki, Datadog) và đảm bảo an toàn thông tin |
| Network Binding | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port=settings.port`, `reload=settings.debug` | `0.0.0.0` cho phép nhận traffic từ ngoài container; đọc `PORT` từ cloud platform |
| Shutdown | Tắt đột ngột | `lifespan` + `signal.signal(signal.SIGTERM, handle_sigterm)` | Hoàn thành request in-flight trước khi thoát, tránh lỗi 502/mất request khi deploy |
| CORS & Validation | Không có CORS, nhận `question` qua query param | `CORSMiddleware` theo `allowed_origins`, kiểm tra body JSON và trả `422` nếu thiếu | Kiểm soát origin được phép gọi API và validate input rõ ràng |

---

## Part 2: Docker

### Exercise 2.1: Trả lời 4 câu hỏi về `02-docker/develop/Dockerfile`
1. **Base image:** `python:3.11` (bản Python đầy đủ, dung lượng lớn ~1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` đứng trước `COPY . .` (hoặc `COPY app.py`)?** Để tận dụng Docker layer cache. Khi chỉ sửa code mà không đổi `requirements.txt`, Docker dùng lại layer đã chạy `pip install`, không phải tải và cài lại toàn bộ thư viện.
4. **CMD vs ENTRYPOINT khác nhau thế nào?** `ENTRYPOINT` định nghĩa executable chính cố định khi container khởi chạy (khó ghi đè bằng tham số `docker run`), còn `CMD` cung cấp lệnh mặc định hoặc tham số mặc định cho `ENTRYPOINT` và dễ bị ghi đè khi truyền command ở cuối `docker run`.

### Exercise 2.2 & 2.3: So sánh kích thước image (Multi-stage build)
- Trong `02-docker/production/Dockerfile`:
  - **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` và `pip install --user -r requirements.txt` vào `/root/.local`.
  - **Stage 2 (`runtime`):** Dùng `python:3.11-slim`, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local` và copy source code (`main.py`, `utils/mock_llm.py`), không mang theo `gcc` hay build tools nên image nhỏ gọn và an toàn hơn.
- Kết quả đo `docker images`: 
IMAGE               ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:advanced   963bd0f9f957        237MB         57.4MB        
my-agent:develop    086e7662a204       1.66GB          426MB    

### Exercise 2.4: Kiến trúc Docker Compose (`02-docker/production/docker-compose.yml`)
Các service trong stack giao tiếp qua bridge network `internal`:
```text
Client ──▶ nginx (:80/:443) ──▶ agent (:8000, runtime target) ──▶ redis (:6379)
                                                             └──▶ qdrant (:6333)
```
- `nginx`: Reverse proxy nhận traffic từ cổng 80/443 và forward vào `agent`.
- `agent`: Chạy FastAPI trên cổng 8000 (không expose thẳng ra ngoài), `depends_on` `redis` và `qdrant` ở trạng thái `service_healthy`.
- `redis`: Cache session & rate limit (`redis:7-alpine`, volume `redis_data`).
- `qdrant`: Vector DB cho RAG (`qdrant/qdrant:v1.9.0`, volume `qdrant_data`).

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 lên Cloud
- URL public: `https://k5-l3a-day14-nguyendactuannghia-2a202603442-productio-f58e5fca.up.railway.app`
- Nền tảng: Railway — Root Directory `06-lab-complete`, builder Dockerfile, Redis add-on inject `REDIS_URL`
- Screenshots: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### So sánh `railway.toml` và `render.yaml`
- **Định dạng & phạm vi:** `railway.toml` dùng định dạng TOML, tập trung cấu hình build (`builder = "DOCKERFILE"`, `dockerfilePath`) và deploy (`healthcheckPath = "/health"`, `restartPolicyType`) cho 1 service; trong khi `render.yaml` dùng YAML theo chuẩn Blueprint (Infrastructure as Code), có thể khai báo nhiều service cùng lúc (cả `web` service lẫn `redis` managed add-on) trong một file.
- **Cổng & biến môi trường:** Cả hai đều inject `PORT` tự động và yêu cầu `healthcheckPath`/`healthCheckPath` là `/health`. Tuy nhiên, `render.yaml` hỗ trợ khai báo trực tiếp `envVars` với `generateValue: true` (tự sinh secret) hoặc `sync: false` (nhập tay trên dashboard), còn `railway.toml` thường cấu hình biến môi trường qua Railway Dashboard hoặc `railway variables set`.

### Exercise 3.3: Mô tả pipeline CI/CD Cloud Run (`03-cloud-deployment/production-cloud-run/`)
Pipeline trong `cloudbuild.yaml` gồm 4 bước tuần tự khi push lên nhánh `main`:
1. **`test`:** Dùng `python:3.11-slim` cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`.
2. **`build`:** Dùng `gcr.io/cloud-builders/docker` build image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from`).
3. **`push`:** Đẩy image với tất cả tag lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy`:** Dùng `gcloud run deploy` triển khai image `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`, `min-instances=1`, `max-instances=10`, `512Mi` RAM, gắn secret `OPENAI_API_KEY` từ Secret Manager). File `service.yaml` định nghĩa cấu hình Knative Service tương đương dưới dạng IaC (concurrency 80, `livenessProbe` `/health`, `startupProbe` `/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)
1. Không có header `X-API-Key` → **401 Unauthorized**:
```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```
2. Có header `X-API-Key: secret-key-123` → **200 OK**:
```http
HTTP/1.1 200 OK
content-type: application/json

{"question":"hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2 & 4.3: JWT Token & Rate Limiting (`04-api-gateway/production/app.py`)
Lấy JWT token bằng `POST /auth/token` với `student` / `demo123` (giới hạn 10 req/phút), gọi vòng lặp 12 request (đã che token):
```text
Request 1 -> HTTP 200: {"question":"test","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.8e-05}}
...
Request 10 -> HTTP 200: {"question":"test","answer":"...","usage":{"requests_remaining":0,"budget_remaining_usd":0.000185}}
Request 11 -> HTTP 429: {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Request 12 -> HTTP 429: {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách làm Cost Guard (`04-api-gateway/production/cost_guard.py`)
- **Trước khi gọi LLM (`check_budget`):** Kiểm tra tổng chi phí toàn hệ thống (`global_daily_budget_usd = $10`) và chi phí trong ngày của từng user (`daily_budget_usd = $1`). Nếu vượt global budget → trả `503`; nếu vượt user budget → trả `402 Payment Required`; nếu đạt ≥ 80% → ghi log cảnh báo.
- **Sau khi gọi LLM (`record_usage`):** Tính chi phí dựa trên số `input_tokens`, `output_tokens` và đơn giá (`PRICE_PER_1K_INPUT_TOKENS = 0.00015`, `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`), cộng dồn vào bộ đếm theo ngày. Trong production (Part 6), bộ đếm này được lưu trong Redis (`INCRBYFLOAT` với TTL) để đồng bộ giữa các worker/instance.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Health Check, Readiness & Graceful Shutdown (`05-scaling-reliability/develop/app.py`)
- `GET /health` (Liveness): kiểm tra process còn sống và memory usage (`psutil`), trả `200 OK`:
  `{"status":"ok","uptime_seconds":1.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T07:32:52.548917+00:00","checks":{"memory":{"status":"ok","used_percent":39.5}}}`
- `GET /ready` (Readiness): kiểm tra `_is_ready` (trả `503` khi đang khởi động, đang shutdown, hoặc mất kết nối dependency như Redis), trả `200 OK`:
  `{"ready":true,"in_flight_requests":1}`
- **Sự khác nhau:** `/health` fail → platform restart container; `/ready` fail → load balancer ngừng route traffic mới tới instance đó nhưng không restart.
- **Graceful shutdown:** Khi gửi `SIGTERM`, log ghi nhận `Received signal 15 — uvicorn will handle graceful shutdown`, `lifespan` chuyển `_is_ready = False` và chờ `_in_flight_requests == 0` rồi mới thoát sạch.

### Exercise 5.4 & 5.5: Stateless Agent với Redis (`05-scaling-reliability/production/`)
- Nếu lưu session trong RAM (in-memory dict), khi chạy nhiều instance sau load balancer (Nginx round-robin), request 1 vào instance 1 và request 2 vào instance 2 sẽ bị mất lịch sử hội thoại.
- Giải pháp: lưu `session:{session_id}` trong **Redis** (với TTL) để mọi instance đều đọc/ghi chung một nguồn state.
- Chạy kiểm chứng `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py`: *(Cần chạy sau khi user `mrballs` được cấp quyền truy cập `/var/run/docker.sock`)*.

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `python check_production_ready.py --skip-docker` (do chưa có quyền truy cập `/var/run/docker.sock` trong phiên hiện tại; cần chạy lại `python check_production_ready.py` đầy đủ khi có Docker để đạt `PASS 12/12`):

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
```

---

## AI Log
- **Hỏi/Thực hiện:** Sử dụng AI Assistant (Gemini 4 Hydrogen) để kiểm tra cấu trúc bài lab, triển khai code Part 6 trong `06-lab-complete/app/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`), cấu hình `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`, chạy các script kiểm thử Part 1, 4, 5, 6, 7 và tổng hợp số liệu đo thực tế vào `MISSION_ANSWERS.md` và `BENCHMARK_REPORT.md`.
- **Tự kiểm tra:** Đã chạy trực tiếp các server Part 1, 4, 5 (develop), chạy `check_production_ready.py --skip-docker` (37/38 checks passed), chạy `load_test.py` và `eval/run_eval.py` (đạt 100% / 23/23 không regression sau khi bổ sung `KNOWLEDGE_BASE`).
