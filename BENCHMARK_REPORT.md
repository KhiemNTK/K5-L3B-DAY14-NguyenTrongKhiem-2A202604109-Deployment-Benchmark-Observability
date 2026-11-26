# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyễn Trọng Khiêm  
**MSSV:** 2A202604109  
**Ngày chạy:** 26/11/2026  
**Môi trường thực nghiệm:** Windows 11 Pro 64-bit / WSL2 Ubuntu 22.04 LTS, Docker Desktop (4 vCPU, 8GB RAM), Python 3.11.9, Redis 7.2-alpine, Prometheus v3.16.0, Jaeger 1.50, Grafana 10.2.0, Nginx 1.25-alpine.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo trải nghiệm tương tác thời gian thực cho người dùng cuối trên chat UI. 95% request phải được phản hồi dưới 500ms để người dùng không cảm giác đơ/lag giao diện. Ngưỡng này bao gồm cả thời gian xử lý của LLM (~120–180ms) và overhead mạng/framework. |
| Error rate `/ask` | < 1.0 % | Tiêu chuẩn độ tin cậy dịch vụ (99% success rate) cho API nghiệp vụ. Tỷ lệ lỗi dưới 1% tránh kích hoạt retry storm từ client và giữ độ sẵn sàng cao cho hệ thống production. |
| Accuracy trên golden dataset | ≥ 95.0 % | Đảm bảo chất lượng kiến thức của agent, không bị ảo giác (hallucination) hoặc bỏ sót các từ khóa cốt lõi về deployment, docker, security, scaling, observability. (Thực tế sau khi fix Knowledge Base, agent đạt 100.0%). |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

*Dữ liệu lấy từ `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json` (mỗi mức chạy 300 requests, `MOCK_SLOW_RATE=0.03`):*

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO (p95 < 500ms, Error < 1%) |
|---|---|---|---|---|---|---|
| 1 | 5.8 | 142.1 | 210.4 | 1682.0 | 0.0% | ĐẠT (p95 210.4 ms < 500 ms) |
| 10 | 48.2 | 148.3 | 235.1 | 1712.5 | 0.0% | ĐẠT (p95 235.1 ms < 500 ms) |
| 50 | 78.5 | 185.0 | 520.6 | 1845.0 | 0.0% | VI PHẠM (p95 520.6 ms > 500 ms) |
| 100 | 82.1 | 260.4 | 952.0 | 2145.0 | 0.0% | VI PHẠM (p95 952.0 ms > 500 ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

**Phân tích của tôi:**
RPS **KHÔNG** tăng tuyến tính theo concurrency:
1. **Giai đoạn tăng tốc (c=1 → c=10):** RPS tăng mạnh từ 5.8 lên 48.2 (tăng ~8.3 lần, gần tuyến tính). Lý do là server Uvicorn tận dụng rất tốt mô hình bất đồng bộ (async event loop) để xử lý I/O non-blocking trong lúc các request đang chờ mock LLM phản hồi.
2. **Giai đoạn suy giảm hiệu suất biên (c=10 → c=50):** Concurrency tăng gấp 5 lần (10 lên 50), nhưng RPS chỉ tăng khiêm tốn từ 48.2 lên 78.5 (tăng 1.6 lần). p50 bắt đầu tăng từ 148.3 ms lên 185.0 ms, và p95 vượt ngưỡng SLO (520.6 ms).
3. **Giai đoạn bão hòa và nghẽn hàng đợi (c=50 → c=100):** Concurrency tăng gấp đôi (50 lên 100), nhưng thông lượng RPS gần như đi ngang (78.5 lên 82.1 RPS, chỉ tăng 4.5%). Trong khi đó, p50 vọt lên 260.4 ms và p95 tăng phi mã lên 952.0 ms (gần 1 giây), p99 vượt 2.1 giây.
4. **Nguyên nhân cốt lõi:** Một single worker Uvicorn chạy trên 1 CPU core chỉ có thể xử lý một giới hạn tác vụ tính toán đồng thời (CPU bound cho serialization JSON, routing, HTTP parsing) và socket queueing. Khi số lượng request đồng thời vượt quá khả năng phục vụ của event loop, các request mới bắt buộc phải nằm đợi trong hàng đợi socket OS (queueing delay). Thời gian chờ xếp hàng này làm phình to tail latency trong khi throughput đã chạm trần phần cứng. Để tăng RPS tiếp, bắt buộc phải scale ngang ra nhiều worker process/container.

---

### 2.2 Tail latency

*Dữ liệu lấy từ `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json` (chạy tại concurrency 20, 300 requests):*

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 147.6 | 184.8 | 208.5 |
| 0.03 (mặc định) | 192.4 | 240.2 | 1722.0 |
| 0.1 | 294.8 | 1692.0 | 1785.0 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

**Phân tích của tôi:**
1. **Chỉ số nhạy nhất với request chậm:** Là **p99** và **p95** (các percentile cao ở đuôi phân phối):
   - Với `MOCK_SLOW_RATE=0.03` (chỉ 3% request bị chậm ~1.5s–1.8s): Thời gian trung bình (`avg`) chỉ tăng thêm 44.8 ms (từ 147.6 ms lên 192.4 ms) và p95 chỉ tăng nhẹ lên 240.2 ms; thế nhưng **p99 lập tức nhảy vọt từ 208.5 ms lên 1722.0 ms (tăng hơn 8.2 lần!)**.
   - Với `MOCK_SLOW_RATE=0.1` (10% request bị chậm): Do tỷ lệ request chậm vượt quá ngưỡng 5%, **p95 lập tức vỡ trận từ 240.2 ms vọt lên 1692.0 ms (tăng 7 lần)**. Trong khi đó, `avg` mới chỉ tăng lên 294.8 ms.
2. **Vì sao SLO không nên đặt theo Average (The Flaw of Averages):**
   - Giá trị trung bình (`avg`) là một cái bẫy toán học: nó bị làm loãng cực kỳ mạnh bởi số lượng lớn các request bình thường chạy nhanh (~140 ms).
   - Nếu một dịch vụ có 10% khách hàng phải chờ tới 1.7 giây (trải nghiệm cực kỳ ức chế), nhưng chỉ số trung bình vẫn báo `294.8 ms` — nếu team đặt SLO là `avg < 300 ms` thì dashboard vẫn báo "xanh" (đạt SLO), trong khi thực tế 1/10 người dùng đang gặp sự cố lag nghiêm trọng.
   - Do đó, chuẩn senior SRE bắt buộc phải thiết lập SLO theo các phân vị cao như **p95** hoặc **p99** để bảo vệ trải nghiệm của mọi nhóm khách hàng, đặc biệt là nhóm người dùng rơi vào đuôi phân phối trễ (tail latency).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

*Dữ liệu lấy từ `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json` (chạy trên 23 câu hỏi golden dataset):*

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | **100.0% (23/23)** |
| Avg tokens / câu | 45.0 | 88.0 | 92.0 |
| Tổng cost (USD) | $0.000736 | $0.001334 | $0.001403 |
| Cost / câu đúng (USD) | $0.000736 | $0.000064 | **$0.000061** |
| Quality gate | FAIL (4.3% < 80%) | FAIL (91.3% < 100%) | **PASS (100.0% ≥ 100%)** |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `['token', 'hết hạn', 'chữ ký']` | Bổ sung mục kiến thức `jwt` vào từ điển `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"JWT (JSON Web Token) là token xác thực không trạng thái gồm 3 phần: header, payload, chữ ký. Token có thời gian hết hạn (expiration time) để đảm bảo an toàn."* |
| `scaling-03` | `['cpu', 'memory', 'custom metrics']` | Bổ sung mục kiến thức `hpa` vào từ điển `KNOWLEDGE_BASE` trong `utils/mock_llm.py`: *"HPA (Horizontal Pod Autoscaler) tự động scale số lượng Pod dựa trên mức sử dụng CPU, Memory hoặc custom metrics thu thập từ hệ thống giám sát."* |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

1. **Chất lượng:** Agent v1 là mô hình ngây thơ không có retrieval/RAG, chỉ phản hồi một câu generic duy nhất (*"Đây là câu trả lời từ AI agent (mock)..."*), dẫn tới việc chỉ ngẫu nhiên đúng 1 câu cơ bản (accuracy 4.3%). Ngược lại, Agent v2 tích hợp context retrieval, đẩy độ chính xác ban đầu lên 91.3% (21/23 câu) và sau khi hoàn thiện Knowledge Base đạt 100.0% tuyệt đối mà không có bất kỳ regression nào so với baseline.
2. **Chi phí:** Agent v2 inject kiến thức vào prompt nên số token trung bình mỗi câu tăng khoảng gấp đôi (từ 45 lên 92 tokens), khiến tổng chi phí chạy eval tăng ~1.9 lần (từ $0.000736 lên $0.001403). Tuy nhiên, khi nhìn vào thước đo quan trọng nhất là **Cost / câu đúng (Effective Cost per Correct Answer)**, Agent v2 fixed lại **rẻ hơn v1 hơn 12 lần** (chỉ $0.000061/câu đúng so với $0.000736/câu đúng ở v1). Chi phí rẻ mà tạo ra 96% câu trả lời vô dụng thực chất là lãng phí tài nguyên lớn nhất.
3. **Latency:** v2 thực hiện thêm bước tra cứu kiến thức trong memory và xử lý prompt dài hơn, khiến latency trung bình tăng nhẹ (~149 ms so với ~125 ms ở v1, tăng ~19%), hoàn toàn nằm sâu trong ngưỡng an toàn của SLO (< 500 ms).
4. **Cơ chế Quality Gate trong CI/CD:**
   - Trong pipeline CI (GitHub Actions / GitLab CI), chúng tôi tích hợp lệnh:
     ```bash
     python eval/run_eval.py --baseline reports/eval_v2.json --min-accuracy 1.0
     ```
   - Script `run_eval.py` tận dụng chuẩn Unix exit code:
     - Khi kiểm tra thành công (accuracy đạt 100% và không có câu hỏi nào bị regression so với baseline): In `Quality gate: ✅ PASS` và kết thúc với `exit code 0`, cho phép pipeline tiếp tục các bước build và deploy.
     - Khi kiểm tra thất bại: In `Quality gate: ❌ FAIL` và kết thúc với `sys.exit(1)`. Pipeline CI lập tức bị fail, chặn hoàn toàn việc merge Pull Request vào branch `main` và ngăn ngừa mã nguồn lỗi được đưa lên production.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

---

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `HighErrorRate` (tỷ lệ lỗi > 5% trong 1 phút) | ~1 phút 15 giây (1m evaluation window + 15s scrape interval) | Panel *"Error Rate (%)"* và *"HTTP Status Codes by Instance"* vọt lên ~20% mã lỗi 500. |
| B | `MOCK_SLOW_RATE=0.3` | `HighLatencyP95` (p95 latency > 1s trong 2 phút) | ~2 phút 20 giây (2m evaluation window + 15s scrape interval) | Panel *"Request Latency (p50, p95, p99)"* với đường p95 vượt ngưỡng đỏ 1000ms lên ~1700ms. |
| C | `LLM_MODEL=mock-llm-large` | `HighCostRate` (cảnh báo tốc độ tiêu thụ chi phí/token tăng vọt) | ~2 phút 30 giây | Panel *"Token Consumption Rate"* và *"Estimated Cost ($/min)"* tăng gấp 3 lần bình thường. |
| D | `docker pause` 1 instance | `InstanceDown` / `AgentInstanceDown` (target scrape bị down) | ~1 phút 10 giây (1m `for` duration trong alert rule) | Panel *"Active Instances"* giảm từ 3 xuống 2; panel *"Traffic by Instance"* mất 1 đường metric. |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | Không bao giờ firing (mọi request trả 200 OK, latency ~120ms, CPU/RAM đều xanh) | Không panel hạ tầng nào cảnh báo; chỉ thấy Token count giảm bất thường ở panel *"Tokens/sec"*. |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

**Phân tích của tôi:**
Thí nghiệm E là điển hình của sự cố **"Model & Semantic Regression"** (suy giảm chất lượng mô hình). Về mặt hạ tầng vật lý, agent vẫn phản hồi HTTP 200 OK, không có lỗi exception, latency thậm chí còn nhanh hơn bình thường (~120ms), không tốn RAM hay CPU. Do đó, toàn bộ hệ thống giám sát hạ tầng truyền thống (Prometheus, Grafana, Node Exporter) hoàn toàn bị "mù" trước sự cố này.

Để phát hiện sự cố này trên production, tôi áp dụng các giải pháp chuẩn LLMOps:
1. **Synthetic Monitoring / Canaries theo lịch (Scheduled Eval):** Thiết lập một cronjob hoặc worker định kỳ (mỗi 5–15 phút) gửi bộ câu hỏi golden dataset vào endpoint production và chạy kiểm tra tự động (eval script). Nếu accuracy của synthetic probe rớt dưới 95%, hệ thống lập tức bắn alert mức độ P1 tới PagerDuty/Slack.
2. **Production Tracing & Semantic Evaluation (OpenTelemetry + Langfuse / Phoenix):** Thu thập toàn bộ log và trace kèm prompt, completion, token counts và model version. Theo dõi phân phối độ dài câu trả lời; nếu tỷ lệ câu trả lời generic lặp lại tăng đột biến, hệ thống phát hiện bất thường ngay lập tức.
3. **User Feedback Signals (Thumbs up / Thumbs down):** Thu thập tín hiệu phản hồi của người dùng trên giao diện chat và đưa vào Prometheus metric `agent_user_feedback_total{type="negative"}`. Khi tỷ lệ negative feedback vượt quá 5% trong 10 phút, kích hoạt alert điều tra chất lượng model.
4. **Token Consumption Anomaly Detection:** Thiết lập alert Prometheus phát hiện khi số lượng output tokens trung bình trên mỗi request đột ngột giảm > 40% so với baseline trong 15 phút (dấu hiệu agent rơi vào fallback response hoặc template ngắn).

**Giải thích thêm về Exercise 7.4:**
- **Khoảng cách giữa avg và p95:** Do phân phối thời gian phản hồi có tính chất lệch phải (right-skewed). Phần lớn request (~97%) hoàn thành nhanh chóng trong 130–150 ms. Chỉ có một tỷ lệ nhỏ (~3%) gặp trường hợp mock slow rate hoặc queue delay. Giá trị trung bình bị kéo tụt xuống bởi số đông request nhanh, trong khi p95 phản ánh chính xác ngưỡng thời gian thực tế mà 5% người dùng bị chậm.
- **Input tokens lớn hơn Output tokens:** Do hệ thống áp dụng kiến trúc Retrieval-Augmented Generation (RAG). Prompt template phải đóng gói toàn bộ đoạn context tri thức được tra cứu từ Knowledge Base kèm theo câu hỏi của user, khiến input prompt dài hơn rất nhiều so với câu trả lời cô đọng ở output.
- **Vì sao endpoint `/metrics` bị chặn ở Nginx bên ngoài:** Endpoint `/metrics` phơi bày toàn bộ dữ liệu nội bộ nhạy cảm của hệ thống: cấu trúc endpoint, số lượng request, tỷ lệ lỗi, thông số bộ nhớ, tên hàm, version app. Nếu mở công khai ra Internet, kẻ tấn công có thể thu thập thông tin tình báo (reconnaissance) để tìm điểm yếu DDoS hoặc khai thác bảo mật. Do đó, Nginx reverse proxy chỉ cho phép mạng nội bộ (Prometheus server) truy cập `/metrics` và chặn toàn bộ người dùng bên ngoài.

---

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất ghi nhận được trong Jaeger:

- `trace_id`: `a8f3b92c4e1d705a3b98c1e2f4a56789`
- Tổng thời gian: **1782.4 ms**
- Span chiếm nhiều thời gian nhất: `chat mock-llm-standard` (**1645.1 ms**, chiếm **92.3%** tổng thời gian request)
- Dòng log tương ứng (grep theo `trace_id` trong log JSON của container):

```json
{"timestamp": "2026-11-26T14:22:15.823Z", "level": "INFO", "service": "agent-v2", "trace_id": "a8f3b92c4e1d705a3b98c1e2f4a56789", "span_id": "4b8c9d1e2f3a4b5c", "method": "POST", "path": "/ask", "status_code": 200, "duration_ms": 1782.4, "llm_model": "mock-llm-standard", "llm_latency_ms": 1645.1, "tokens_used": 92, "client_ip": "10.0.1.45"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

*Dữ liệu lấy từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`:*

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 96.0 | 140 | 1720 | 1920 | 0 (0.0%) |
| 3 | 276.0 | 135 | 320 | 1780 | 0 (0.0%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

**Phân tích của tôi:**
1. **Scale có cải thiện p95 không?**
   - **CẢI THIỆN VƯỢT BẬC!** p95 giảm ngoạn mục từ **1720 ms xuống còn 320 ms** (giảm hơn **5.3 lần**).
   - Trước khi scale (1 instance), dưới tải 100 người dùng đồng thời, hệ thống vi phạm nghiêm trọng SLO (1720 ms so với ngưỡng < 500 ms).
   - Sau khi scale lên 3 instance đằng sau Nginx Load Balancer, p95 đạt 320 ms — hoàn toàn đáp ứng xuất sắc SLO đề ra.
   - Đồng thời, thông lượng (throughput) tăng gần gấp 3 lần từ **96.0 RPS lên 276.0 RPS** (hiệu suất scale đạt ~96% so với lý thuyết tuyến tính 3x). Tỷ lệ lỗi duy trì 0% tuyệt đối.
2. **Nút thắt (Bottleneck) nằm ở đâu?**
   - **Ở cấu hình 1 instance:** Nút thắt chính nằm ở tài nguyên CPU và event loop của single worker process. Khi 100 concurrent users dồn dập gửi request, hàng đợi kết nối bị tắc nghẽn (queueing delay), khiến các request phải chờ đợi lâu trước khi được phân phối vào event loop, làm p95 bị đẩy lên 1720 ms.
   - **Ở cấu hình 3 instances:** Hàng đợi CPU được giải tỏa hoàn toàn nhờ Nginx chia tải round-robin cho 3 process độc lập, giúp p95 giảm sâu xuống 320 ms. Tuy nhiên, **p99 vẫn ở mức 1780 ms** vì `MOCK_SLOW_RATE=0.03` giả lập độ trễ mạng/LLM cố hữu (3% request bị chậm). Lúc này nút thắt đã dịch chuyển từ tầng tính toán nội bộ (Web Agent) sang tầng phụ thuộc bên ngoài (Third-party LLM Provider).

---

## 6. Kết luận

- **3 điều tôi học được về benchmark & observability:**
  1. **"The Average Lie" (Cái bẫy của số trung bình):** Không bao giờ dùng average để đo lường SLO độ trễ. Luôn sử dụng Percentiles (p95, p99) kết hợp Distributed Tracing để vạch trần tail latency và định vị chính xác span gây nghẽn.
  2. **Giám sát hạ tầng là chưa đủ đối với hệ thống AI Agent:** Một agent có thể "xanh" toàn bộ về CPU, RAM, HTTP 200 nhưng câu trả lời bị hallucination hoặc suy thoái chất lượng hoàn toàn (như Thí nghiệm E). Cần xây dựng lớp giám sát chuyên biệt cho LLMOps: eval gate trong CI/CD, synthetic canary probes, và theo dõi biến động token/cost.
  3. **Scale ngang giải tỏa hàng đợi nhưng không xóa được trễ của dependency:** Scale 3 instance giải quyết triệt để nút thắt p95 do xếp hàng, nhưng các request rơi vào tail latency của LLM provider bên ngoài vẫn cần các giải pháp kiến trúc khác như Semantic Caching (Redis), Streaming response (SSE), và cơ chế Fallback model.
- **Nếu đưa agent này lên production thật, tôi sẽ bổ sung các metric / alert sau:**
  1. **Semantic Cache Hit Rate (%):** Đo lường tỷ lệ câu hỏi trùng lặp được trả lời ngay từ Redis vector cache mà không cần gọi ra LLM API bên ngoài, giúp tiết kiệm chi phí và giảm p95 latency xuống < 50ms.
  2. **Token & Budget Burn Rate Alert:** Cảnh báo khi tốc độ tiêu thụ ngân sách vượt ngưỡng quy định trong 1 giờ (phát hiện kịp thời vòng lặp vô tận của agent hoặc user spam tấn công quota).
  3. **Time To First Token (TTFT):** Đo lường thời gian từ lúc user gửi câu hỏi đến khi token đầu tiên hiển thị trên giao diện streaming qua Server-Sent Events (SSE).
  4. **Guardrails Violation Metric:** Đo lường tỷ lệ request bị chặn bởi lớp an toàn bảo mật (NeMo Guardrails / Llama Guard) do vi phạm chính sách prompt injection hoặc toxic content.
