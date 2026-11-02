<!-- ivorysql-issue-triage:v1 -->
## Issue triage

### 1. Classification and labels

| Dimension | Proposed result (preserving manual labels) | Automated suggestion |
| --- | --- | --- |
| Type | `type/bug` | `type/bug` |
| Area | `area/logical-replication` | `area/logical-replication` |
| Reported AI model | `ai-model/org-model-a-v2` | `ai-model/org-model-a-v2` |
| Triage stage | `needs-triage` | Maintainer acceptance required |

Evidence:

- `type/bug` (rule): Bug
- `area/logical-replication` (rule): logical replication
- `ai-model/org-model-a-v2` (reporter declaration): org/model-a-v2

### 2. Information completeness

Check result: Required-field checks passed; maintainer review is still needed

| Field | Extracted value |
| --- | --- |
| Database version | 18.1 |
| Platform | linux |
| Reporter's declared AI model | org/model-a-v2 |
| Reproduction clues | Reproduction instructions or code found; reproduction still needs verification |
| Expected behavior | Subscription refresh completes without a crash. |
| Compatible mode | pg |
| Server encoding | UTF8 |
| Key errors | ERROR: cache lookup failed for relation 12345 |

Information to provide or verify:

- No missing required information identified.

**Submission check passed.** Thank you for providing the required information. A maintainer still needs to review the report.

### 3. Similar issues

- [#80](https://github.com/fixture/repository/issues/80) Logical replication crash on subscription refresh (closed; related issue; text similarity 0.674)
  Shared terms: subscription, refresh, during, logical, replication

### 4. Label changes

- Add: `ai-model/org-model-a-v2`, `area/logical-replication`, `needs-triage`, `type/bug`
- Remove bot-managed labels: —

### 5. Triage notes

- Analysis method: Not enabled; using rules and Chinese/English text similarity.
- No additional notes.

Maintainers can use `triage/accepted` after triage, or `resolution/duplicate` after confirming and linking the original issue. Maintainers review all triage conclusions.

<!-- triage-state:eyJmaWVsZF9oaXN0b3J5IjogeyJib2R5IjogeyJBSSBtb2RlbCI6IHsidXBkYXRlZF9hdCI6IG51bGwsICJ2YWx1ZV9zaGEyNTYiOiAiNjM2NzRiZTVjOTQ1MGM3ZmM3ZDBjYzNlMjg3ZWE3NzZhY2M0ZDVlNDY3NDQ1MWNjMGNlYjA3NDZkZjA1YmE2ZCJ9LCAiQ29tcGF0aWJsZSBtb2RlIjogeyJ1cGRhdGVkX2F0IjogbnVsbCwgInZhbHVlX3NoYTI1NiI6ICIxYmJiNTQwYzlmYjQwNThlYjhiZjU0OWI0ODMyODgyMWUyYzA3ZjUwMDRhNmEyMjQ3YmFlMzA1YjYyYmJiNGU2In0sICJFeHBlY3RlZCBiZWhhdmlvciI6IHsidXBkYXRlZF9hdCI6IG51bGwsICJ2YWx1ZV9zaGEyNTYiOiAiMjg0N2RiNGJmZjFkZThkMjgzZWVmOTJlZjliMWNkY2VlNWY1Y2MzODQwNjMyODliNGNjOWU1MTA2ZDVjMjk1NCJ9LCAiU2VydmVyIGVuY29kaW5nIjogeyJ1cGRhdGVkX2F0IjogbnVsbCwgInZhbHVlX3NoYTI1NiI6ICI3YmU2ZGUwOWEzNmI3MmRiN2YzZmE5N2ZkM2VkZjBhNWIwZDc3ZWRiZWEyM2NmODE0MGM1MmNhZTU5N2VlMGM3In19fSwgImZpZWxkX3NvdXJjZXMiOiB7IkFJIG1vZGVsIjogeyJzb3VyY2UiOiAiYm9keSIsICJ1cGRhdGVkX2F0IjogbnVsbCwgInZhbHVlX3NoYTI1NiI6ICI2MzY3NGJlNWM5NDUwYzdmYzdkMGNjM2UyODdlYTc3NmFjYzRkNWU0Njc0NDUxY2MwY2ViMDc0NmRmMDViYTZkIn0sICJDb21wYXRpYmxlIG1vZGUiOiB7InNvdXJjZSI6ICJib2R5IiwgInVwZGF0ZWRfYXQiOiBudWxsLCAidmFsdWVfc2hhMjU2IjogIjFiYmI1NDBjOWZiNDA1OGViOGJmNTQ5YjQ4MzI4ODIxZTJjMDdmNTAwNGE2YTIyNDdiYWUzMDViNjJiYmI0ZTYifSwgIkV4cGVjdGVkIGJlaGF2aW9yIjogeyJzb3VyY2UiOiAiYm9keSIsICJ1cGRhdGVkX2F0IjogbnVsbCwgInZhbHVlX3NoYTI1NiI6ICIyODQ3ZGI0YmZmMWRlOGQyODNlZWY5MmVmOWIxY2RjZWU1ZjVjYzM4NDA2MzI4OWI0Y2M5ZTUxMDZkNWMyOTU0In0sICJTZXJ2ZXIgZW5jb2RpbmciOiB7InNvdXJjZSI6ICJib2R5IiwgInVwZGF0ZWRfYXQiOiBudWxsLCAidmFsdWVfc2hhMjU2IjogIjdiZTZkZTA5YTM2YjcyZGI3ZjNmYTk3ZmQzZWRmMGE1YjBkNzdlZGJlYTIzY2Y4MTQwYzUyY2FlNTk3ZWUwYzcifX0sICJpbnB1dF9zaGEyNTYiOiAiNmViN2MyZDNjNTcxZjgwMDg0MTg4YjcyMTZiYzE0MTZhY2VkMDBiNmYyNjQ5ZjE4MWJiODJiNjAyZTg5MDllOCIsICJtYW5hZ2VkIjogWyJhaS1tb2RlbC9vcmctbW9kZWwtYS12MiIsICJhcmVhL2xvZ2ljYWwtcmVwbGljYXRpb24iLCAibmVlZHMtdHJpYWdlIiwgInR5cGUvYnVnIl0sICJyZXZpZXdfc3RhdHVzIjogImNvbXBsZXRlIiwgInNvdXJjZV93YXRlcm1hcmsiOiB7ImxhdGVzdF9jb21tZW50X2lkIjogMCwgImxhdGVzdF91cGRhdGVfYXQiOiBudWxsfSwgInN1cHByZXNzZWQiOiBbXX0= -->
