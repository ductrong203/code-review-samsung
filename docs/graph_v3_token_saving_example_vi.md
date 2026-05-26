# Ví dụ đánh giá tiết kiệm token của Graph v3

## Mục tiêu

Tài liệu này lấy một PR cụ thể để so sánh lượng context nếu đưa toàn bộ `diff`, `file`, `repo` vào LLM so với cách Graph v3 đang dùng: `diff` của PR kết hợp với graph context gồm changed functions, related functions, test gaps và review priorities.

Ví dụ được chọn:

- PR: `https://github.com/langflow-ai/langflow/pull/6044`
- Repo local: `E:\My_Project\samsung\langflow`
- Source commit: `5bcf4d001f1174ed9e63b7115f10e5dbe1bcca9f`
- Target commit: `bcfe6f9ded091cd360b3212b6e9f5a58cbcdac5e`
- Số file changed: `44`
- Số changed line trong dataset: `882`

Token được ước lượng theo công thức gần đúng:

```text
approx_tokens = chars / 4
```

## Kết quả đo kích thước context

| Loại context | Kích thước chars | Token ước lượng | Ghi chú |
|---|---:|---:|---|
| Full PR diff | 267,988 | 66,997 | Toàn bộ diff giữa source và target commit |
| Full content của changed files | 1,227,668 | 306,917 | Nội dung đầy đủ của 43 file còn tồn tại sau PR |
| Full source repo | 14,986,124 | 3,746,531 | Các file source/text chính trong target commit |
| Full diff + full changed files + repo | 16,481,780 | 4,120,445 | Cách nhét toàn bộ context, rất tốn token |
| Graph v3 file context đã cap | 119,094 | 29,774 | Diff theo file đã bị cap/truncate, khoảng 6,000 chars/file trong `agent_base.py` |

Benchmark log của Graph v3 cho PR này:

| Graph item | Số lượng |
|---|---:|
| Changed functions | 12 |
| Test gaps | 10 |
| Review priorities | 5 |
| Related context | 8 |
| Overall risk | 0.5 |

Graph context trong prompt hiện tại là dạng summary ngắn, ví dụ:

```text
- Changed `function_name` [file.py:line_start-line_end] risk=... untested=...
  callers: [...]
  callees: [...]
  tests: [...]
Related repo context: [...]
Review priorities: [...]
```

Vì vậy graph context thường chỉ thêm khoảng vài nghìn token, thay vì phải đưa nguyên file hoặc nguyên repo.

## So sánh mức tiết kiệm token

Lưu ý quan trọng: Graph v3 trong pipeline hiện tại không đưa toàn bộ full diff vào prompt. Backend dựng `file_context` từ diff theo từng file và cap khoảng `6,000 chars/file`, đồng thời graph context chỉ là summary ngắn về changed functions, callers, callees, tests, test gaps và review priorities.

Vì vậy con số `~31k token` bên dưới là **capped diff + graph summary**, không phải **full diff + graph summary**. Nếu thật sự đưa full diff rồi cộng thêm graph context, tổng token chắc chắn sẽ lớn hơn `66,997 token`.

| Baseline so sánh | Token baseline | Token Graph v3 ước lượng | Tiết kiệm |
|---|---:|---:|---:|
| Full raw diff | 66,997 | ~31,000 | ~53.7% |
| Full diff + full changed files | 373,914 | ~31,000 | ~91.7% |
| Full diff + full changed files + repo | 4,120,445 | ~31,000 | ~99.2% |

Cách diễn đạt chính xác hơn:

```text
Graph v3 ~= capped diff + selected graph context
Không phải Graph v3 = full diff + full graph/repo context
```

## Ý nghĩa của Graph v3

Nếu chỉ dùng diff, hệ thống tiết kiệm token nhưng thiếu ngữ cảnh để hiểu ảnh hưởng của thay đổi tới caller, callee, test và các luồng liên quan. Điều này làm model dễ bỏ sót lỗi cần file-level hoặc repo-level context.

Nếu đưa toàn bộ file hoặc toàn bộ repo vào prompt, model có nhiều thông tin hơn nhưng chi phí token tăng rất lớn. Với PR `langflow#6044`, việc đưa full repo có thể lên tới hơn `4.1M token`, vượt xa giới hạn context của nhiều model và gây lãng phí vì phần lớn repo không liên quan trực tiếp đến thay đổi.

Graph v3 nằm ở giữa hai hướng trên. Hệ thống vẫn giữ diff làm nguồn chính để anchor comment vào changed lines, nhưng chỉ bổ sung các node liên quan như changed functions, callers, callees, tests và related context. Nhờ đó model có thêm ngữ cảnh repo-level có chọn lọc mà không cần đọc toàn bộ repo.

## Kết luận

Trong ví dụ PR `langflow#6044`, Graph v3 giúp giảm lượng context từ mức hàng trăm nghìn hoặc hàng triệu token xuống còn khoảng vài chục nghìn token. So với phương án đưa full diff + full changed files + full repo, mức tiết kiệm token ước lượng khoảng `99.2%`.

Điểm quan trọng là Graph v3 không chỉ cắt bớt token một cách cơ học. Nó thay thế full repo context bằng context có cấu trúc: changed functions, related functions, test gaps và review priorities. Cách này giúp model tập trung vào phần code có khả năng ảnh hưởng trực tiếp tới review, thay vì bị nhiễu bởi toàn bộ repository.

Tuy nhiên, Graph v3 vẫn phụ thuộc vào chất lượng graph extraction và ranking. Nếu graph bỏ sót related function quan trọng hoặc chọn nhầm node ít liên quan, model vẫn có thể thiếu context. Vì vậy, hướng cải thiện tiếp theo nên tập trung vào ranking node tốt hơn, giới hạn edge theo loại quan hệ, và thêm confidence score cho từng related context item.
