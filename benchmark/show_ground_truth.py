import json

# Load ground truth dataset
with open('dataset/positive_samples.json', encoding='utf-8') as f:
    data = json.load(f)

# Show first example
pr = data[0]
print('=== GROUND TRUTH EXAMPLE (từ AACR-Bench dataset) ===')
print(f"PR: {pr['githubPrUrl']}")
print(f"Language: {pr['project_main_language']}")
print(f"Category: {pr['category']}")
print()
print(f"Total Reference Comments: {len(pr['comments'])}")
print()
print('First 2 reference comments:')
for i, c in enumerate(pr['comments'][:2], 1):
    print(f"{i}. Path: {c['path']}")
    print(f"   Lines: {c['from_line']}-{c['to_line']}")
    print(f"   Category: {c['category']}")
    print(f"   Note: {c['note'][:100]}...")
    print()
