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

- Types: select `bug`, `feature`, or `enhancement`, or abstain. The `issue_types`
  mapping defaults to native `Bug`, `Feature`, and `Enhancement`. Regressions are
  bugs; features add capabilities; enhancements improve existing ones. When the
  matching native type is unavailable, use its `type/*` label as a fallback.
- Areas: at most two of the 20 `area/*` labels, mapped from PostgreSQL subsystems.
  These are repository labels based on PG documentation, not official PG issue labels.
- Models: `ai-model/*` records the model explicitly declared by the reporter.
  Every issue type requires a declaration, including an explicit `not used` if applicable.
- Stage: `needs-triage` is workflow-managed, including when added by a template.
  On the next triage run, acceptance (`triage/accepted`) or any `resolution/*`
  label removes it. Removing acceptance and resolution restores it for open
  issues on the next run. Automated classification does not imply acceptance.
- Information: bot-owned `triage/needs-information` asks the author for specific
  missing details. Maintainer acceptance or resolution clears automated requests;
  manually applied information-request labels remain for maintainers. Missing model
  declarations, empty descriptions, and incomplete bug reports
  produce a specific checklist. Releases, `master`/`main`,
  PostgreSQL stable branches, and explicit commit IDs count as version information.
  Reproduction fields can contain prose; SQL, shell commands, and numbered steps
  are also accepted clues. Environment scaffolding and log sections are excluded.
  These checks do not prove that reproduction succeeds.
- Reproduction/clarification: `triage/needs-reproduce` routes an author response or uncertain source
  conflict to maintainers. It does not mean the report is complete or accepted.
- Resolutions: `resolution/duplicate`, `resolution/invalid`, `resolution/wontfix` are
  maintainer decisions. Confirmed duplicates should link to their original issue.
- `triage/skip` is manually applied by maintainers to exclude an issue from all
  triage runs, including manual runs. The bot never adds this label. Removing it
  allows processing on the next supported event or manual run.

An existing manual native Issue Type has first priority, followed by manual classification labels. Except for the workflow-managed
`needs-triage` stage, the bot removes only labels it added and recorded in its
comment, plus redundant legacy type assignments after confirming their canonical
replacement. A manually set information-request label is also retained. Removing a
bot-managed type, area, or model label freezes automation for that group. To reset
ownership, delete the bot comment and rerun; existing labels remain manual labels.
Only the dedicated comment authored by `github-actions[bot]` supplies ownership
state. Missing, malformed, or copied user-authored state cannot claim ownership.

Adding or removing labels does not trigger a run. Use a manual `apply` run to
reconcile stage labels immediately, or wait for the next supported event.

Templates retain portable `type/bug`, `type/feature`, or `type/enhancement`
bootstrap labels so they remain usable before organization types are configured.
The bot migrates them into the native Type when available and removes known
redundant type assignments after verifying the field. Without native support,
apply adds or confirms the canonical fallback label before removing a redundant
legacy assignment. Legacy `enhancement` is also redundant
when an explicit `type/feature` exists, matching older feature templates. Conflicting
type assignments are left for maintainers. The normalized label retains the manual
priority of the original classification, including after an interrupted writeback.

## Native Issue Types and label fallback

`issue_types` maps the classifier's `bug`, `feature`, and `enhancement` values to
organization type names. The worker reads enabled types once from
`GET /repos/{owner}/{repo}/issue-types`, requiring only repository metadata read
access, and uses `PATCH /repos/{owner}/{repo}/issues/{number}` with `type` to set
the chosen value. First verify that the repository is organization-owned: personal
repositories can expose a default type catalog while silently ignoring type writes,
even with owner credentials. For organizations, inspect enabled names rather than
assuming the required types exist. Personal repositories, missing/disabled types,
or an unavailable catalog keep the existing label fallback. Discovery does not
create or modify organization settings. Organization owners can add `Enhancement` later and replay
the issues. `sync-labels` omits fallback type labels whose native types are enabled.
The fallback definitions remain in `labels` for matching, colors, and compatibility.

Native Type is authoritative when manually set. Bot-owned Types can be updated
when the report's classification changes; manually migrated label/form choices
retain manual priority. A human Type edit transfers ownership to the human, and a
human clear freezes automatic type assignment rather than replacing the field
with a fallback label. The `typed` and `untyped` events capture those actions,
including a clear before the first bot run. Delete the bot comment to reset state,
or choose a native Type explicitly. A temporarily unavailable proposed type does
not produce a contradictory label alongside a different existing native Type.

A native write is journaled before it happens and is reread before old type labels
are removed. Rejected or silently ignored writes fail the target and preserve its
old labels; they do not report successful migration. Interrupted writes recover
from the observed native value, including lost API responses. Human changes during
analysis or recovery are preserved. The input fingerprint includes the native
field and enabled type catalog, so later activation of an organization type can
migrate fallback labels on the next supported event or manual run. The public bot
comment remains short; native change plans are available in preview diagnostics.

An organization-only deployment may set the form's top-level `type: Bug` (or
`Feature` / `Enhancement`) and remove its bootstrap label once those types exist.
The shared templates avoid that requirement so the same PR can still be tested
in a fork where form-level native types may not be supported.

See [repository type discovery](https://docs.github.com/en/rest/repos/issue-types),
[issue updates](https://docs.github.com/en/rest/issues/issues#update-an-issue), and
[organization type settings](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-types-in-an-organization).

## Renaming the previous review label

`triage/needs-reproduce` replaces `triage/needs-review` everywhere. The state rules
are unchanged: it covers unverified reproduction, ordinary author replies,
classification uncertainty, and conflicting declarations. Rename the existing
repository label to `triage/needs-reproduce` in GitHub's label settings before
replaying existing reports; GitHub preserves its issue assignments. Old hidden
`needs-review` states and pending ownership records are recognized so completion
can still clear bot-owned labels after the rename. Manual labels remain manual.
Do not delete and recreate the old label: that would discard its assignments.

## Guiding incomplete submissions

The bot checks required information rather than requiring an exact Markdown layout.
GitHub does not expose which template was selected, so it reports specific missing
information instead of claiming that an author did not use a template. CLI/API
submissions and free-form reports receive the same checks.

| Report type | Required information |
| --- | --- |
| All reports | A description and the reporter's AI model declaration |
| Bugs | Database version or revision, reproduction instructions, and expected behavior |
| Bugs with prose or unfenced reproduction instructions | Whether the author personally reproduced the problem with the reported version |
| Database behavior bugs | Compatible mode and server encoding, or an explicit not-applicable explanation |

The type comes first from an existing manual native Type, then an existing manual
type label (including legacy `bug`, `feature`, `feature-request`, and `enhancement`
labels), an optional explicit form choice, AI classification, or fallback rules.
An existing native Type outside the configured mapping is preserved and routed
to maintainers, without guessing a replacement. Required fields use the effective
native classification or the planned classification for an initially untyped report. An unresolved type is
a maintainer task and is never requested from the author. Other clear information
gaps can still be requested. Build-only
reports do not need running-server settings. Feature and enhancement requests do
not need bug-only fields. The generic form includes the conditional bug fields;
the existing bug form headings are also recognized. Placeholders such as TODO,
_No response_, bare Other, and tool-only model names do not satisfy the checks.

In `apply` mode, an incomplete report receives `triage/needs-information` and the
same fixed bot comment briefly states whether more information is needed and lists
the missing fields. Authors can edit the issue or supplement it in an author
comment. For example:

```text
Description: Refreshing a subscription crashes the server.
Database version: master
Reproduction steps: Create a subscription and refresh it while decoding changes.
Reproduced in a real environment: Yes
Expected behavior: Subscription refresh completes without crashing.
Compatible mode: pg
Server encoding: UTF8
AI model: not used
```

The next apply run follows these transitions:

| Situation | Automatic result |
| --- | --- |
| First incomplete report, or a structured supplement that still leaves clear gaps | Update the missing-field checklist and use `triage/needs-information` |
| The author responds in prose and the checks cannot confirm completeness | Replace the author request with a maintainer-review message and use `triage/needs-reproduce` |
| Conflicting answers cannot be ordered reliably | Request maintainer review; preserve existing labels in the conflicting type/model group |
| The author explicitly says reproduction has not been verified | Route to maintainer review without repeatedly demanding a Yes answer |
| Required information is present without unresolved conflicts | Clear bot-owned information/review labels and report that field checks passed |
| A maintainer applies `triage/accepted` or a `resolution/*` label | Clear automated requests and let maintainers manage further questions |

Manual information/review labels remain for maintainers. Review is retained across
ordinary replies instead of repeatedly asking the author to rewrite information.
Structured corrections can refresh the remaining checklist; a complete supplement
clears the bot-owned review label. Removing acceptance and
resolution allows a new automatic information-request round on the next run.
Edited or deleted supplements are reevaluated; supplements are not lost after five
later comments. Comments from other users or bots do not satisfy reporter requirements.

Filled field-only replies are accepted inside a text/Markdown code block when they
contain at least two recognized fields, or a single field the bot has requested.
Blocks containing log lines, code, or unrelated text stay fenced and do not become
declarations. Version numbers followed by sentence punctuation are recognized.
Common prose such as "I expected ...", "in pg compatibility mode", and "UTF8
encoding" is recognized. When the bug form selects `Other` for encoding, one
unambiguous encoding in its additional-information section is accepted.

Reproduction instructions and reported verification are separate facts. When a bug
has only prose or unfenced example code and no explicit confirmation, the short
checklist asks whether the author reproduced it in a real environment with the
reported version. Formatting does not establish AI authorship, and fenced code
does not establish that it was run. `Reproduced in a real environment: Yes` records
the author's confirmation; `No` or `Not verified yet` routes the report to review.
Running the real project module or build code counts for module/build reports;
a database server is not required for those cases. The bot never executes submitted
commands or claims independent verification.

After this question, a new author reply of `Yes` or `No` also counts. Its binding
to the question is retained for subsequent edits of that reply. Older unrelated
answers and other users' comments do not supply confirmation. When field edit
times establish a version or reproduction change newer than the confirmation,
renewed confirmation is required.

Required-field and lifecycle decisions run locally. AI classifies the type when
labels or an explicit form choice have not fixed it; rules provide fallback.
Area rules remain primary, with optional model suggestions when rules abstain. These checks do not
verify reproduction, accept the issue, or close it. Repeated runs reuse one bot
comment. Automatic reminders require `AUTO_APPLY=true`; otherwise events produce
previews and a manual `apply` run is needed to publish the guidance.

## Declaring the report's AI model

The new [issue form](../ISSUE_TEMPLATE/issue.yml) and existing repository templates
include an `AI usage` dropdown, preselected to `Not used`, and an optional
`AI model` field. Choose `Used` and supply model names/versions when AI helped
discover, investigate, or write the issue. The bot requests missing model details
only when needed; `Not used` with a blank model field maps to `ai-model/not-used`.
GitHub forms cannot conditionally require the model field, so the bot checks it.
API, CLI, and other submission paths still need an explicit disclosure; a missing
field does not imply `Not used`. Legacy model-only declarations remain accepted.
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

The usage choice and optional model field form one declaration for update
ordering. A later model-only comment can correct an earlier `Not used` selection;
a later `Not used` selection clears an older model declaration. Contradictory
answers in one declaration require clarification.

A reporter comment or body edit can supply or correct this field. The field-source
rules below determine which declaration is current. Ordinary subsequent comments
do not erase a prior declaration. Quoted text, arbitrary code blocks, hidden
comments, other users, and bot configuration do not supply the reporter's model.
The field-only reply exception above also applies to this field.
Chinese field names and declarations are accepted;
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

## Field sources and edit times

Each explicit field records its source (`body` or a comment ID), answer hash, and
edit time. The first observation uses source edit times as its baseline; historical
field-level edits before that observation cannot be reconstructed. The latest
changed answer wins after that baseline. Editing a different paragraph does not
reassert every unchanged answer from that body/comment: saved field history keeps
the earlier field time. History retains the body declaration, the two newest
comment declarations, and one unresolved declaration per field, bounding saved metadata. An edited old comment
outside that retained history is treated conservatively if its field order cannot
be established.

REST issue `updated_at` also changes on comments and labels. The reader therefore
uses a read-only GraphQL query for the body's `lastEditedAt`/`createdAt`, verifying
that the GraphQL and REST body snapshots agree. If this lookup fails or edit times
tie, conflicting declarations route to maintainer review. The bot does not guess
which answer is newer or change type/model labels based on an unresolved conflict.
Only hashes and source metadata are saved in the trusted bot comment, without
copying complete discussions or API keys into its hidden state. Existing comments
without this metadata continue to work and gain it on the next apply run.

## Fixed bot comment

Every comment starts with `Thanks for contributing to IvorySQL!` after its hidden
ownership marker.

[comment.md](comment.md) fixes two visible sections:

1. Information needed: a short conclusion and only the missing fields. Review and
   maintainer-confirmed states use one short sentence without repeating requests.
2. Similar issues: at most three issue links and short titles, with a related or
   possible-duplicate indication. An empty or deferred search uses one sentence.

The public comment does not include classification tables, evidence dumps,
similarity scores, model configuration, label operations, or a reply skeleton.
Detailed analysis, labels, and diagnostics remain in the Actions result JSON and
an expandable Analysis details block in the workflow Summary.

AI supplies data rather than formatting. Untrusted content is escaped, including
mentions, links, headings, and hidden markers. Existing bot comments are updated
in place. [example-comment.md](example-comment.md) is the tested offline rendering.

## Interrupted writeback

Before changing the native Type or issue labels, an apply run saves a pending writeback record in the
same trusted bot comment. If saving the record fails, issue labels are not changed.
The record retains previous ownership and planned additions/removals. After the
label requests succeed, the comment is finalized with the resulting ownership.

If label creation, label updates, or comment finalization fails, the run fails and
the pending record remains in the hidden comment state. The public comment keeps
the same two-section format. Rerun the issue in `apply` mode to recover.
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

## Repeated events and stale results

Automatic jobs wait 15 seconds before reading the current issue so rapid author
edits can settle. Writes for one issue remain serialized. The saved input hash
includes title/body, author supplements, labels, native Type/catalog, policy/configuration, comment
template, and model settings. When these match a successfully published result,
an automatic event skips history scans, search, model calls, and writes. A pending
writeback record always bypasses this shortcut. Manual runs always analyze afresh,
which can refresh similar-issue results even without an author content change.
Preview never stores a new hash or modifies a pending record.

An automatic plain response to an outstanding information request can be routed
to maintainer review using local checks. That path defers history/search/model
analysis and preserves existing type/area labels. A manual run still performs the
full analysis.

Before publishing the pending record, before changing labels, and before finalizing
the comment, the script checks the current evidence against the analyzed snapshot
or expected resulting labels. A stale decision is rejected. Changes after journal
publication leave that journal available for recovery. These checks are best
effort: GitHub does not offer an atomic compare-and-write operation for this flow.

## Deployment and manual ranges

Merge the triage files, issue-template updates, and two workflows into the default
branch. Both planning and execution always check out that branch.

1. In Actions -> Issue triage -> Run workflow, select `sync-labels` to create missing
   fixed labels. Existing label colors and descriptions are preserved.
2. Select `preview` and provide `numbers`, for example `12,20-25,31`. Review the batch Summary and its per-issue outcomes. Closed historical reports can be replayed offline.
3. Select `apply` to update labels and the bot comment for the selected issues.
4. After checking results, set the repository Actions variable
   `AUTO_APPLY=true` to enable automatic label and comment writes. Otherwise event-triggered
   runs are previews. Manual preview is always read-only.

The workflow listens to issue creation, edits, reopening, native typing/untyping,
and creation, editing, or deletion of reporter comments. Adding or removing labels does not
trigger analysis. Bot events are ignored.
Closed, unavailable, opted-out, and PR entries are skipped with an explanation.

`numbers` supports individual IDs, inclusive ascending ranges, mixed lists,
commas, Chinese commas, newlines, and optional `#` prefixes. Duplicates are removed
and IDs sorted. `all`, zero, negative numbers, and open-ended ranges are invalid.
Issue and PR numbers share a sequence; PRs within a range are detected and skipped.

The default limit is 50 unique IDs (`max_batch_items`, configurable up to 200).
Planning only validates IDs and emits sanitized target data without credentials or
API requests. Execution uses one Python process for the whole batch, processing
issues sequentially and sharing a history snapshot. The repository-wide execution
concurrency group uses `queue: max`, allowing up to 100 pending jobs instead of
replacing older pending events. Jobs beyond GitHub's queue limit are canceled and
must be replayed manually. Other workflows are outside this concurrency group.
A non-rate-limit failure on one issue does not cancel other targets. A rate-limit
cooldown stops the remaining targets, reports them as failed, and exits nonzero;
rerun those numbers after the reported time. `sync-labels` ignores ranges.
The worker has a 180-minute job limit; split very large or slow batches.

Planning requests only `contents: read`; execution requests `contents: read` and
`issues: write`. It uses `GITHUB_TOKEN`, without a personal PAT. Before applying,
the script rereads the issue and comments and rejects stale analysis if they changed.

## History caching and API rate limits

The workflow restores and saves a repository-scoped Actions cache containing only
bounded history inputs and request pacing/cooldown timestamps. It never stores
model credentials, raw event payloads, or the authoritative issue/comment reads.
Cache actions are pinned to an immutable official `actions/cache` commit.

One process fetches history at most once per limit and shares it across a batch.
Across workflow runs, `history_cache_ttl` defaults to 900 seconds. A valid snapshot
inside that freshness window is reused without a history API request. After it
expires, list issues updated since the previous scan began, with a 60-second
overlap, merge their new titles/bodies/states, and retain the bounded recent window.
If updates overflow the bound, the cache is invalid, or the daily full-refresh
interval (`history_full_sync_interval`, 86400 seconds) has elapsed, perform a bounded
full scan instead. Periodic full refreshes occur on the next run and remove deleted
records. Cache failures fall back to a bounded scan or in-memory reuse and are
noted in diagnostics. Cached candidate descriptions can be up to the freshness
window old; keyword searches supplement them. Current issue and comments are
always read from GitHub before deciding or writing changes.

GitHub requests are sequential and paced by resource. Start with at least one
second between ordinary/GraphQL requests, 2.2 seconds between searches, and eight
seconds between content writes. Response rate-limit headers further slow requests
based on remaining budget and reset time, reserving headroom. This does not grant
an independent quota: other repository workflows can consume the same budget.

For a rejected request, honor both `Retry-After` (seconds or HTTP date) and an
exhausted primary bucket's reset time. Secondary-limit responses without those
headers wait at least one minute with exponential backoff. Ordinary permission
403 responses are not retried. At most three attempts and 120 seconds of pacing/
retry budget are allowed per request; longer waits stop the batch with a retry time.
The cooldown is saved for subsequent queued workers, which stop before making
another API request if the remaining cooldown exceeds their wait budget. Cache
save/restore must succeed for that cross-run handoff. A cache outage still leaves
per-process pacing and bounded retries, but loses the shared cooldown.
Unknown outcomes from network/write failures are not automatically retried; the
existing write journal supports recovery on the next run. AI failures continue to
fall back to local rules and are separate from GitHub rate control.

See [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api),
[REST API best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api),
and [Actions concurrency queues](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

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
`choices[0].message.content` must contain a JSON object with a `type` object (or
null), an area `labels` array, and a `similar` array. The type object carries
`name`, `confidence`, and `evidence`. Types and areas require an allowed value,
a confidence score of at least `ai_threshold`, and an original evidence quote.
Legacy AI output using `type/*` label entries remains accepted, but does not create
such labels when a native Type can be used. Model scores are uncalibrated.
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
Local batches run sequentially and reuse history scans, continue after non-rate
failures, and return a nonzero status if any item failed. To persist snapshots and
cooldowns locally, set `TRIAGE_HISTORY_CACHE` to a writable JSON path. Local
processes do not participate in the Actions repository queue; avoid running
multiple local writers for the same repository. Result JSON and optional
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
