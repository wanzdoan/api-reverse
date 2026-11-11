# API Cryptographic Signatures & Reverse Engineering

Cẩm nang nhận diện và tái tạo các thuật toán tính chữ ký số (Request Signing), mã hóa tham số và bảo vệ API trong ứng dụng Web.

---

## 1. Các mô hình ký danh API thường gặp (Common Signature Patterns)

Hầu hết các hệ thống API hiện đại sử dụng một trong các công thức sau để chống sửa đổi dữ liệu (Anti-Tamper):

### Mô hình 1: MD5 / SHA256 với Salt tĩnh
```text
sign = MD5("param1=val1&param2=val2&timestamp=1727680000" + SECRET_SALT)
```
- **Đặc điểm:** Thường có tham số `t` hoặc `_t` (timestamp).
- **Cách tìm:** Đặt breakpoint tại `md5(` hoặc `CryptoJS.MD5(`; tìm chuỗi `SECRET_SALT` được nối ở cuối chuỗi tham số.

### Mô hình 2: HMAC-SHA256 với Secret Key
```text
sign = HMAC_SHA256(key=API_SECRET, message=METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH)
```
- **Đặc điểm:** Tương tự AWS SigV4 hoặc chuẩn OAuth.
- **Cách tìm:** Hook `crypto.subtle.sign` hoặc `CryptoJS.HmacSHA256`.

### Mô hình 3: Sắp xếp tham số từ điển (Sorted Query Params)
Các tham số trong URL hoặc Body được gom lại, sắp xếp theo thứ tự bảng chữ cái A-Z, sau đó nối thành chuỗi trước khi băm:
```javascript
const sortedKeys = Object.keys(params).sort();
const rawString = sortedKeys.map(k => `${k}=${params[k]}`).join('&');
const sign = md5(rawString + salt);
```

### Mô hình 4: Mã hóa đối xứng AES (CBC / GCM / ECB)
Toàn bộ body JSON được mã hóa thành một chuỗi Base64 hoặc Hex dài:
```text
payload = AES_Encrypt(plaintext=json_string, key=aes_key, iv=aes_iv)
```
- **Đặc điểm:** Header `Content-Type: text/plain` hoặc request body chỉ có 1 trường duy nhất `data: "q8s9d7f6..."`.
- **Cách tìm:** Hook `CryptoJS.AES.encrypt` hoặc `crypto.subtle.encrypt`.

---

## 2. Quy trình 4 bước bóc tách chữ ký số

1. **Bước 1: Xác định giá trị đầu ra (Output Identification)**
   - Quan sát gói tin HTTP trong tab Network.
   - Tìm kiếm các header hoặc query params khả nghi:
     - `sign`, `signature`, `_signature`, `_t`, `token`, `x-token`, `x-sign`, `nonce`, `hash`.

2. **Bước 2: Tìm nguồn gốc nơi gán giá trị (Tracing Origin)**
   - Mở Console DevTools, chạy Hook trap:
     ```javascript
     hookProperty(window, 'sign');
     ```
   - Hoặc tìm kiếm tên header trong file JS đã deobfuscate:
     `grep -rn "x-sign" .`
   - Hoặc đặt XHR/Fetch Breakpoint khi URL chứa `/api/target`.

3. **Bước 3: Đọc hiểu và phân rã logic (Logic Disassembly)**
   - Khi breakpoint dừng lại tại hàm tạo chữ ký, quan sát các biến Local trong scope:
     - Biến đầu vào: query params, payload, timestamp, deviceId.
     - Salt / Secret key: có cố định hay lấy từ cookie / local storage?
     - Thuật toán băm: MD5, SHA-1, SHA-256, HMAC hay thuật toán biến dị tự viết?

4. **Bước 4: Viết lại bằng Python / Node.js độc lập**
   - Viết test case: Lấy đúng bộ input bắt được từ trình duyệt, đưa vào hàm Python xem kết quả băm có trùng khớp 100% với giá trị `sign` mà trình duyệt đã gửi đi hay không.
   - Khi đã khớp 100%, tích hợp hàm vào script gọi API tự động.
