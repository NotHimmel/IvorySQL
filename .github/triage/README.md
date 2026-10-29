# Issue triage

Classify GitHub issues by type, PostgreSQL subsystem, and declared AI model;
check required information and suggest similar historical issues. Python 3.10+
and the standard library are sufficient. The default mode is preview.

## Scope and labels

Only issues are processed. A PR number in a manual range is reported as skipped
before comments, history, or AI are read; no PR labels or comments are changed.
Existing repository PR governance and CI workflows are independent of this tool.

[config.json](config.json) defines label descriptions, colors, matching rules,
thresholds, and limits:

- Types: `type/bug`, `type/feature`, `type/enhancement`; select at most one, or abstain.
  Regressions are bugs; features add capabilities; enhancements improve existing ones.
- Areas: at most two of the 20 `area/*` labels, mapped from PostgreSQL subsystems.
  These are repository labels based on PG documentation, not official PG issue labels.
- Models: `ai-model/*` records the model explicitly declared by the reporter.
  Every issue type requires a declaration, including an explicit `not used` if applicable.
- Stage: `needs-triage` is workflow-managed, including when added by a template.
  On the next triage run, acceptance (`triage/accepted`) or any `resolution/*`
  label removes it. Removing acceptance and resolution restores it for open
  issues on the next run. Automated classification does not imply acceptance.
- Information: `triage/needs-information` can coexist with acceptance. Missing model
  declarations, unknown issue types, empty descriptions, and incomplete bug reports
  produce a specific checklist. Releases, `master`/`main`,
  PostgreSQL stable branches, and explicit commit IDs count as version information.
  Reproduction fields can contain prose; SQL, shell commands, and numbered steps
  are also accepted clues. Environment scaffolding and log sections are excluded.
  These checks do not prove that reproduction succeeds.
- Resolutions: `resolution/duplicate`, `resolution/invalid`, `resolution/wontfix` are
  maintainer decisions. Confirmed duplicates should link to their original issue.
- `triage/skip` is manually applied by maintainers to exclude an issue from all
  triage runs, including manual runs. The bot never adds this label. Removing it
  allows processing on the next supported event or manual run.

Manual classification labels take precedence. Except for the workflow-managed
`needs-triage` stage, the bot removes only labels it added and recorded in its
comment. A manually set information-request label is also retained. Removing a
bot-managed type, area, or model label freezes automation for that group. To reset
ownership, delete the bot comment and rerun; existing labels remain manual labels.
Only the dedicated comment authored by `github-actions[bot]` supplies ownership
state. Missing, malformed, or copied user-authored state cannot claim ownership.

Adding or removing labels does not trigger a run. Use a manual `apply` run to
reconcile stage labels immediately, or wait for the next supported event.

## Guiding incomplete submissions

The bot checks required information rather than requiring an exact Markdown layout.
GitHub does not expose which template was selected, so it reports specific missing
information instead of claiming that an author did not use a template. CLI/API
submissions and free-form reports receive the same checks.

| Report type | Required information |
| --- | --- |
| All reports | A recognizable issue type, a description, and the reporter's AI model declaration |
| Bugs | Database version or revision, reproduction instructions, and expected behavior |
| Database behavior bugs | Compatible mode and server encoding, or an explicit not-applicable explanation |

The type can come from the form, a manual type label, or classification. Build-only
reports do not need running-server settings. Feature and enhancement requests do
not need bug-only fields. The generic form includes the conditional bug fields;
the existing bug form headings are also recognized. Placeholders such as TODO,
_No response_, bare Other, and tool-only model names do not satisfy the checks.

In `apply` mode, an incomplete report receives `triage/needs-information` and the
same fixed bot comment includes an action request, field-specific instructions,
a template link, and a copyable reply containing only the missing fields. Authors
can edit the issue or supplement it in an author comment. For example:

```text
Description: Refreshing a subscription crashes the server.
Database version: master
Reproduction steps: Create a subscription and refresh it while decoding changes.
Expected behavior: Subscription refresh completes without crashing.
Compatible mode: pg
Server encoding: UTF8
AI model: not used
```

The next apply run shrinks the checklist or replaces it with a passed check, and
clears the bot-owned information-request label when all required information is
present. Manual information-request labels remain for maintainers. Edited or
deleted supplements are reevaluated; supplements are not lost after five later
comments. Comments from other users or bots do not satisfy reporter requirements.
The most recently updated author comment with an explicit answer takes precedence
over older answers for expected behavior and runtime settings.

These checks run locally without relying on the model's opinion. They do not
verify reproduction, accept the issue, or close it. Repeated runs reuse one bot
comment. Automatic reminders require `AUTO_APPLY=true`; otherwise events produce
previews and a manual `apply` run is needed to publish the guidance.

## Declaring the report's AI model

The new [issue form](../ISSUE_TEMPLATE/issue.yml) and existing repository templates
include an `AI model` field. API, CLI, and other submission paths are checked too.
Adding a model label does not replace a written reporter declaration.

Accepted examples:

```text
AI model: org/model-a-v2
```

```text
### AI model

org/model-a-v2, model-b-v1
```

```text
AI model: not used
```

A reporter comment can supply or correct this field. The most recently updated
reporter comment containing a declaration takes precedence; otherwise the issue
body is used. Ordinary subsequent comments do not erase a prior declaration.
Quoted text, code blocks, hidden comments, other users, and bot configuration do
not supply the reporter's model. Chinese field names and declarations are accepted;
bot-generated headings, explanations, and instructions are in English. Quoted
reporter evidence retains its original language.

Up to five models may be separated by commas, semicolons, or newlines; configure
`model_disclosure.max_models` to adjust this. Empty values, placeholders, automatic
model selection, and tool names alone require more information. Conflicting model
and no-AI statements also require clarification.

Normalize names by case, Unicode width, and separators: `org/model-a-v2` becomes
`ai-model/org-model-a-v2`. Long names use a hash suffix; label names are at most
50 characters. Original names remain visible. Labels represent self-reporting,
not validation that a provider actually offers the model. Dynamic labels are
created on apply; `sync-labels` only creates the fixed configured labels.

Model metadata is excluded from database-version extraction, area rules, and
text similarity. The bot clears its own information request when all required
fields have been supplied; manual information requests remain for maintainers.

## Fixed bot comment

[comment.md](comment.md) fixes the order and layout, including empty fields:

1. Classification and labels: proposed result, manual labels, suggestions, evidence.
2. Information completeness: version, platform, model, reproduction clues, expected
   behavior, runtime settings, errors, and an actionable checklist with a reply template.
3. Similar issues: links, relationships, scores, and reasons, or a fixed empty state.
4. Label changes: planned additions and removal of bot-managed labels.
5. Triage notes: analysis method, configured model, search limits, maintainer actions.

AI supplies data rather than formatting. Untrusted content is escaped, including
mentions, links, headings, and hidden markers. Existing bot comments are updated
in place. [example-comment.md](example-comment.md) is the tested offline rendering.

## Interrupted writeback

Before changing issue labels, an apply run saves a pending writeback record in the
same trusted bot comment. If saving the record fails, issue labels are not changed.
The record retains previous ownership and planned additions/removals. After the
label requests succeed, the comment is finalized with the resulting ownership.

If label creation, label updates, or comment finalization fails, the run fails and
the comment may show `Writeback pending`. Rerun the issue in `apply` mode to recover.
Recovery reads current labels, adopts only additions actually present, and treats
completed removals as completed work rather than human suppression. It reanalyzes
the latest report instead of replaying an outdated decision. Preview remains
read-only and does not finalize a pending record. Old comments without pending
records remain compatible.

GitHub does not provide an atomic label-and-comment transaction. A pending record
cannot distinguish an interrupted bot addition from a human adding the exact same
label during the interruption, or an unfinished addition from a later human removal.
Human replacement labels and unrelated labels remain protected. Keep the pending
comment until recovery completes so that ownership evidence is not lost.

## Deployment and manual ranges

Merge the triage files, issue-template updates, and two workflows into the default
branch. Both planning and execution always check out that branch.

1. In Actions -> Issue triage -> Run workflow, select `sync-labels` to create missing
   fixed labels. Existing label colors and descriptions are preserved.
2. Select `preview` and provide `numbers`, for example `12,20-25,31`. Review each
   matrix task's Summary. Closed historical reports can be replayed offline.
3. Select `apply` to update labels and the bot comment for the selected issues.
4. After checking results, set the repository Actions variable
   `AUTO_APPLY=true` to enable automatic label and comment writes. Otherwise event-triggered
   runs are previews. Manual preview is always read-only.

The workflow listens to issue creation, edits, and reopening, plus creation,
editing, or deletion of reporter comments. Adding or removing labels does not
trigger analysis. Bot events are ignored.
Closed, unavailable, opted-out, and PR entries are skipped with an explanation.

`numbers` supports individual IDs, inclusive ascending ranges, mixed lists,
commas, Chinese commas, newlines, and optional `#` prefixes. Duplicates are removed
and IDs sorted. `all`, zero, negative numbers, and open-ended ranges are invalid.
Issue and PR numbers share a sequence; PRs within a range are detected and skipped.

The default limit is 50 unique IDs (`max_batch_items`, configurable up to 200).
Planning only validates IDs and emits sanitized matrix data without credentials or
API requests. At most two matrix tasks run in parallel. Runs for the same number
are serialized. One failed task does not cancel others; its task is marked failed.
Each task has its own Summary. `sync-labels` ignores ranges and creates one task.

Planning requests only `contents: read`; execution requests `contents: read` and
`issues: write`. It uses `GITHUB_TOKEN`, without a personal PAT. Before applying,
the script rereads the issue and comments and rejects stale analysis if they changed.

## Similarity search

Read up to 1,000 recent issue/PR records, retaining open and closed issues and
filtering PRs. Supplement this with at most three repository-scoped keyword
searches. Query tokens cannot inject extra repository or search qualifiers.

TF-IDF weighted cosine similarity emphasizes titles and includes English words,
Chinese bigrams, and a small PostgreSQL vocabulary bridge. The default threshold
is 0.24 with at least two shared terms; show at most three candidates. The score
is text similarity, not a duplicate probability. History and search caps or search
failures are explicitly noted.

Optional AI compares at most ten retrieved candidates using trigger conditions,
versions, reproduction details, and errors. References must belong to the candidate
set and cite actual evidence from both reports. Possible duplicates remain subject
to maintainer confirmation.

## Optional AI

Default request endpoint and model:

```text
https://openrouter.ai/api/v1/chat/completions
openrouter/free
```

A full endpoint is preserved; `/v1` base URLs have `/chat/completions` appended.
Use an OpenRouter key with Bearer authentication. `openrouter/free` is a free-model
router rather than a fixed model version. JSON Object output is requested through
`response_format`, allowing the router to select compatible models. No provider-
specific thinking flag is sent by default. Local validation remains mandatory.
See [OpenRouter API](https://openrouter.ai/docs/api/reference/overview) and
[Free Models Router](https://openrouter.ai/docs/guides/routing/routers/free-router).

| Setting | Location | Purpose |
| --- | --- | --- |
| `AI_API_KEY` | Actions Secret | OpenRouter API key |
| `TRIAGE_AI_ENDPOINT` | Actions variable, optional | Override the endpoint |
| `TRIAGE_AI_MODEL` | Actions variable, optional | Override `openrouter/free` |

Model selection order: manual `ai_model`, repository variable, configuration default.
Without a token, rules and text similarity remain available and no AI request is sent.
Errors, rate limits, unavailable models, and invalid output fall back to rules.

Manual inputs are `mode`, `numbers`, optional `ai_model`, and optional `ai_token`.
The repository Secret takes precedence over the temporary token. The reporter's
`ai-model/*` labels remain independent of the triage service's configured model.

**`ai_token` is a plain workflow string input, not a Secret or password field.**
It enters event data. Trusted steps can read the complete event payload; printing,
uploading, or forwarding it could expose the token. Masking protects subsequent
logs, not the event data itself. Prefer `AI_API_KEY`; use only short-lived,
revocable tokens in the optional manual field.

The script reads a temporary token from `GITHUB_EVENT_PATH`, never interpolating
it into shell commands or a runner-printed env block. It registers `add-mask`
before analysis, escaping percent signs and newlines; unused temporary tokens are
also masked. Tokens do not enter comments, summaries, result JSON, Actions outputs,
or environment files. Automatic issue events ignore manual token inputs.
See [GitHub workflow inputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputsinput_idtype)
and [log masking](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#masking-a-value-in-a-log).

The chat completion protocol sends `model`, system/user `messages`, `temperature: 0`,
and `max_tokens: 3000`; the default model also receives JSON Object response format.
`choices[0].message.content` must contain a JSON object with `labels` and `similar`
arrays. Labels require an allowed type/area, a confidence score of at least
`ai_threshold`, and an exact evidence quote. Model scores are uncalibrated.
Similar entries require a retrieved number, `related` or `possible-duplicate`,
a reason in English, and `evidence_current` / `evidence_candidate` quotes.
Conflicting types are discarded; model results do not override explicit rule groups.

The configured service receives bounded issue text, up to five recent reporter
comments, and bounded candidate descriptions. API credentials are not prompt data.
No issue-provided code or links are executed, and API redirects are not followed.

## Local use and checks

Offline examples neither access the network nor use model credentials:

```sh
python3 -B .github/triage/triage.py --fixture .github/triage/example.json
python3 -B -m unittest discover -s .github/triage -p 'test_*.py' -v
```

Fixtures contain an `issue`, optional `comments`, and `history` in GitHub REST form.
Set `GH_TOKEN` for online preview:

```sh
python3 -B .github/triage/triage.py --repository OWNER/REPO --issue 123
python3 -B .github/triage/triage.py --repository OWNER/REPO --numbers '12,20-25,31'
```

Add `--apply` to write changes. Use `--sync-labels --apply` to create fixed labels,
`--config PATH` for custom configuration, or `--plan-only` to validate ranges
without credentials. Offline fixtures cannot be combined with write modes or ranges.
Local batches run sequentially and reuse history scans, continue after individual
failures, and return a nonzero status if any item failed. Result JSON and optional
`GITHUB_STEP_SUMMARY` include per-item outcomes and aggregate counts.

The checks workflow runs offline tests when automation or issue templates change.
It does not read model credentials. Tests cover bilingual classification, model
declarations, submission guidance and author supplements, form-version and reproduction extraction, stage transitions, manual
overrides, stable comments, range parsing, interrupted writeback before and after
server mutations, PR skipping, stale analysis, credential masking, and provider fallback.

## Classification references

- [PostgreSQL internals overview](https://www.postgresql.org/docs/current/overview.html)
- [PostgreSQL internals](https://www.postgresql.org/docs/current/internals.html)
- [PostgreSQL administration](https://www.postgresql.org/docs/current/admin.html)
- [CommitFest tags](https://commitfest.postgresql.org/)
- [Kubernetes issue triage](https://www.kubernetes.dev/docs/guide/issue-triage/)

Maintainers use Projects and linked PRs to track implementation and review progress.
The bot does not assign owners, set priorities, or close inactive issues.
