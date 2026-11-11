# Anti-Debug & WAF Fingerprinting Evasion Guide

Hướng dẫn toàn diện về nhận diện, vô hiệu hóa các cơ chế chống dịch ngược (Anti-Debugging) và vượt qua kiểm tra dấu vân tay (WAF / TLS Fingerprinting).

---

## 1. Các dạng Anti-Debugging phổ biến trên Trình duyệt

### a) Vòng lặp vô hạn `debugger;` (Infinite Debugger)
Trang web định kỳ gọi lệnh `debugger;` để làm treo tab DevTools:
- **Dạng 1: `setInterval` / `setTimeout` gọi trực tiếp:**
  ```javascript
  setInterval(() => { debugger; }, 100);
  ```
- **Dạng 2: Tạo hàm động qua `Function` constructor:**
  ```javascript
  (function() {
      (function a() {
          try {
              (function b(i) {
                  if (('' + (i / i)).length !== 1 || i === 0) {
                      (function() {}).constructor('debugger')();
                  } else {
                      [].filter.constructor('debugger')();
                  }
                  b(++i);
              }(0));
          } catch (e) {
              setTimeout(a, 500);
          }
      }());
  }());
  ```
- **Dạng 3: `eval('debugger')`**

### Cách vô hiệu hóa:
1. **Never pause here:** Trong Chrome DevTools, chuột phải vào dòng có chữ `debugger` và chọn **"Never pause here"**.
2. **Hook Function Constructor:**
   ```javascript
   const _Function = window.Function;
   window.Function = function(...args) {
       if (args.length > 0 && typeof args[args.length - 1] === 'string' && args[args.length - 1].includes('debugger')) {
           args[args.length - 1] = '';
       }
       return _Function.apply(this, args);
   };
   ```
3. **Hook eval:**
   ```javascript
   const _eval = window.eval;
   window.eval = function(code) {
       if (typeof code === 'string' && code.includes('debugger')) {
           code = code.replace(/debugger\s*;?/g, '');
       }
       return _eval.apply(this, arguments);
   };
   ```

---

## 2. Phát hiện mở DevTools (DevTools Detection)

1. **Phát hiện qua kích thước cửa sổ:**
   So sánh `window.outerWidth - window.innerWidth > 160`.
   - *Cách đối phó:* Mở DevTools ở dạng cửa sổ rời (Undock into separate window).
2. **Phát hiện qua `console.log` Getter:**
   Đối tượng truyền vào `console.log` có thuộc tính `id` dạng getter. Khi DevTools mở, trình duyệt sẽ tự động gọi getter để render UI:
   ```javascript
   const element = new Image();
   Object.defineProperty(element, 'id', {
       get: function() { devtoolsOpen = true; }
   });
   console.log(element);
   ```
   - *Cách đối phó:* Ghi đè `console.log = function() {}` ngay từ đầu.
3. **Phát hiện qua độ lệch thời gian (Timing check):**
   ```javascript
   const start = performance.now();
   debugger;
   if (performance.now() - start > 100) {
       // DevTools đang dừng breakpoint!
   }
   ```
   - *Cách đối phó:* Tắt tính năng dừng breakpoint hoặc vô hiệu hóa `debugger`.

---

## 3. Vượt qua WAF & Fingerprinting (Cloudflare, Akamai, Datadome)

### a) TLS Fingerprinting (JA3 / JA4)
Các thư viện Python tiêu chuẩn như `requests` hoặc `urllib3` sử dụng OpenSSL với bộ Cipher Suites và TLS Extensions cố định, hoàn toàn khác với trình duyệt thật:
- WAF chặn ngay lập tức với mã HTTP 403 Forbidden.
- **Giải pháp:** Sử dụng thư viện `curl_cffi`:
  ```python
  from curl_cffi import requests
  # Giả lập hoàn hảo TLS fingerprint của Chrome 124 trên Windows
  resp = requests.get(url, impersonate="chrome124")
  ```

### b) HTTP/2 Fingerprinting
Kiểm tra các thông số SETTINGS frame, WINDOW_UPDATE frame, thứ tự header `:method`, `:authority`, `:scheme`, `:path`.
`curl_cffi` mô phỏng chính xác khung HTTP/2 của trình duyệt thật.

### c) Trình duyệt không đầu (Headless Detection)
Khi chạy Chrome ở chế độ tự động hóa:
- Cờ `navigator.webdriver` mặc định là `true`.
- Plugin `navigator.plugins` rỗng (`length === 0`).
- User-Agent chứa chuỗi `HeadlessChrome`.
- **Giải pháp:**
  - Khởi chạy với `--headless=new` (chế độ Headless thế hệ mới của Chromium mô phỏng giống hệt chế độ có UI).
  - Thêm cờ `--disable-blink-features=AutomationControlled`.
  - Inject script xóa `navigator.webdriver`.
