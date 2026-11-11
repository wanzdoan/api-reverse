# Web Reverse Engineering: Pure Browserless Workflow (NO BROWSER / NO PLAYWRIGHT)

Quy trình 5 bước chuẩn hóa dành cho Reverse Engineer và Agent khi thực hiện bóc tách, đảo ngược logic các ứng dụng Web và API mà **hoàn toàn không sử dụng trình duyệt thật, không Playwright, không Puppeteer, không Selenium**.

---

## Nguyên Tắc Bất Di Bất Dịch:
> **100% CLI, Static Analysis, HTTP-Level Inspection, AST Deobfuscation & Node.js VM Emulation.**
> Không khởi chạy Chromium, Chrome, Edge, Firefox hay bất kỳ tiến trình tự động hóa trình duyệt nào.

---

## Bước 1: Thu thập Asset & Dò tìm Source Map (Asset Scraping)

Mục tiêu: Tải toàn bộ mã nguồn JavaScript tĩnh, file WebAssembly và kiểm tra rò rỉ Source Map mà không cần mở trình duyệt.

- Sử dụng công cụ `scripts/web-fetcher.py`:
  ```bash
  py scripts/web-fetcher.py "https://target.com" --out ./assets
  ```
- Script sử dụng `curl_cffi` (impersonate Chrome TLS JA3/JA4) để vượt qua Cloudflare/WAF, bóc tách toàn bộ thẻ `<script src="...">`, `<link rel="modulepreload">` từ HTML tĩnh.
- Tự động kiểm tra xem có tệp `.js.map` bị lộ trên server không. Nếu tìm thấy Source Map:
  ```bash
  npx source-map-unpack "./assets/bundle.js.map" ./src_restored
  ```
  -> Khôi phục nguyên vẹn 100% code TypeScript/ES6 gốc trước khi đóng gói!

---

## Bước 2: Phân tích Giao thức & Nhận diện Tham số Bảo vệ (Traffic & HAR Triage)

Mục tiêu: Phân tích cấu trúc request API mục tiêu từ cURL hoặc file HAR được lưu lại.

1. **Phân tích file HAR hoặc log mạng:**
   ```bash
   py scripts/har-analyzer.py ./traffic.har --filter "api" --diff
   ```
2. **Nhận diện các tham số động & trường bảo mật:**
   - Trường băm/chữ ký: `sign`, `signature`, `_signature`, `token`, `X-Sign`, `X-Timestamp`, `nonce`.
   - Tham số so sánh: So sánh giữa 2 request để xác định trường nào cố định (static) và trường nào thay đổi theo thời gian hoặc nội dung (dynamic).

---

## Bước 3: Giải mã AST & Tách Module Webpack (Static Deobfuscation)

Mục tiêu: Đọc hiểu và phân tích tệp JavaScript bị nén hoặc làm rối.

1. **Giải mã chuỗi và đơn giản hóa biểu thức:**
   ```bash
   node scripts/deobfuscate.cjs ./assets/app.js --out ./assets/app.clean.js
   ```
   - Giải mã toàn bộ chuỗi hex/unicode (`\x61` -> `a`).
   - Khởi tạo sandbox VM an toàn trong Node.js để giải quyết triệt để mảng chuỗi (String Array) và hàm giải mã chuỗi của Obfuscator.io.
   - Rút gọn biểu thức hằng (`!0` -> `true`, `0x1a` -> `26`).

2. **Tách module Webpack (Unpack Webpack):**
   ```bash
   node scripts/deobfuscate.cjs ./assets/app.js --unpack-webpack --out ./assets/webpack_modules/
   ```
   - Trích xuất từng module Webpack thành từng file riêng biệt (`module_1.js`, `module_2.js`) để dễ dàng grep tìm kiếm.

3. **Grep định vị điểm chốt logic:**
   - Tìm kiếm tên header bảo mật đã phát hiện ở Bước 2:
     ```bash
     grep -rn "X-Sign" ./assets/webpack_modules/
     ```

---

## Bước 4: Tái tạo Thuật toán ("Bổ JS" qua Node VM hoặc Viết lại Python)

Có 2 phương án thực thi (cả hai đều 100% không dùng trình duyệt):

### Phương án A: Viết lại thuật toán thuần túy bằng Python (Tối ưu nhất)
- Đọc hiểu logic toán học của hàm sinh chữ ký:
  - Thông thường là sự kết hợp của: Sắp xếp key từ điển (A-Z) + Nối chuỗi + Băm MD5/SHA256/HMAC với Salt bí mật.
  - Tái tạo bằng `hashlib` và `hmac` trong Python.

### Phương án B: Giả lập môi trường trong Node.js VM (Kỹ thuật "Bổ JS")
- Khi thuật toán quá phức tạp hoặc dùng nhiều phép biến đổi nhị phân:
- Cắt hàm tính toán ra tệp `extracted_logic.js`.
- Sử dụng `scripts/node-sandbox-runner.cjs`:
  ```bash
  node scripts/node-sandbox-runner.cjs ./extracted_logic.js --call calculateSign --args '["/api/data", 1727000000]'
  ```
- Script tự động polyfill các đối tượng `window`, `document`, `navigator`, `location` và vô hiệu hóa anti-debug trong Node.js.
- Có thể chạy làm service RPC cục bộ qua `--serve 8000` để Python gọi trực tiếp.

---

## Bước 5: Sinh mã PoC Khai Thác Độc Lập (Automated Replay PoC)

1. **Chuyển cURL thành mã Python:**
   ```bash
   py scripts/curl-to-code.py "curl 'https://target.com/api' -H 'X-Sign: ...'" -o poc.py
   ```
2. **Tích hợp hàm tính toán chữ ký động:**
   - Ghép hàm tính chữ ký từ Bước 4 vào `poc.py`.
   - Tham số hóa timestamp, nonce, payload.
3. **Thực thi và Kiểm chứng:**
   - Chạy `py poc.py` trong terminal.
   - Nhận phản hồi HTTP 200 OK với dữ liệu JSON giải mã thành công.
