$marker
## Issue triage

### 1. Classification and labels

| Dimension | Proposed result (preserving manual labels) | Automated suggestion |
| --- | --- | --- |
$classification

Evidence:

$evidence

### 2. Information completeness

Check result: $information_status

| Field | Extracted value |
| --- | --- |
| Database version | $versions |
| Platform | $platforms |
| Reporter's declared AI model | $reported_models |
| Reproduction clues | $reproduction |
| Expected behavior | $expected_behavior |
| Compatible mode | $compatible_mode |
| Server encoding | $server_encoding |
| Key errors | $errors |

Information to provide or verify:

$missing

$submission_guidance

### 3. Similar issues

$similar

### 4. Label changes

- Add: $add_labels
- Remove bot-managed labels: $remove_labels

### 5. Triage notes

- Analysis method: $ai_status
$notes

Declare the model name/version in the `AI model` field or an author comment. Separate multiple models with commas or newlines; explicitly write `not used` if no AI was used.
Maintainers can use `triage/accepted` after triage, or `resolution/duplicate` after confirming and linking the original issue. Maintainers review all triage conclusions.

$state
