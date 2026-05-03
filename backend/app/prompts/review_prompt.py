"""
Review Prompt Template — Human message template for code review requests.
"""

REVIEW_PROMPT_TEMPLATE = """Please review the following Pull Request changes.

## PR Information
- **Title**: {title}
- **Description**: {description}

## Code Diff
The following diff shows the changes made in this PR. Lines prefixed with `+` are additions, `-` are deletions, and unmarked lines are context. Line numbers are shown on the left.

{diff_content}

---

Please analyze the code changes above and provide your review comments. Focus on meaningful issues (bugs, security, performance, maintainability). Use the exact file paths and line numbers from the diff.
"""
