# Deployment Information — Day 14 Lab

**Học viên:** Nguyễn Trọng Khiêm  
**Mã sinh viên:** 2A202604109  
**Lớp:** K5-L3B · AICB-P1 · VinUniversity 2026  
**Repository:** `K5-L3B-DAY14-NguyenTrongKhiem-2A202604109-Deployment-Benchmark-Observability`

---

## 1. Public Service URL

**Production Endpoint:**  
`https://k5-l3b-day14-nguyentrongkhiem-2a202604109-deploy-staging.up.railway.app`

---

## 2. Platform

- **Cloud Platform:** Railway
- **Region:** `us-west1`
- **Builder:** `DOCKERFILE` (Multi-stage build từ `06-lab-complete/Dockerfile` và root `Dockerfile`)
- **Backing Services:** Managed Redis (`redis:7-alpine`) trên Railway Private Network

---

## 3. Test Commands & Verification Results

### 3.1. Liveness Health Check (`GET /health`)
```bash
curl -i https://k5-l3b-day14-nguyentrongkhiem-2a202604109-deploy-staging.up.railway.app/health
```
**Expected Response:** `HTTP/1.1 200 OK`
```json
{
  "status": "ok"
}
```

### 3.2. Readiness Probe (`GET /ready`)
```bash
curl -i https://k5-l3b-day14-nguyentrongkhiem-2a202604109-deploy-staging.up.railway.app/ready
```
**Expected Response:** `HTTP/1.1 200 OK` (khi kết nối Redis thành công)
```json
{
  "status": "ready"
}
```

### 3.3. API Test — Authentication Required (Thiếu API Key)
```bash
curl -i -X POST https://k5-l3b-day14-nguyentrongkhiem-2a202604109-deploy-staging.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is cloud deployment?"}'
```
**Expected Response:** `HTTP/1.1 401 Unauthorized`
```json
{
  "detail": "Invalid or missing API key. Include header: X-API-Key: <key>"
}
```

### 3.4. API Test — Authentication Success (Có API Key)
```bash
curl -i -X POST https://k5-l3b-day14-nguyentrongkhiem-2a202604109-deploy-staging.up.railway.app/ask \
  -H "X-API-Key: k5-aicb-sec-2a202604109-prod" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is cloud deployment?"}'
```
**Expected Response:** `HTTP/1.1 200 OK`
```json
{
  "question": "What is cloud deployment?",
  "answer": "Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."
}
```

---

## 4. Environment Variables Configured on Railway

Các biến môi trường được cấu hình an toàn trên Railway Dashboard (không commit secret vào code):

| Variable Name | Environment | Description |
|---|---|---|
| `PORT` | `8000` | Port lắng nghe được Railway inject tự động |
| `ENVIRONMENT` | `production` | Môi trường triển khai |
| `AGENT_API_KEY` | `k5-aicb-sec-2a202604109-prod` | Khóa bí mật xác thực API |
| `REDIS_URL` | `redis://default:***@redis.railway.internal:6379` | Connection string tới Railway Redis instance |
| `RATE_LIMIT_PER_MINUTE` | `10` | Giới hạn sliding window rate limit |
| `DAILY_BUDGET_USD` | `10.0` | Ngân sách giới hạn chi phí token hàng ngày |

---

## 5. Deployment Screenshots

- [Dashboard tổng quan dịch vụ](screenshots/dashboard.png)
- [Trạng thái Active/Running của Agent & Redis](screenshots/running.png)
- [Kết quả 4 lệnh kiểm tra HTTP code](screenshots/test.png)
