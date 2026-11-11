# JavaScript Deobfuscation & AST Analysis Guide

Tài liệu chuyên sâu về các kỹ thuật bóc tách và giải mã mã nguồn JavaScript bị làm rối (obfuscated) phổ biến trong các ứng dụng web hiện đại.

---

## 1. Cấu trúc của JavaScript-Obfuscator (Obfuscator.io)

JavaScript-Obfuscator là công cụ làm rối JS phổ biến nhất trên web. Nó bao gồm 4 thành phần đặc trưng:

### a) Mảng chuỗi ký tự (String Array)
Toàn bộ chuỗi (tên biến, URL, API endpoint, thuật toán mã hóa) được trích xuất ra một mảng duy nhất ở đầu tệp:
```javascript
var _0x1a2b = ['log', 'Hello\x20World', 'API_KEY_SECRET', 'post', 'https://api.site.com'];
```

### b) Vòng xoay mảng (Array Rotation / Shuffle)
Một hàm tự thực thi (IIFE) dùng vòng lặp while để xoay chuyển thứ tự các phần tử trong mảng cho đến khi tổng modulo thỏa mãn một giá trị magic number:
```javascript
(function(_0xarr, _0xnum) {
    var _0xrot = function(_0xtarget) {
        while (--_0xtarget) {
            _0xarr['push'](_0xarr['shift']());
        }
    };
    _0xrot(++_0xnum);
}(_0x1a2b, 0x1bf));
```

### c) Hàm giải mã (String Decoder Function)
Hàm nhận chỉ mục (index) hoặc khóa giải mã, tính offset và lấy giá trị chuỗi thực sự:
```javascript
function _0xfunc(_0xidx, _0xkey) {
    _0xidx = _0xidx - 0x0;
    var _0xval = _0x1a2b[_0xidx];
    return _0xval;
}
```

### d) Làm phẳng luồng điều khiển (Control Flow Flattening)
Các khối lệnh logic tuần tự bị băm nhỏ và nhét vào một câu lệnh `switch(case)` bên trong vòng lặp `while(true)` với chuỗi thứ tự chạy ngẫu nhiên:
```javascript
var _0xorder = '3|1|0|2'.split('|'), _0xstep = 0;
while (true) {
    switch (_0xorder[_0xstep++]) {
        case '0': doSecondAction(); continue;
        case '1': doFirstAction(); continue;
        case '2': break;
        case '3': init(); continue;
    }
    break;
}
```

---

## 2. Phương pháp giải mã tự động bằng Abstract Syntax Tree (AST)

AST biểu diễn mã nguồn dưới dạng cây cú pháp. Thông qua Babel (`@babel/parser`, `@babel/traverse`, `@babel/generator`), ta có thể:

### Bước 1: Parse code thành AST
```javascript
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const generate = require('@babel/generator').default;
const t = require('@babel/types');

const ast = parser.parse(sourceCode, { sourceType: 'module' });
```

### Bước 2: Thay thế hàm giải mã bằng chuỗi tường minh
Duyệt qua tất cả các `CallExpression` có tên hàm trùng với hàm giải mã `_0xfunc`:
```javascript
traverse(ast, {
    CallExpression(path) {
        if (path.node.callee.name === '_0xfunc') {
            const args = path.node.arguments.map(arg => arg.value);
            const plainString = executeDecoderInSandbox(args);
            path.replaceWith(t.stringLiteral(plainString));
        }
    }
});
```

### Bước 3: Unflatten luồng điều khiển
1. Tìm các biến chứa chuỗi thứ tự (ví dụ `'3|1|0|2'.split('|')`).
2. Tách từng case trong switch block thành mảng các Node AST câu lệnh.
3. Sắp xếp lại các Node theo đúng thứ tự chuỗi.
4. Thay thế toàn bộ vòng lặp while-switch bằng danh sách các câu lệnh tuần tự.

---

## 3. Webpack Chunk & Module Unpacking

Khi ứng dụng web sử dụng Webpack, code thường được bọc trong hàm tự gọi hoặc mảng chunks:

```javascript
(self.webpackChunkmy_app = self.webpackChunkmy_app || []).push([
    [742],
    {
        1423: function(module, exports, __webpack_require__) {
            // Module code
        },
        5912: function(module, exports, __webpack_require__) {
            // Module code
        }
    }
]);
```

### Cách bóc tách:
1. Dùng script `scripts/deobfuscate.cjs --unpack-webpack target.js`.
2. Trích xuất từng module thành các file độc lập trong thư mục `webpack_modules/module_<id>.js`.
3. Tìm kiếm module quan trọng qua các từ khóa:
   - `crypto`, `aes`, `md5`, `sha256`, `hmac`
   - `axios`, `request`, `fetch`
   - `baseURL`, `headers`, `sign`, `token`

---

## 4. Khôi phục từ Source Map (.map)

Nếu server web chưa tắt Source Map trên môi trường Production:
1. Tìm đường dẫn file `.map` (thường là `<filename>.js.map`).
2. Tải file `.map` về. File này là định dạng JSON chứa:
   - `sources`: danh sách đường dẫn file gốc ban đầu.
   - `sourcesContent`: toàn bộ nội dung mã nguồn gốc chưa qua minify/obfuscate!
3. Dùng công cụ giải nén:
   ```bash
   npx source-map-unpack path/to/bundle.js.map ./restored_src
   ```
   Toàn bộ project gốc bao gồm chú thích, tên hàm, cấu trúc thư mục sẽ được phục hồi 100%.
