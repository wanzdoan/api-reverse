# Pure Node.js Sandbox & Environment Emulation Guide (Bổ JS Thuần)

Cẩm nang chuyên sâu về kỹ thuật bóc tách và thực thi mã nguồn JavaScript của trang web bên trong Node.js mà **HOÀN TOÀN KHÔNG DÙNG TRÌNH DUYỆT THẬT (No Chrome, No Playwright, No Puppeteer, No Selenium)**.

---

## 1. Triết lý "Bổ JS" (Pure JavaScript Emulation)

Trong web reverse engineering chuyên nghiệp, việc bật một trình duyệt thật tốn nhiều tài nguyên (CPU, RAM), dễ bị các hệ thống WAF phát hiện (qua `navigator.webdriver`, canvas fingerprint, CDP flags), và rất chậm khi cần cào dữ liệu hay gọi API ở quy mô lớn.

Phương pháp tối ưu nhất là:
1. **Tìm đúng đoạn mã sinh chữ ký / mã hóa dữ liệu** trong bundle JS tĩnh.
2. **Cắt đoạn mã đó ra** (Extract snippet).
3. **Giả lập môi trường trình duyệt tối thiểu** bên trong Node.js (`window`, `document`, `navigator`).
4. **Chạy trực tiếp hàm trong Node.js VM** hoặc chuyển đổi sang Python thuần.

---

## 2. Kỹ thuật Giả lập các Đối tượng Trình duyệt (Polyfilling)

Khi một hàm JS trên web chạy trong Node.js, nó thường gặp lỗi `ReferenceError: window is not defined` hoặc `Cannot read properties of undefined (reading 'userAgent')`. Ta cần bổ sung các đối tượng giả lập:

### a) Cấu hình window & globalThis cơ bản:
```javascript
const window = global;
global.window = window;
global.self = window;
global.top = window;
global.parent = window;
```

### b) Giả lập `navigator`:
```javascript
global.navigator = {
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    appVersion: "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    platform: "Win32",
    language: "en-US",
    languages: ["en-US", "en"],
    webdriver: false,
    hardwareConcurrency: 8,
    cookieEnabled: true
};
```

### c) Giả lập `document`:
```javascript
global.document = {
    cookie: "session_id=mock_cookie_here;",
    referrer: "",
    title: "",
    createElement: function(tag) {
        if (tag.toLowerCase() === 'canvas') {
            return {
                getContext: () => ({
                    fillText: () => {},
                    getImageData: () => ({ data: new Uint8Array([1, 2, 3, 4]) })
                }),
                toDataURL: () => "data:image/png;base64,mock"
            };
        }
        return { style: {}, setAttribute: () => {}, appendChild: () => {} };
    },
    getElementById: () => null,
    getElementsByTagName: () => []
};
```

### d) Giả lập `location`:
```javascript
global.location = {
    href: "https://api.target.com/page",
    protocol: "https:",
    host: "api.target.com",
    hostname: "api.target.com",
    pathname: "/page",
    search: "",
    hash: "",
    origin: "https://api.target.com"
};
```

---

## 3. Vô hiệu hóa Anti-Debugging trong Node.js

Mã nguồn bị obfuscated thường chứa các lệnh bẫy:
1. `debugger;`
2. `(function() { return this; })().constructor('debugger')()`
3. Kiểm tra độ lệch thời gian `performance.now()`.

### Cách xử lý:
- Dùng `scripts/node-sandbox-runner.cjs` — script đã được tích hợp sẵn bộ lọc regex để thay thế mọi lệnh `debugger` trước khi đưa vào Node VM.
- Đặt giới hạn thời gian thực thi `timeout` trong `vm.Script.runInContext` để tránh vòng lặp vô tận (infinite loop).

---

## 4. Cầu nối giữa Python và Node.js (Node RPC Server)

Khi viết chương trình cào dữ liệu hoặc kiểm thử bảo mật bằng Python, nếu việc viết lại thuật toán JS sang Python quá tốn thời gian (do thuật toán quá dài hoặc sử dụng Webpack phụ thuộc nhiều module), ta có thể dùng tính năng `--serve` của `node-sandbox-runner.cjs`:

```bash
# Khởi chạy Node sandbox thành service HTTP nội bộ tại cổng 8000
node scripts/node-sandbox-runner.cjs ./extracted_sign.js --call getSignature --serve 8000
```

Trong code Python:
```python
import requests

def get_signature_from_node(params):
    res = requests.post("http://127.0.0.1:8000", json={
        "function": "getSignature",
        "args": [params]
    })
    return res.json()["result"]

# Sử dụng signature trong request
sign = get_signature_from_node({"query": "laptop", "page": 1})
```
Ưu điểm: Không cần trình duyệt, độ trễ cực thấp (< 5ms mỗi lần gọi), ổn định 100%.
