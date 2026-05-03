# Những Cải Tiến Của Hệ Thống Multi-Agent So Với Phiên Bản Single-LLM Cũ

Tài liệu này tóm tắt những điểm vượt trội của kiến trúc Multi-Agent hiện tại so với phương pháp sử dụng một prompt LLM nguyên bản (chỉ truyền toàn bộ code vào và yêu cầu LLM review).

## 1. Phân Chia Chuyên Môn Hóa (Specialization)

Thay vì dùng một cấu hình LLM duy nhất để vạch lá tìm sâu mọi thể loại lỗi, hệ thống mới chia nhỏ nhiệm vụ cho 4 đặc vụ (Agents) riêng biệt. Mỗi Agent được tùy chỉnh với một System Prompt tối ưu sâu cho lĩnh vực của nó.

**Các file liên quan:**

- `backend/app/agents/defect_agent.py`: Chuyên săn các lỗi logic, bug tiềm ẩn và edge cases.
- `backend/app/agents/security_agent.py`: Chuyên dò tìm các lỗ hổng bảo mật, rủi ro rò rỉ dữ liệu hoặc Injection.
- `backend/app/agents/performance_agent.py`: Tập trung vào bài toán tối ưu hóa tài nguyên (Memory, CPU) và tốc độ thực thi.
- `backend/app/agents/maintainability_agent.py`: Đánh giá cấu trúc code, Clean Code, và khả năng bảo trì.
- Được điều phối chung tại `backend/app/agents/orchestrator.py`.

## 2. Cơ Chế Đồng Thuận và Xử Lý Nhiễu (Consensus & Filtering)

Một nhược điểm lớn của LLM thuần là dễ bị "ảo giác" (hallucination) hoặc báo động giả (false positive). Hệ thống mới giải quyết triệt để vấn đề này thông qua cơ chế tổng hợp và chấm điểm.

- **Lọc nhiễu:** Các báo cáo sẽ bị loại bỏ nếu điểm tin cậy (`confidence_threshold`) thấp.
- **Chống trùng lặp:** Hợp nhất các phát hiện tương tự nhau từ nhiều agents (Deduplication).

**File liên quan:**

- `backend/app/agents/consensus.py` (Class `ConsensusEngine`)

## 3. Xây Dựng Ngữ Cảnh Chuyên Sâu (Intelligent Context Gathering)

Phiên bản cũ thường chỉ ném mã nguồn thô (raw diff) vào LLM, khiến LLM mất phương hướng. Hệ thống mới trích xuất ngữ cảnh phong phú (Rich ReviewContext) trước khi giao cho Agents phân tích. Nó biết đoạn code nằm ở đâu, phụ thuộc (dependency) vào những file nào, và giới hạn số lượng ký tự (`max_file_chars`) để tránh tràn token.

**Các file liên quan:**

- `backend/app/services/context_builder.py` (Class `ContextBuilder`)
- `backend/app/services/github_service.py`

## 4. Tăng Tốc Thông Qua Xử Lý Song Song (Parallel Execution)

Tuy sử dụng đến 4 Agents khác nhau để phân tích toàn diện, kiến trúc sử dụng `ThreadPoolExecutor` hoặc `asyncio` để cho phép các Agents phân tích **cùng lúc**. Điều này giúp tạo ra báo cáo chất lượng cao mà không bị phân mảnh thời gian chờ đợi.

**File liên quan:**

- `backend/app/agents/orchestrator.py` (cơ chế `parallel=True` trong hàm khởi tạo)

---

**Tóm lại:** Kiến trúc mới chuyển mình từ một "chatbot đọc mã" đơn thuần thành một **"hội đồng đánh giá mã (Code Review Pipeline) tự động"** với dữ liệu ngữ cảnh rõ ràng, được đối chiếu, chắt lọc kĩ càng và phân tích đa chiều.
