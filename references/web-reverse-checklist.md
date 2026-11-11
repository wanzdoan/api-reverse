# Web Reverse Engineering: Browserless Pre-flight & Delivery Checklist

Bảng kiểm tra (Checklist) quy chuẩn dành cho Agent và Kỹ sư trước khi bắt đầu và trước khi bàn giao kết quả reverse engineering theo phương pháp **Browserless / Pure CLI (Không dùng trình duyệt thật, không Playwright)**.

---

## 1. Ràng buộc Tác chiến Cốt lõi (Strict Constraints)

- [ ] **TUYỆT ĐỐI KHÔNG mở trình duyệt thật** (Chrome, Edge, Firefox, Brave).
- [ ] **TUYỆT ĐỐI KHÔNG cài đặt hoặc sử dụng Playwright, Puppeteer, Selenium**.
- [ ] Mọi hoạt động tải dữ liệu được thực hiện qua HTTP Client (`curl_cffi`, `httpx`, `fetch`).
- [ ] Mọi hoạt động thực thi JavaScript được thực hiện bên trong Node.js VM / Sandbox hoặc chuyển ngữ sang Python.

---

## 2. Giai đoạn Neo mục tiêu (Objective Scoping)

- [ ] Đã xác nhận mục tiêu cụ thể từ người dùng vào `@muc_tieu` (ví dụ: bóc tách chữ ký `_signature`, giải mã token, tìm thuật toán mã hóa payload).
- [ ] Đã xác định rõ URL API, Method (GET/POST) và dữ liệu cần trích xuất.

---

## 3. Giai đoạn Thu thập & Phân tích Tĩnh (Recon & Static Analysis)

- [ ] Đã tải mã nguồn bundle tĩnh bằng `scripts/web-fetcher.py`.
- [ ] Đã kiểm tra sự tồn tại của tệp `.js.map` (Source Map).
- [ ] Đã phân tích file HAR hoặc mẫu request bằng `scripts/har-analyzer.py`.
- [ ] Đã xác định danh sách các trường động (Timestamp, Nonce, Token, Signature).
- [ ] Đã deobfuscate mã nguồn JS bằng `scripts/deobfuscate.cjs` (giải mã chuỗi hex, string array, unpack webpack).

---

## 4. Giai đoạn Tái tạo Logic & Bàn giao (Delivery Checklist)

- [ ] Đã chạy thử thuật toán trong Node.js sandbox qua `scripts/node-sandbox-runner.cjs` hoặc viết lại thành công bằng Python thuần.
- [ ] Script PoC (`poc.py` / `poc.js`) chạy độc lập 100% trong terminal mà không yêu cầu môi trường đồ họa hay trình duyệt.
- [ ] Sử dụng `curl_cffi` (impersonate) trong Python để vượt qua kiểm tra TLS JA3/JA4 của Cloudflare/Akamai.
- [ ] Báo cáo `ANALYSIS_REPORT.md` đã có đầy đủ:
  - Mục tiêu ban đầu
  - Endpoint URL, Method, Headers
  - Phân tích chi tiết thuật toán mã hóa / ký danh (Kèm vị trí dòng code JS)
  - Đoạn code PoC hoàn chỉnh có thể chạy được ngay.
