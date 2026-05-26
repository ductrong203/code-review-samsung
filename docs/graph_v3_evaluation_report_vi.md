# Báo cáo đánh giá Graph v3 và Graph v3 Qwen36

## Nguồn dữ liệu

Báo cáo này tổng hợp kết quả từ hai file:

- `benchmark/output/results/graph_v3/evaluation_results.json`
- `benchmark/output/results/graph_v3_qwen36/evaluation_results.json`

F1-score được tính theo công thức:

```text
F1 = 2 * precision * recall / (precision + recall)
```

## Bảng kết quả

| Phiên bản | Generated comments | Reference comments | Line precision | Line recall | Line F1 | Semantic precision | Semantic recall | Semantic F1 | Noise rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| graph_v3 | 1136 | 1416 | 0.3187 | 0.2556 | 0.2837 | 0.2210 | 0.1773 | 0.1968 | 0.7790 |
| graph_v3_qwen36 | 1960 | 1398 | 0.2316 | 0.3247 | 0.2704 | 0.1719 | 0.2411 | 0.2007 | 0.8281 |

## Nhận xét kết quả

`graph_v3` sinh ít comment hơn `graph_v3_qwen36` nhưng có precision cao hơn. Điều này cho thấy phiên bản này thận trọng hơn khi đưa ra nhận xét: số lượng comment ít hơn, tỉ lệ comment đúng theo line và semantic tốt hơn, nhưng lại bỏ sót nhiều vấn đề hơn so với ground truth. Vì vậy recall của `graph_v3` thấp hơn.

`graph_v3_qwen36` sinh nhiều comment hơn đáng kể, từ 1136 lên 1960 comment. Nhờ vậy, hệ thống bắt được nhiều match hơn: line matches tăng từ 362 lên 454, semantic matches tăng từ 251 lên 337. Recall cũng tăng rõ rệt, đặc biệt semantic recall tăng từ 0.1773 lên 0.2411. Tuy nhiên, số comment dư cũng tăng mạnh, làm precision giảm và noise rate tăng từ 0.7790 lên 0.8281.

Kết quả này phản ánh sự đánh đổi giữa coverage và chất lượng lọc. Khi mô hình sinh nhiều nhận xét hơn, khả năng chạm tới các lỗi trong ground truth tăng lên, nhưng đồng thời hệ thống cũng tạo thêm nhiều comment không khớp với ground truth. Vì vậy `graph_v3_qwen36` có semantic F1 nhỉnh hơn một chút so với `graph_v3`, nhưng line F1 lại thấp hơn.

## Điểm mạnh

- Graph context giúp hệ thống mở rộng phạm vi phân tích ra ngoài từng đoạn code cục bộ, từ đó phát hiện thêm các vấn đề liên quan đến dependency, caller, callee, test, function và file liên quan.
- `graph_v3_qwen36` có khả năng bao phủ tốt hơn, thể hiện qua recall và số lượng match cao hơn.
- Semantic F1 của `graph_v3_qwen36` cao hơn nhẹ, cho thấy việc sinh nhiều comment hơn vẫn mang lại thêm giá trị ở mức ý nghĩa nội dung, không chỉ ở số lượng.
- `graph_v3` có precision tốt hơn, phù hợp hơn khi cần giảm số lượng false positive trong review.

## Điểm yếu

- Noise rate của cả hai phiên bản đều cao. Điều này cho thấy phần lớn comment sinh ra chưa khớp với ground truth.
- Semantic precision còn thấp, nghĩa là nhiều comment có vẻ hợp lý nhưng chưa đúng với vấn đề mà ground truth kỳ vọng.
- Line localization chưa tốt. Hệ thống có thể phát hiện đúng khu vực hoặc vấn đề liên quan, nhưng chưa đặt comment đúng dòng cần review.
- `graph_v3_qwen36` bị over-generation: sinh nhiều comment hơn nhưng không tăng precision, làm người dùng phải đọc nhiều nhận xét nhiễu hơn.
- Graph context có thể mở rộng quá rộng, kéo vào nhiều node liên quan nhưng không thật sự cần thiết cho lỗi hiện tại.
- Chưa có cơ chế ranking, confidence threshold hoặc deduplication đủ mạnh để loại bỏ các comment yếu, trùng lặp hoặc chỉ mang tính suy đoán.

## Conclusion

Kết quả cho thấy hướng dùng graph context là có tiềm năng, đặc biệt trong việc tăng recall và phát hiện thêm các vấn đề liên quan đến ngữ cảnh liên file. `graph_v3_qwen36` chứng minh rằng khi hệ thống được mở rộng khả năng sinh và khai thác context, số lượng match với ground truth tăng lên đáng kể. Tuy nhiên, việc tăng số lượng comment không đồng nghĩa với chất lượng tổng thể tốt hơn, vì precision giảm và noise rate tăng.

So sánh hai phiên bản cho thấy `graph_v3` phù hợp hơn với mục tiêu review thận trọng, ít nhiễu hơn, còn `graph_v3_qwen36` phù hợp hơn với mục tiêu tăng coverage và không bỏ sót lỗi. Điểm quan trọng là hệ thống hiện tại chưa kiểm soát tốt chất lượng đầu ra sau khi sinh comment. Do đó, bottleneck chính không chỉ nằm ở khả năng tìm context, mà nằm ở bước chọn lọc, xếp hạng, định vị dòng và xác minh comment trước khi trả về cho người dùng.

Nhìn chung, hệ thống hiện tại đã có nền tảng tốt để khai thác graph-based code review, nhưng cần cải thiện mạnh ở khâu giảm nhiễu. Nếu không có cơ chế lọc tốt hơn, việc tăng sức mạnh mô hình hoặc tăng số lượng context có thể tiếp tục làm recall tăng nhưng precision giảm, khiến trải nghiệm review thực tế bị ảnh hưởng.

## Future Work

Trong các phiên bản tiếp theo, hệ thống nên bổ sung cơ chế ranking và confidence score cho từng comment. Comment có độ tin cậy thấp nên bị loại bỏ hoặc đưa xuống nhóm phụ, thay vì hiển thị ngang hàng với các comment có bằng chứng mạnh.

Cần cải thiện line localization bằng cách kết hợp diff hunk, AST span, function boundary và vị trí node trong graph. Mục tiêu là không chỉ phát hiện đúng vấn đề, mà còn đặt comment đúng dòng hoặc đúng block code mà reviewer cần sửa.

Hệ thống cũng nên giới hạn graph expansion theo loại cạnh và độ sâu. Ví dụ, các cạnh trực tiếp như function call, import, test coverage hoặc same-file relation nên có trọng số cao hơn các quan hệ gián tiếp. Điều này giúp giảm việc kéo vào quá nhiều ngữ cảnh không liên quan.

Một hướng quan trọng khác là thêm bước post-verification sau khi mô hình sinh comment. Bộ verifier có thể kiểm tra lại comment dựa trên code evidence, ground rule, vị trí dòng và mức độ cụ thể của vấn đề. Những comment chung chung, thiếu bằng chứng hoặc trùng lặp nên bị loại bỏ.

Ngoài ra, cần có cơ chế deduplication và grouping theo root cause. Nếu nhiều comment đang nói về cùng một vấn đề, hệ thống nên gộp lại thành một nhận xét rõ ràng hơn để giảm nhiễu cho người dùng.

Về đánh giá, nên phân tích thêm theo từng nhóm lỗi, từng loại file và từng loại node trong graph. Điều này giúp xác định hệ thống đang mạnh ở loại vấn đề nào và yếu ở đâu, thay vì chỉ nhìn vào precision, recall và F1 tổng thể.

Cuối cùng, nên tối ưu ngân sách sinh comment theo từng file. Với các file ít thay đổi hoặc ít rủi ro, hệ thống cần sinh ít comment hơn. Với các file trung tâm, có nhiều dependency hoặc có mức độ rủi ro cao, hệ thống có thể cho phép nhiều context hơn nhưng vẫn cần kiểm soát bằng threshold và verifier.
