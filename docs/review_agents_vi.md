# Hệ Thống 4 Review Agent

Tài liệu này mô tả vai trò của 4 agent trong hệ thống review code, nhóm lỗi mỗi
agent phụ trách, và ví dụ cụ thể để trình bày trong báo cáo.

## Tổng Quan

Hệ thống chia nhiệm vụ review thành 4 agent chuyên biệt:

| Agent | Mục tiêu |
| --- | --- |
| Defect Agent | Tìm lỗi chức năng, logic sai, crash, edge case. |
| Security Agent | Tìm lỗ hổng bảo mật và dữ liệu nhạy cảm bị lộ. |
| Performance Agent | Tìm vấn đề hiệu năng, tài nguyên và khả năng scale. |
| Maintainability Agent | Tìm vấn đề dễ đọc, dễ sửa, thiết kế và testability. |

Việc tách agent giúp mỗi agent có checklist riêng, tập trung vào một loại rủi
ro, giảm bỏ sót lỗi và làm kết quả review rõ ràng hơn.

## Defect Agent

Defect Agent tập trung vào lỗi khiến chương trình chạy sai, crash, trả kết quả
sai hoặc xử lý thiếu tình huống.

Các lỗi thường bắt:

- Sai điều kiện logic: dùng `&&` thay vì `||`, đảo ngược điều kiện.
- Lỗi null/undefined: truy cập property khi object có thể null.
- Sai kiểu dữ liệu: nhầm string/number, ép kiểu sai.
- Lỗi control flow: thiếu `return`, thiếu `break`, code unreachable.
- Lỗi boundary: off-by-one, không xử lý list rỗng.
- Race condition hoặc state bị cập nhật sai.

Ví dụ:

```js
if (user.role !== "admin" || user.role !== "owner") {
  denyAccess();
}
```

Điều kiện này luôn đúng. Nếu `user.role` là `admin`, vế
`user.role !== "owner"` vẫn đúng. Nếu `user.role` là `owner`, vế
`user.role !== "admin"` vẫn đúng.

Fix đúng hơn:

```js
if (user.role !== "admin" && user.role !== "owner") {
  denyAccess();
}
```

Ví dụ edge case:

```python
def average(numbers):
    return sum(numbers) / len(numbers)
```

Nếu `numbers` là list rỗng, code sẽ chia cho 0. Defect Agent bắt lỗi này vì nó
có thể gây crash.

## Security Agent

Security Agent tập trung vào lỗi có thể bị khai thác bởi attacker hoặc làm lộ dữ
liệu nhạy cảm.

Các lỗi thường bắt:

- Thiếu kiểm tra quyền truy cập.
- SQL injection, command injection, XSS.
- Hardcoded secret, API key, password.
- Path traversal như `../../etc/passwd`.
- SSRF khi user điều khiển URL server request.
- Thiếu validate input.
- JWT/session xử lý sai.
- Log password, token hoặc PII.
- Debug mode, CORS hoặc security header cấu hình không an toàn.

Ví dụ SQL injection:

```python
query = f"SELECT * FROM users WHERE email = '{email}'"
db.execute(query)
```

Nếu `email` đến từ user input, attacker có thể truyền:

```text
a@example.com' OR '1'='1
```

Fix an toàn hơn là dùng parameterized query:

```python
db.execute("SELECT * FROM users WHERE email = ?", [email])
```

Ví dụ lộ dữ liệu nhạy cảm:

```js
console.log("login token:", token);
```

Token bị ghi vào log. Nếu log bị truy cập, attacker có thể chiếm session.

## Performance Agent

Performance Agent tập trung vào code chạy chậm, tốn tài nguyên, leak memory hoặc
không scale khi dữ liệu lớn.

Các lỗi thường bắt:

- Thuật toán `O(n^2)` hoặc tệ hơn khi có cách tốt hơn.
- Query trong vòng lặp gây N+1 query.
- Không đóng file, database connection hoặc network resource.
- Memory leak: event listener, timer, goroutine/thread không cleanup.
- Gọi API lặp lại thay vì batch.
- Compile regex trong loop.
- Tính toán lại nhiều lần thay vì cache.
- Không phân trang khi query dữ liệu lớn.

Ví dụ N+1 query:

```python
for user in users:
    orders = db.query("SELECT * FROM orders WHERE user_id = ?", user.id)
    user.orders = orders
```

Nếu có 1.000 users, code chạy 1.000 query. Performance Agent sẽ gợi ý batch
query:

```python
user_ids = [user.id for user in users]
orders = db.query("SELECT * FROM orders WHERE user_id IN (?)", user_ids)
```

Ví dụ computation dư thừa:

```js
for (const item of items) {
  const regex = new RegExp(pattern);
  if (regex.test(item.name)) {
    result.push(item);
  }
}
```

Regex được compile lại ở mỗi vòng lặp. Nên đưa `new RegExp(pattern)` ra ngoài
loop.

## Maintainability Agent

Maintainability Agent tập trung vào chất lượng code dài hạn: code có dễ đọc, dễ
sửa, dễ test và dễ mở rộng không.

Các lỗi thường bắt:

- Vi phạm SOLID.
- Function/class làm quá nhiều việc.
- Code duplicate.
- Tên biến/hàm mơ hồ hoặc gây hiểu nhầm.
- Magic number không giải thích.
- Error handling kém: catch rỗng, catch quá rộng.
- Function quá dài, nesting sâu.
- Quá nhiều parameter.
- Tight coupling, khó test.
- Comment sai hoặc thiếu với logic phức tạp.

Ví dụ quá nhiều tham số:

```python
def process(data, mode, flag, type, retry, timeout, debug):
    ...
```

Hàm này khó hiểu và dễ gọi sai thứ tự tham số. Maintainability Agent có thể gợi
ý gom cấu hình vào object hoặc tách hàm theo responsibility.

Ví dụ code duplicate:

```js
function validateAdmin(user) {
  if (!user.email) throw new Error("Missing email");
  if (!user.name) throw new Error("Missing name");
}

function validateCustomer(user) {
  if (!user.email) throw new Error("Missing email");
  if (!user.name) throw new Error("Missing name");
}
```

Hai function lặp logic giống nhau. Agent có thể gợi ý tách helper chung.

Ví dụ error handling kém:

```java
try {
    uploadFile(file);
} catch (Exception e) {
}
```

Exception bị nuốt hoàn toàn, khiến lỗi upload rất khó debug.

## Cách Trình Bày Ngắn Gọn

Hệ thống sử dụng 4 agent chuyên biệt, mỗi agent tập trung vào một nhóm lỗi khác
nhau. Defect Agent tìm lỗi chức năng như sai điều kiện, null pointer và edge
case. Security Agent tìm lỗ hổng bảo mật như injection, auth bypass và lộ
secret. Performance Agent tìm vấn đề hiệu năng như N+1 query, vòng lặp `O(n^2)`
và leak tài nguyên. Maintainability Agent tìm vấn đề chất lượng code như
duplicate, naming kém, function quá dài, coupling cao và khó test.
