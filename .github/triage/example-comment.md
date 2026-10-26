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
| Reproduction clues | SQL or numbered steps found; reproduction still needs verification |
| Key errors | ERROR: cache lookup failed for relation 12345 |

Information to provide or verify:

- No missing required information identified.

### 3. Similar issues

- [#80](https://github.com/fixture/repository/issues/80) Logical replication crash on subscription refresh (closed; related issue; text similarity 0.681)
  Shared terms: subscription, refresh, during, logical, replication

### 4. Label changes

- Add: `ai-model/org-model-a-v2`, `area/logical-replication`, `needs-triage`, `type/bug`
- Remove bot-managed labels: —

### 5. Triage notes

- Analysis method: Not enabled; using rules and Chinese/English text similarity.
- No additional notes.

Declare the model name/version in the `AI model` field or an author comment. Separate multiple models with commas or newlines; explicitly write `not used` if no AI was used.
Maintainers can use `triage/accepted` after triage, or `resolution/duplicate` after confirming and linking the original issue. Maintainers review all triage conclusions.

<!-- triage-state:eyJtYW5hZ2VkIjogWyJhaS1tb2RlbC9vcmctbW9kZWwtYS12MiIsICJhcmVhL2xvZ2ljYWwtcmVwbGljYXRpb24iLCAibmVlZHMtdHJpYWdlIiwgInR5cGUvYnVnIl0sICJzdXBwcmVzc2VkIjogW119 -->
