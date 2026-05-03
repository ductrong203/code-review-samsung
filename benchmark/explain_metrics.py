"""
Giải thích chi tiết cách tính Precision và Recall
"""
import json

# Load ground truth dataset
with open('dataset/positive_samples.json', encoding='utf-8') as f:
    data = json.load(f)

# Load evaluation results
with open('output/results/evaluation_results.json', encoding='utf-8') as f:
    results = json.load(f)

print("=" * 80)
print("GIẢI THÍCH CHI TIẾT: PRECISION VÀ RECALL")
print("=" * 80)
print()

# 1. Công thức cơ bản
print("1️⃣  CÔNG THỨC CƠ BẢN")
print("-" * 80)
print()
print("Precision = Số comment ĐÚNG sinh ra / Tổng số comment sinh ra")
print("  → Đáp: 'Trong những gì LLM nói, % nào là chính xác?'")
print()
print("Recall = Số comment ĐÚNG sinh ra / Tổng số comment trong ground truth")
print("  → Đáp: 'LLM tìm được % nào của tất cả issues đúng?'")
print()
print()

# 2. Ví dụ cụ thể
print("2️⃣  VÍ DỤ CỤ THỂ - CHO MỘT PR")
print("-" * 80)
print()

# Find a PR with good examples
example_result = None
for r in results['details']:
    if 'error' not in r and r.get('total_generated_nums', 0) > 0:
        example_result = r
        break

if example_result:
    pr_url = example_result['github_pr_url']
    print(f"PR: {pr_url}")
    print()
    print("Tình huống:")
    print(f"  • LLM sinh ra: {example_result['total_generated_nums']} comments")
    print(f"  • Ground truth có: {example_result['positive_expected_nums']} comments")
    print(f"  • Comments khớp (line): {example_result['positive_line_match_nums']}")
    print(f"  • Comments khớp (semantic): {example_result['positive_match_nums']}")
    print()
    
    gen = example_result['total_generated_nums']
    ref = example_result['positive_expected_nums']
    line_match = example_result['positive_line_match_nums']
    sem_match = example_result['positive_match_nums']
    
    print("Tính toán:")
    print()
    print("  Line Precision = Số comment khớp vị trí dòng / Tổng sinh ra")
    print(f"                 = {line_match} / {gen}")
    print(f"                 = {line_match/gen*100:.1f}%")
    print(f"    Ý nghĩa: Trong {gen} comment LLM nói, {line_match} cái nó nói đúng vị trí dòng")
    print()
    
    print("  Line Recall = Số comment khớp vị trí dòng / Tổng ground truth")
    print(f"              = {line_match} / {ref}")
    print(f"              = {line_match/ref*100:.1f}%")
    print(f"    Ý nghĩa: Ground truth có {ref} issues, LLM tìm được {line_match} cái")
    print()
    
    if sem_match > 0:
        print("  Semantic Precision = Số comment khớp ý nghĩa / Tổng sinh ra")
        print(f"                     = {sem_match} / {gen}")
        print(f"                     = {sem_match/gen*100:.1f}%")
        print()
        
        print("  Semantic Recall = Số comment khớp ý nghĩa / Tổng ground truth")
        print(f"                  = {sem_match} / {ref}")
        print(f"                  = {sem_match/ref*100:.1f}%")
print()
print()

# 3. Tổng thể
print("3️⃣  TỔNG THỂ (177 PRs)")
print("-" * 80)
print()

total_gen = results['total_generated_comments']
total_ref = results['total_reference_comments']
total_line_match = results['total_line_matches']
total_sem_match = results['total_semantic_matches']

print(f"Tổng cộng:")
print(f"  • LLM sinh ra: {total_gen} comments")
print(f"  • Ground truth có: {total_ref} comments")
print(f"  • Khớp vị trí dòng: {total_line_match}")
print(f"  • Khớp ý nghĩa: {total_sem_match}")
print()

print("Tính toán:")
print()
print(f"  Line Precision = {total_line_match} / {total_gen}")
print(f"                 = {total_line_match/total_gen*100:.2f}%")
print(f"    Ý: {total_line_match/total_gen*100:.2f}% comment LLM sinh ra có vị trí dòng ĐÚNG")
print()

print(f"  Line Recall = {total_line_match} / {total_ref}")
print(f"              = {total_line_match/total_ref*100:.2f}%")
print(f"    Ý: LLM tìm được {total_line_match/total_ref*100:.2f}% tất cả {total_ref} issues đúng")
print()

print(f"  Semantic Precision = {total_sem_match} / {total_gen}")
print(f"                     = {total_sem_match/total_gen*100:.2f}%")
print()

print(f"  Semantic Recall = {total_sem_match} / {total_ref}")
print(f"                  = {total_sem_match/total_ref*100:.2f}%")
print()
print()

# 4. Giải thích ý nghĩa
print("4️⃣  GIẢI THÍCH Ý NGHĨA")
print("-" * 80)
print()

print("⚖️  PRECISION cao")
print("   → LLM sinh ra comments chất lượng cao")
print("   → Ít sai lệch, ít false positive")
print("   → Người dùng tin tưởng vào suggestions")
print()

print("⚖️  PRECISION thấp")
print("   → LLM sinh ra nhiều comments SAI")
print("   → Phí thời gian review cái không cần")
print("   → Cần sửa prompt để LLM khắt khe hơn")
print()

print("🔍 RECALL cao")
print("   → LLM tìm được NHIỀU issues")
print("   → Không bỏ sót gì")
print("   → Bao phủ toàn bộ nhưng có thể tạo noise")
print()

print("🔍 RECALL thấp")
print("   → LLM bỏ lỡ NHIỀU issues")
print("   → Chỉ tìm được 1 số nhỏ")
print("   → Cần cải thiện để tìm nhiều hơn")
print()
print()

# 5. Trade-off
print("5️⃣  PRECISION vs RECALL (Trade-off)")
print("-" * 80)
print()

print("📊 Tình huống đơn giản:")
print()
print("  PR có 10 issues thực sự")
print()
print("  Chiến lược 1: LLM rất cẩn thận")
print("    → Sinh ra 4 comments")
print("    → Tất cả 4 cái đều ĐÚNG")
print("    → Precision: 4/4 = 100% ✓✓✓")
print("    → Recall: 4/10 = 40% ✗ (bỏ lỡ 6 issues)")
print()
print("  Chiến lược 2: LLM hòa lẫn")
print("    → Sinh ra 12 comments")
print("    → 8 cái ĐÚNG, 4 cái SAI")
print("    → Precision: 8/12 = 67% ✓")
print("    → Recall: 8/10 = 80% ✓✓ (tìm được 8 issues)")
print()
print("  Chiến lược 3: LLM siêu tích cực")
print("    → Sinh ra 20 comments")
print("    → 9 cái ĐÚNG, 11 cái SAI")
print("    → Precision: 9/20 = 45% ✗ (nhiều noise)")
print("    → Recall: 9/10 = 90% ✓✓✓ (tìm được hầu hết)")
print()

print("💡 Mục tiêu: Cân bằng giữa Precision và Recall!")
print()
