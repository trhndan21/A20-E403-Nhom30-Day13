# Báo cáo Cá nhân — Day 13 Observability Lab

| Thông tin | Chi tiết |
|---|---|
| **Họ và tên** | Tạ Thị Thuỳ Dương |
| **Mã sinh viên** | 2A202600287 |
| **Vai trò trong nhóm** | Member A — Logging & PII |
| **Nhóm** | Nhóm 30 — A20-E403 |
| **Repo** | https://github.com/tttduong/A20-E403-Nhom30-Day13 |
| **Branch cá nhân** | `main` |
| **Commit chính** | `0228cf5` — `"duong, Logging & PII"` |

---

## 1. Nhiệm vụ được phân công

Theo kế hoạch nhóm, Dương chịu trách nhiệm **Logging & PII** — đảm bảo mọi request đều có correlation ID duy nhất và không lộ thông tin cá nhân trong logs.

### Checklist nhiệm vụ

| # | Nhiệm vụ | Trạng thái |
|---|---|:---:|
| 1 | `middleware.py` — Gọi `clear_contextvars()` đầu `dispatch()` để tránh rò context giữa các request | ✅ Hoàn thành |
| 2 | `middleware.py` — Extract `x-request-id` từ header, tự sinh `req-<8 hex>` nếu không có | ✅ Hoàn thành |
| 3 | `middleware.py` — `bind_contextvars(correlation_id=correlation_id)` gắn ID vào structlog context | ✅ Hoàn thành |
| 4 | `middleware.py` — Thêm 2 response header: `x-request-id` và `x-response-time-ms` | ✅ Hoàn thành |
| 5 | `logging_config.py` — Thêm `scrub_event` vào danh sách processors của structlog | ✅ Hoàn thành |
| 6 | `pii.py` — Thêm regex cho Passport VN (`[A-Z]\d{7}`), CMND/CCCD (`\d{9}\|\d{12}`), địa chỉ VN | ✅ Hoàn thành |

---

## 2. Các file đã chỉnh sửa

### 2.1 `app/middleware.py` — Correlation ID Middleware

**Vấn đề ban đầu:** Mọi request không có định danh duy nhất — khi có lỗi không thể biết log line nào thuộc request nào.

**Những gì tôi đã làm:**

```python
async def dispatch(self, request: Request, call_next):
    clear_contextvars()  # reset context từ request trước

    correlation_id = request.headers.get("x-request-id") or f"req-{secrets.token_hex(4)}"
    bind_contextvars(correlation_id=correlation_id)
    request.state.correlation_id = correlation_id

    start = time.perf_counter()
    response = await call_next(request)

    response.headers["x-request-id"] = correlation_id
    response.headers["x-response-time-ms"] = str(round((time.perf_counter() - start) * 1000, 2))
    return response
```

- `clear_contextvars()`: xóa dict context của structlog — tránh metadata của request trước bị rò sang request mới trong môi trường async
- Tự sinh `req-<8 hex>` nếu client không gửi header — đảm bảo mọi request đều có ID
- Trả lại `x-request-id` qua response header để client/frontend có thể dùng khi báo lỗi

### 2.2 `app/pii.py` — PII Scrubbing Patterns

**Vấn đề ban đầu:** Chỉ có regex cho email, phone, credit card — chưa cover đặc thù Việt Nam.

**Những gì tôi đã làm — thêm 3 patterns:**

```python
PII_PATTERNS: dict[str, str] = {
    "email":       r"[\w\.-]+@[\w\.-]+\.\w+",
    "phone_vn":    r"(?:\+84|0)[ \.-]?\d{3}[ \.-]?\d{3}[ \.-]?\d{3,4}",
    "cccd":        r"\b\d{12}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "passport_vn": r"\b[A-Z]\d{7}\b",       # Hộ chiếu VN: B1234567
    "cmnd":        r"\b\d{9}\b",             # CMND 9 số
    "address_vn":  r"\b(?:phường|quận|thành phố|tp\.?)\s+[\w\s]+",  # Địa chỉ VN
}
```

Hàm `scrub_text()` duyệt qua tất cả patterns và replace bằng `[REDACTED_<TYPE>]` trước khi ghi log.

### 2.3 `app/logging_config.py` — Cắm scrubber vào pipeline

**Những gì tôi đã làm:** Đảm bảo `scrub_event` có mặt trong danh sách processors của structlog:

```python
structlog.configure(
    processors=[
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        scrub_event,          # ← scrub PII trước khi ghi ra file
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        JsonlFileProcessor(),
        structlog.processors.JSONRenderer(),
    ],
    ...
)
```

`scrub_event` chạy trước `JsonlFileProcessor` — đảm bảo PII bị xóa trước khi ghi vào `data/logs.jsonl`.

---

## 3. Kết quả `validate_logs.py`

```
--- Lab Verification Results ---
Total log records analyzed: 99
Records with missing required fields: 0
Records with missing enrichment (context): 0
Unique correlation IDs found: 44
Potential PII leaks detected: 0

--- Grading Scorecard (Estimates) ---
+ [PASSED] Basic JSON schema
+ [PASSED] Correlation ID propagation
+ [PASSED] Log enrichment
+ [PASSED] PII scrubbing

Estimated Score: 100/100
```

---

## 4. Hiểu sâu về phần việc đảm nhận

### Tại sao phải `clear_contextvars()` trước khi `bind`?

FastAPI chạy async — nhiều request tồn tại đồng thời trong cùng 1 process. structlog dùng `contextvars.ContextVar` để mỗi coroutine có bản copy riêng của context dict. Nếu không `clear()`, context của request trước (gồm `user_id_hash`, `session_id` của user A) sẽ bị kế thừa sang request sau — log của user B sẽ ghi nhầm thành user A.

### Tại sao scrub ở tầng logging, không phải ở handler?

Log thường đi ra nhiều nơi: file local, Elasticsearch, S3, Datadog. Nếu scrub ở handler, một log statement bị bỏ sót là đủ để lộ PII. Scrub tại processor của structlog đảm bảo **mọi log line đều được xử lý**, bất kể ai viết code.

### Giải thích regex `address_vn`

```python
r"\b(?:phường|quận|thành phố|tp\.?)\s+[\w\s]+"
```

- `(?:phường|quận|thành phố|tp\.?)` — keyword trigger
- `\s+[\w\s]+` — capture tên địa danh theo sau
- Ví dụ: `"phường Bến Nghé, quận 1"` → `"[REDACTED_ADDRESS_VN]"`

---

## 5. Bằng chứng Git

| File | Loại thay đổi | Commit |
|---|---|---|
| `app/middleware.py` | Modified | `0228cf5` |
| `app/pii.py` | Modified | `0228cf5` |
| `app/logging_config.py` | Modified | `0228cf5` |
| Screenshots evidence | Added | `ef1a6c3` |

**Link commit code:** https://github.com/tttduong/A20-E403-Nhom30-Day13/commit/0228cf554620421bb7bcd58a21176242e0e60f98

**Link commit screenshot:** https://github.com/tttduong/A20-E403-Nhom30-Day13/commit/ef1a6c30413590b69939aefdbca1a6dc010f55ae

**Screenshot bằng chứng:**
- `docs/evidence/log-pii-redacted-email-and correlation-id.png` — log line có `"correlation_id"` và email đã redact
- `docs/evidence/log-pii-redacted-creditcard.png` — log line có số thẻ đã redact

---

## 6. Tự đánh giá

| Hạng mục rubric | Tự chấm | Lý do |
|---|:---:|---|
| **B1 — Individual Report** | 20/20 | Giải thích đủ sâu về middleware và PII regex |
| **B2 — Git Evidence** | 20/20 | 2 commits rõ ràng tách code và screenshot |
| **Tổng cá nhân** | **40/40** | |
