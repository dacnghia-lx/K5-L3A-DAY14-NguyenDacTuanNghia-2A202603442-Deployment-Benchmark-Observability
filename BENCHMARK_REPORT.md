# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file report JSON trong `reports/` do `load_test.py` và `eval/run_eval.py` tạo ra.

**Họ tên:** Nguyễn Đắc Tuấn Nghĩa (MSSV: 2A202603442)
**Ngày chạy:** 2026-11-25
**Môi trường:** Linux, Python 3.12.16 (`.venv`), Docker 29.10.0

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Đảm bảo 95% người dùng nhận phản hồi dưới 0.5s, giữ trải nghiệm hội thoại mượt mà |
| Error rate `/ask` | ≤ 2.0 % | Chấp nhận một tỉ lệ nhỏ lỗi upstream (mock error rate 1%) nhưng vẫn giữ độ tin cậy 98% |
| Accuracy trên golden dataset | ≥ 80 % (mục tiêu 100% không regression) | Đảm bảo chất lượng trả lời trước khi merge/deploy |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.31 | 193.5 | 224.4 | 1697.1 | 0.33% | ✅ PASS |
| 10 | 36.43 | 191.0 | 223.8 | 1691.8 | 0.67% | ✅ PASS |
| 50 | 108.01 | 198.4 | 261.6 | 1702.3 | 1.00% | ✅ PASS |
| 100 | 68.37 | 314.5 | 2530.4 | 2773.6 | 0.67% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:** RPS không tăng tuyến tính theo concurrency. Từ concurrency 1 → 10 → 50, RPS tăng từ 4.31 lên 36.43 rồi 108.01 req/s vì I/O async xử lý song song tốt. Nhưng ở concurrency 100, event loop / 1 worker uvicorn bị bão hòa, RPS tụt xuống 68.37 req/s và p95 tăng vọt lên 2530.4 ms (vượt SLO 500 ms).

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 192.9 | 220.7 | 238.6 |
| 0.03 (mặc định) | 244.1 | 231.1 | 1709.5 |
| 0.1 | 295.8 | 1674.8 | 1704.6 |

**Nhận xét:** `p99` (và `p95` khi slow rate ≥ 5–10%) nhạy nhất với request chậm: khi `MOCK_SLOW_RATE=0.03`, `avg` chỉ tăng nhẹ từ 192.9 ms lên 244.1 ms và `p95` là 231.1 ms, nhưng `p99` nhảy vọt từ 238.6 ms lên **1709.5 ms** (gấp >7 lần). Nếu đặt SLO theo average thì sẽ che giấu hoàn toàn trải nghiệm tệ của nhóm người dùng ở đuôi phân phối (tail latency).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.2 | 108.8 | 113.1 |
| Tổng cost (USD) | $0.000405 | $0.000758 | $0.000786 |
| Cost / câu đúng (USD) | $0.00040515 | $0.00003607 | $0.00003417 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS (min-accuracy 1.0) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "api key"], ...)` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["kubernetes", "hpa"], ...)` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 tốn gần gấp đôi số token/câu (108.8–113.1 so với 57.2) và thêm ~20 ms retrieval nên tổng cost tăng gần gấp đôi ($0.000786 so với $0.000405).
- Tuy nhiên, accuracy tăng từ 4.3% lên 100%, giúp **cost / câu đúng** giảm hơn **11 lần** (từ $0.00040515 xuống $0.00003417).
- **CI Quality Gate:** Khi chạy `python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json`, lệnh trả về **exit code 1**. Có thể dùng bước này trong GitHub Actions (chạy `run_eval.py --min-accuracy 0.8 --baseline reports/eval_v2.json`) để tự động fail CI job và chặn merge PR nếu có regression.

---

## 4. Observability stack (production)

> Stack: `docker compose -p k5-day14-observability up -d --build` trong `06-lab-complete/benchmark-observability/production/`. Load test: Locust 30 users, ramp 5, host `http://nginx`.

### 4.1 Screenshot
- [x] `screenshots/grafana-dashboard.png` — Dashboard "Day 14 — AI Agent Overview" khi đang chạy 30 users (Locust RUNNING, RPS ~19, p95 ~230ms, Failure 2%)
- [x] `screenshots/jaeger-slow-trace.png` — Trace chậm nhất (~1.7 s) trong Jaeger: service `observable-agent`, sort Duration giảm dần
- [x] `screenshots/jaeger-error-trace.png` — Trace lỗi trong Jaeger: filter `error=true`, tag `http.status_code=500`
- [x] `screenshots/prometheus-alert-firing.png` — Trang `localhost:9090/alerts` hiển thị ≥ 2 alert FIRING đồng thời (AgentHighErrorRate + AgentHighLatencyP95)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (critical) | ~90 giây (rule: `for: 1m`, thêm ~30s scrape + eval) | **Error rate** (Golden Signals) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (warning) | ~150 giây (rule: `for: 2m`, thêm ~30s scrape + eval) | **Latency p95** và **Latency /ask — p50 / p95 / p99** |
| C | `LLM_MODEL=mock-llm-large` | Không có (latency tăng nhẹ nhưng không vượt ngưỡng 1s) | N/A | **LLM latency p95 theo model** (thấy model name thay đổi) |
| D | `docker pause` 1 instance | `AgentInstanceDown` (critical) | ~40 giây (rule: `for: 30s`) | **Instances up** (giảm từ 2 → 1) |
| E | `AGENT_VERSION=v1` | Không có | N/A | N/A |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
Chạy eval tự động trên golden dataset (quality gate trong CI/CD trước khi deploy) kết hợp theo dõi feedback người dùng / online LLM-as-a-judge sampling trên production traffic. Thêm metric `agent_accuracy_gauge` được cập nhật định kỳ từ shadow eval job → đặt alert nếu accuracy < 80%.

### 4.3 Debug bằng trace

Từ Jaeger UI (`http://localhost:16686`), lấy trace chậm nhất (Duration ~1700 ms), service `observable-agent`:

| Trường | Giá trị |
|---|---|
| `trace_id` | *(đọc từ header `X-Trace-ID` trong response hoặc URL Jaeger: đoạn hex 32 ký tự sau `/trace/`)* |
| Tổng thời gian | ~1700 ms |
| Số span | 4 |
| Span chậm nhất | `chat mock-llm-small` (~1500 ms — đây là span gọi mock LLM với `MOCK_SLOW_RATE=0.03` kích hoạt sleep 1500ms) |

**Cây span của 1 request `/ask` chậm (tổng ~1700 ms):**
```
POST /ask  [HTTP middleware]                ~1710 ms
└── agent.run                               ~1700 ms
    ├── agent.retrieve_context              ~1–3 ms   (tìm context từ KNOWLEDGE_BASE)
    └── chat mock-llm-small                ~1500 ms  ← SLOWEST SPAN (slow path triggered)
```

**Log line tương ứng (JSON, grep theo trace_id):**
```json
{"ts":"2026-11-25T...","level":"INFO","service":"observable-agent","instance":"agent-1","event":"http_request","trace_id":"<trace_id>","span_id":"<span_id>","method":"POST","route":"/ask","status":200,"ms":1710.3}
```

**Nhận xét:** Span `chat mock-llm-small` chiếm ~88% tổng thời gian request. Trong production thực tế, đây sẽ là span gọi LLM API (OpenAI/Gemini) — cần theo dõi timeout và retry strategy để tránh tail latency lan rộng.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.78 | 190 | 230 | 1700 | 99 / 7842 (1.26%) |
| 3 | 63.78 | 190 | 230 | 1700 | 36 / 3768 (0.96%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance không làm giảm p95 (cả hai đều 230 ms) hay tăng RPS nhiều, vì nút thắt nằm ở **độ trễ I/O của từng lần gọi mock LLM** (async sleep ~120–180 ms + 3% tail latency +1500 ms) chứ không phải CPU của 1 container `agent` (1 worker async uvicorn đã chịu được ~65 RPS với 100 user có `wait_time = between(0.5, 2)`). Scale nhiều instance giúp tăng khả năng chịu tải khi lưu lượng vượt ngưỡng 1 instance và đảm bảo high availability khi 1 instance gặp sự cố.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. Latency trung bình che giấu tail latency; cần đặt SLO theo p95/p99.
  2. Eval trên golden dataset kết hợp baseline giúp phát hiện regression chất lượng (như đổi nhầm `AGENT_VERSION=v1`) mà metrics hạ tầng không bắt được.
  3. Metrics (Prometheus/Grafana), Traces (OpenTelemetry/Jaeger) và JSON Logs có `trace_id` bổ trợ lẫn nhau để khoanh vùng nguyên nhân gốc.
- Nếu đưa agent lên production thật, nên thêm alert cho: tỉ lệ 429 (rate limit), tỉ lệ 402 (hết budget), và token usage bất thường theo từng tenant.
