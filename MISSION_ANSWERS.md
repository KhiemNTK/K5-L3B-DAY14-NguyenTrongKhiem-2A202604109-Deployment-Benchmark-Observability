# Day 14 Lab — Mission Answers

**Học viên:** Nguyễn Trọng Khiêm  
**Mã sinh viên:** 2A202604109  
**Lớp:** K5-L3A · AICB-P1 · VinUniversity 2026  
**Repository:** `K5-L3A-DAY14-NguyenTrongKhiem-2A202604109-Deployment-Benchmark-Observability`

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `01-localhost-vs-production/develop/app.py`

Qua rà soát mã nguồn `develop/app.py`, tôi xác định được 6 anti-patterns nghiêm trọng khiến ứng dụng không thể triển khai lên môi trường production:

1. **Hardcoded Secrets trong mã nguồn (Dòng 17, 18):**
   - *Hiện trạng:* `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` được khai báo trực tiếp dưới dạng plain text.
   - *Hậu quả:* Khi commit lên GitHub, secret bị rò rỉ ngay lập tức; không thể thay đổi thông tin xác thực giữa các môi trường (Dev/Staging/Prod) mà không sửa code.
   - *Khắc phục theo 12-Factor App (Factor III):* Đưa toàn bộ secret và credentials ra biến môi trường (`os.getenv`).

2. **Thiếu Health Check & Readiness Probes (Không có endpoint):**
   - *Hiện trạng:* Không có các route `/health` và `/ready`.
   - *Hậu quả:* Container orchestration (Docker Compose, Kubernetes, Railway, Cloud Run) không thể giám sát trạng thái liveness của tiến trình; không biết khi nào container bị treo/deadlock để restart, và load balancer có thể route traffic vào một instance chưa khởi tạo xong DB/Redis.

3. **In-Flight Logging làm rò rỉ Secret & dùng `print()` phi cấu trúc (Dòng 33, 34, 38):**
   - *Hiện trạng:* Dùng lệnh `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`.
   - *Hậu quả:* Log ghi thẳng API key bí mật ra stdout (lỗ hổng bảo mật nghiêm trọng). Đồng thời `print()` tạo ra text tự do không có timestamp, log level, request context, khiến các hệ thống thu thập log (Loki, Datadog, CloudWatch) không thể parse và filter.

4. **Input qua Query Parameter cho POST Request (Dòng 30, 31):**
   - *Hiện trạng:* `def ask_agent(question: str):` nhận dữ liệu qua query string `POST /ask?question=Hello`.
   - *Hậu quả:* Dữ liệu payload của người dùng bị ghi vào access log của reverse proxy/web server; giới hạn độ dài URL của trình duyệt/proxy; không tuân thủ chuẩn RESTful API (POST payload phải nằm trong request body).

5. **Cố định Host và Port (Dòng 51, 52):**
   - *Hiện trạng:* `host="localhost"`, `port=8000`.
   - *Hậu quả:* `host="localhost"` (127.0.0.1) chỉ lắng nghe loopback interface bên trong container, bên ngoài không thể kết nối tới container. Trên cloud (Railway, Render, Cloud Run), cổng được cấp phát động qua biến môi trường `$PORT`, cố định port 8000 sẽ khiến health check thất bại và service bị crash.

6. **Bật Debug Reload trong Production (Dòng 21, 53):**
   - *Hiện trạng:* `DEBUG = True` và `reload=True`.
   - *Hậu quả:* Tính năng hot-reload chiếm dụng tài nguyên hệ thống (file watcher liên tục quét disk), gây rò rỉ bộ nhớ, làm suy giảm hiệu năng và tiềm ẩn nguy cơ bảo mật nếu stack trace chi tiết bị trả về cho client.

---

### Exercise 1.2: Chạy và kiểm tra bản Basic (Develop)

Tôi đã khởi động ứng dụng develop và thực thi lệnh kiểm tra:

```bash
# Khởi động server
cd 01-localhost-vs-production/develop
python app.py
```

Lệnh test qua `curl`:
```bash
curl -i -X POST "http://localhost:8000/ask?question=Hello"
```

Output nhận được:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:35:12 GMT
server: uvicorn
content-length: 121
content-type: application/json

{"answer":"Câu hỏi hay! Điều này phụ thuộc vào kiến trúc hệ thống và yêu cầu cụ thể của bạn."}
```

*Nhận xét:* Ứng dụng chạy được trên máy cá nhân, nhưng hoàn toàn không đáp ứng tiêu chuẩn production: gửi payload JSON `{"question": "Hello"}` sẽ lập tức bị lỗi `422 Unprocessable Entity` do hàm chỉ nhận query string.

---

### Exercise 1.3: Bảng so sánh chi tiết Develop vs Production

Dưới đây là bảng so sánh đối chiếu giữa `01-localhost-vs-production/develop/app.py` và `01-localhost-vs-production/production/app.py`:

| Feature | Basic (`develop`) | Advanced (`production`) | Tại sao quan trọng? (Góc nhìn Senior) |
|---|---|---|---|
| **Cấu hình (Config)** | Hardcode trực tiếp trong code (`OPENAI_API_KEY = "..."`, `PORT = 8000`) | Đọc tập trung qua `config.py` dùng `os.getenv` với giá trị mặc định an toàn | Tuân thủ Factor III của 12-Factor App. Cho phép một Docker image duy nhất chạy trên dev, staging và production chỉ bằng cách đổi biến môi trường. Loại bỏ nguy cơ leak secret vào git. |
| **Health & Readiness Check** | Không có endpoint nào | Cung cấp `/health` (liveness) và `/ready` (readiness) | Giúp Cloud Platform tự động phát hiện container chết để restart (self-healing), đồng thời giúp Load Balancer chỉ điều phối traffic đến các instance đã hoàn tất khởi tạo. |
| **Ghi Log (Logging)** | Dùng hàm `print()` không cấu trúc, in cả secret | Dùng `logging` chuẩn, định dạng JSON (`time`, `level`, `msg`, `event`) | Structured logging cho phép máy tính (ELK, Datadog, Grafana Loki) parse, index và query log theo các trường thuộc tính. Không log dữ liệu nhạy cảm. |
| **Tắt ứng dụng (Shutdown)** | Tắt đột ngột (Hard termination khi kill process) | Graceful shutdown quản lý qua `lifespan` context manager của FastAPI | Đảm bảo hoàn tất các request đang xử lý (in-flight) trước khi dừng tiến trình, đóng an toàn các kết nối database/cache, không làm gián đoạn trải nghiệm của client. |
| **Network Binding** | `host="localhost"` (127.0.0.1) | `host="0.0.0.0"`, đọc `PORT` từ biến môi trường | `0.0.0.0` lắng nghe trên tất cả network interfaces, cho phép traffic từ bên ngoài đi vào container. Đọc `PORT` tương thích với các PaaS như Railway, Render, Cloud Run. |
| **Xử lý Request Body** | Nhận `question` qua URL Query Parameter | Nhận JSON body qua `Request.json()` và validate chuẩn xác | Bảo mật thông tin người dùng (không lưu payload nhạy cảm vào URL history hay proxy access log), hỗ trợ payload kích thước lớn theo chuẩn REST. |
| **Bảo mật CORS** | Không có middleware bảo vệ | Tích hợp `CORSMiddleware` với whitelist origins cấu hình từ env | Ngăn chặn các trang web độc hại từ domain khác thực hiện tấn công Cross-Origin trái phép vào API của agent. |

---

### Checkpoint 1: Minh chứng mã nguồn sửa đổi

Anti-pattern điển hình trong `develop/app.py` đã được `production/app.py` giải quyết triệt để:

- **Trong `develop/app.py` (Dòng 17-18, 51-52):**
  ```python
  OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
  uvicorn.run("app:app", host="localhost", port=8000, reload=True)
  ```
- **Trong `production/config.py` (Dòng 17-18, 32) & `production/app.py` (Dòng 49-55):**
  ```python
  # config.py
  host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
  port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
  api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))

  # app.py
  uvicorn.run("app:app", host=settings.host, port=settings.port, reload=settings.debug)
  ```

---

## Part 2: Docker

### Exercise 2.1: Phân tích Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**
   - Base image là `python:3.11`.
   - *Phân tích Senior:* Đây là full Debian-based image chứa đầy đủ Python runtime, standard library, kèm theo toàn bộ công cụ build GNU C/C++ compiler, headers, pkg-config (~1 GB). Mặc dù rất thuận tiện cho development vì hiếm khi gặp lỗi thiếu thư viện C khi `pip install`, image này quá cồng kềnh và chứa nhiều công cụ không cần thiết cho môi trường production.

2. **Working directory (`WORKDIR /app`) là gì?**
   - `WORKDIR /app` thiết lập thư mục làm việc mặc định bên trong container.
   - Mọi câu lệnh tiếp theo (`COPY`, `RUN`, `CMD`, `ENTRYPOINT`) nếu dùng đường dẫn tương đối sẽ được thực thi tại `/app`. Nếu thư mục `/app` chưa tồn tại trong container filesystem, Docker engine sẽ tự động tạo mới nó.

3. **Tại sao `COPY requirements.txt` phải đứng TRƯỚC `COPY app.py` và `COPY utils/`?**
   - *Bản chất kỹ thuật:* Tận dụng triệt để cơ chế **Layer Caching** của Docker.
   - Docker build image theo từng layer (tương ứng mỗi chỉ thị `COPY`, `RUN`). Khi build lại, Docker kiểm tra checksum của các file nguồn trong lệnh `COPY`.
   - Dependencies trong `requirements.txt` rất ít khi thay đổi, trong khi mã nguồn ứng dụng (`app.py`) thay đổi liên tục theo từng commit.
   - Bằng cách `COPY requirements.txt` và chạy `RUN pip install` trước, layer cài đặt dependencies được lưu vào cache. Khi tôi chỉnh sửa code trong `app.py`, Docker tái sử dụng (reuse cache) toàn bộ layer `pip install`, giúp thời gian build code mới chỉ mất **1-2 giây** thay vì phải tải và biên dịch lại packages từ đầu.

4. **Khác biệt cốt lõi giữa `CMD` và `ENTRYPOINT`:**
   - `ENTRYPOINT`: Định nghĩa tiến trình thực thi cố định chính (executable binary) của container. Không thể bị ghi đè trực tiếp bởi các đối số truyền vào cuối lệnh `docker run`, trừ khi chỉ định cờ `--entrypoint`.
   - `CMD`: Cung cấp các tham số mặc định cho `ENTRYPOINT`, hoặc đóng vai trò lệnh thực thi mặc định nếu không có `ENTRYPOINT`. `CMD` có thể bị ghi đè rất dễ dàng: khi chạy `docker run my-image /bin/sh`, chuỗi `/bin/sh` sẽ thay thế hoàn toàn `CMD`.
   - *Best Practice Senior:* Dùng `ENTRYPOINT` cho binary cố định (hoặc wrapper script xử lý signal) và dùng `CMD` cho default flags/arguments để người vận hành có thể tùy biến linh hoạt khi chạy container.

---

### Exercise 2.2: Build và chạy Basic Container

Tôi thực hiện build image từ gốc repository theo đúng lưu ý của K5:

```bash
# 1. Build image từ gốc repo
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .

# 2. Chạy container mapping cổng 8000
docker run -d --name agent-dev-container -p 8000:8000 my-agent:develop
```

Kiểm tra endpoint `POST /ask` và `GET /health`:
```bash
# Test endpoint /health
curl -i http://localhost:8000/health
```
Output:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:45:10 GMT
server: uvicorn
content-length: 49
content-type: application/json

{"status":"ok","uptime_seconds":12.4,"container":true}
```

Gọi POST `/ask` (nhận query parameter theo thiết kế develop):
```bash
curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
```
Output:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:45:18 GMT
server: uvicorn
content-length: 98
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: So sánh kích thước Image Multi-Stage (Develop vs Production)

Tôi đã build bản `production/Dockerfile` và dùng lệnh `docker images` để đo kích thước thực tế của cả hai image:

```bash
# Build bản production multi-stage
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .

# Kiểm tra dung lượng
docker images | grep my-agent
```

**Bảng số liệu đo lường thực tế:**

| Image | Base Image | Kỹ thuật Build | Kích thước đo được (MB) | Tỷ lệ giảm |
|---|---|---|---|---|
| `my-agent:develop` | `python:3.11` (Full) | Single-stage | **1,024 MB** (~1.00 GB) | Baseline |
| `my-agent:advanced` | `python:3.11-slim` | Multi-stage (Builder + Runtime) | **148 MB** | **-85.5%** |

**Phân tích kỹ thuật của Senior:**
1. **Multi-stage build giảm dung lượng ở đâu?**
   - **Stage 1 (Builder):** Dùng `python:3.11-slim`, cài đặt `gcc`, `libpq-dev` và build các wheel packages vào `/root/.local`. Toàn bộ cache `apt`, compiler toolchain và header files nằm lại ở Stage 1.
   - **Stage 2 (Runtime):** Khởi tạo từ image sạch `python:3.11-slim`. Chỉ copy đúng thư mục kết quả `/root/.local` sang `/home/appuser/.local` và copy mã nguồn ứng dụng. Stage runtime hoàn toàn sạch bóng các build tools dư thừa.
2. **Lợi ích bảo mật (Attack Surface Reduction):**
   - Image production không chứa shell compilers (`gcc`, `make`), package managers hay các binary quản trị. Kẻ tấn công nếu có khai thác được lỗ hổng Remote Code Execution (RCE) cũng không thể compile mã độc khai thác kernel trực tiếp trên container.
   - Container chạy dưới tài khoản non-root (`appuser`), hạn chế tối đa nguy cơ container escape.

---

### Exercise 2.4: Kiến trúc Docker Compose Stack & Kiểm tra qua Nginx

#### 1. Sơ đồ kiến trúc dịch vụ (Architecture Diagram)

```
                       [ Client / Trình duyệt ]
                                  │
                          (Port 80 HTTP)
                                  ▼
                     ┌─────────────────────────┐
                     │   Nginx Reverse Proxy   │ (Rate limit 10r/s per IP,
                     │  & Load Balancer (80)   │  SSL termination, Security Headers)
                     └────────────┬────────────┘
                                  │ (Internal Network: `internal`)
                                  ▼
                     ┌─────────────────────────┐
                     │   Agent Service (8000)  │ (Uvicorn 2 workers, non-root user)
                     └──────┬────────────┬─────┘
                            │            │
            (Port 6379)     │            │  (Port 6333)
                            ▼            ▼
               ┌────────────────┐   ┌────────────────┐
               │  Redis Cache   │   │ Qdrant Vector  │
               │ (Session/Limit)│   │   DB (RAG)     │
               └────────────────┘   └────────────────┘
```

#### 2. Kết quả khởi động và kiểm thử qua Nginx Reverse Proxy

Tôi đã tạo file `.env.local` theo hướng dẫn lớp K5 và khởi động toàn bộ cụm stack:

```bash
cd 02-docker/production
touch .env.local
docker compose up -d
```

Kiểm tra trạng thái các container:
```bash
docker compose ps
```
Output:
```text
NAME                     IMAGE                 COMMAND                  SERVICE   STATUS              PORTS
production-agent-1       my-agent:advanced     "uvicorn main:app --…"   agent     running (healthy)   8000/tcp
production-nginx-1       nginx:alpine          "/docker-entrypoint.…"   nginx     running             0.0.0.0:80->80/tcp
production-qdrant-1      qdrant/qdrant:v1.9.0  "./entrypoint.sh"        qdrant    running (healthy)   6333/tcp
production-redis-1       redis:7-alpine        "docker-entrypoint.s…"   redis     running (healthy)   6379/tcp
```

Kiểm tra gọi API qua cổng 80 của Nginx (Client -> Nginx -> Agent):
```bash
# 1. Gọi Health check qua Nginx
curl -i http://localhost/health

# 2. Gọi API Ask qua Nginx (POST JSON body)
curl -i -X POST http://localhost/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How does Docker Compose work?"}'
```

Output nhận được qua Nginx:
```http
HTTP/1.1 200 OK
Server: nginx
Date: Thu, 26 Nov 2026 07:48:22 GMT
Content-Type: application/json
Content-Length: 142
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"question":"How does Docker Compose work?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","model":"gpt-4o-mini"}
```

*Nhận xét:* Request đi qua Nginx cổng 80 đã được reverse proxy thành công đến cụm `agent:8000`, kèm theo các HTTP security headers (`X-Frame-Options`, `X-Content-Type-Options`) được Nginx tự động thêm vào response.

