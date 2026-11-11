# HAR-Driven API Reverse Engineering & Session Probing Guide

Cẩm nang chuyên sâu về phương pháp tiếp cận Reverse Engineering từ tệp `.har` (HTTP Archive), tái sử dụng Cookie và Header sống để tự động hóa và "đục" sâu các API liên quan mà **hoàn toàn không cần mở lại trình duyệt**.

---

## 1. Lợi Thế Khi Có Sẵn Tệp `.har`

Khi người dùng đã thao tác trên web và xuất ra file `.har` (từ DevTools Network -> "Export HAR"):
1. **Có sẵn phiên đăng nhập (Live Session):** Đã vượt qua khâu đăng nhập, Captcha, 2FA hoặc xác thực SMS ban đầu. Cookie (`session_id`, `cf_clearance`, `jwt`) và Authorization Header đã hợp lệ.
2. **Không cần đảo ngược luồng Auth phức tạp:** Có thể tập trung 100% vào API nghiệp vụ mục tiêu (ví dụ: lấy dữ liệu, đặt lệnh, cập nhật thông tin).
3. **Mẫu dữ liệu thực tế (Real-world Baseline):** Nắm rõ cấu trúc request hợp lệ, User-Agent, thứ tự header và phản hồi mẫu của máy chủ.

---

## 2. Quy Trình 3 Bước Xử Lý Tệp `.har`

### Bước 1: Trích xuất Session State & Tự Động Sinh Tool API Client
Chạy lệnh tự động hóa qua `scripts/har-analyzer.py`:

```bash
# 1. Trích xuất toàn bộ cookies, auth tokens, headers ra JSON
py scripts/har-analyzer.py session.har --export-session session_state.json

# 2. Sinh trực tiếp mã nguồn Python API Client hoàn chỉnh
py scripts/har-analyzer.py session.har --gen-client api_client.py
```

Tệp `api_client.py` được sinh ra tự động:
- Đã gắn sẵn toàn bộ Cookie và Header từ file `.har`.
- Khởi tạo `curl_cffi` với `impersonate="chrome124"` (trùng khớp với User-Agent trong HAR) để giữ cho session không bị WAF khóa.
- Đã có sẵn các method gọi các API bắt được trong HAR.

---

### Bước 2: Dò Tìm & Khám Phá Endpoint Ẩn ("Đục" Thêm API)

Trong quá trình người dùng thao tác, trình duyệt chỉ mới gọi một phần nhỏ trong toàn bộ hệ thống API. Để "đục" thêm các API liên quan:

#### a) Quét Endpoint từ nội dung phản hồi (Response Bodies) & JS:
```bash
py scripts/har-analyzer.py session.har --find-endpoints
```
Lệnh này quét toàn bộ JSON/HTML/JS trong HAR để tìm các chuỗi URL dạng `/api/...`, `/v1/...`, `/graphql`.

#### b) Đoán nhận & Dò quét cấu trúc tương đồng (Path Enumeration):
Dựa vào các endpoint đã có trong HAR, suy luận các API cùng cấp:
- Nếu có: `GET /api/v1/user/profile`
  - Thử dò: `GET /api/v1/user/settings`
  - Thử dò: `GET /api/v1/user/orders`
  - Thử dò: `GET /api/v1/user/wallet`
  - Thử dò: `GET /api/v1/user/notifications`
- Nếu có: `GET /api/v1/items?category=1`
  - Thử dò: `GET /api/v1/items/detail?id=123`
  - Thử dò: `POST /api/v1/items/checkout`

#### c) Dò quét bằng method `probe_endpoint()` có sẵn trong Client:
```python
from api_client import ApiClient

client = ApiClient()

candidates = [
    "/api/v1/user/wallet",
    "/api/v1/user/transactions",
    "/api/v1/user/addresses",
    "/api/v1/orders/history"
]

for endpoint in candidates:
    success, resp = client.probe_endpoint(endpoint)
    if success:
        print(f"[+] Khám phá thành công API mới: {endpoint}")
```

---

### Bước 3: Phân Tích Chữ Ký Riêng (Nếu Endpoint Mới Yêu Cầu Chữ Ký Động)

Nếu một số endpoint yêu cầu chữ ký động (`sign`, `X-Signature` thay đổi theo từng request):
1. Dùng `py scripts/har-analyzer.py session.har --diff` để xác định trường nào trong request là chữ ký động.
2. Dùng `py scripts/web-fetcher.py` tải các bundle JS về.
3. Dùng `node scripts/deobfuscate.cjs` để gỡ rối code JS.
4. Dùng `scripts/node-sandbox-runner.cjs` ("Bổ JS") để tính toán chữ ký động và nạp vào method của `ApiClient`.

---

## 3. Quản Lý Session & Cookie Hết Hạn (Session Refreshing)

- **Kiểm tra độ sống của Cookie:** Nếu API trả về `401 Unauthorized` hoặc `403 Forbidden`, nghĩa là cookie/token trong file `.har` đã hết hạn.
- **Tách riêng cấu hình session:** Khuyên dùng cấu hình tách rời `session_state.json`. Khi người dùng thao tác lại và lấy session mới, chỉ cần cập nhật file `session_state.json` mà không cần sửa lại code tool.
