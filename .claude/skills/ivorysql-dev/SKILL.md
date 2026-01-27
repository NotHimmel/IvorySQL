---
name: ivorysql-dev
description: Automated development workflows for IvorySQL including build, test, bug fixes, features, commits, and PRs
---

# IvorySQL Development Skill - Execution Guide

**IMPORTANT: This is an EXECUTABLE skill. When invoked, you must PERFORM the actions, not just describe them.**

## Execution Model

When this skill is invoked, parse the user's arguments to determine the workflow to execute:

### 1. Bug Fix Workflow
Triggered when user mentions:
- "fix bug"
- `/ivorysql-dev:fix-bug` arguments

### 2. Feature Development Workflow
Triggered when user mentions:
- "create feature"
- `/ivorysql-dev:feature` arguments

### 3. Build Workflow
Triggered when user mentions:
- "编译" or "build"
- `/ivorysql-dev:build` arguments

### 4. Test Workflow
Triggered when user mentions:
- "测试" or "test"
- `/ivorysql-dev:test` arguments

### 5. Commit Workflow
Triggered when user mentions:
- "提交" or "commit"
- `/ivorysql-dev:commit` arguments

### 6. PR Workflow
Triggered when user mentions:
- "PR" or "pull request"
- `/ivorysql-dev:pr` arguments

---

## Workflow 1: Bug Fix (EXECUTABLE)

**When triggered:** User mentions bug fix with bug ID or bug-fix-XX.md file

**STEPS TO EXECUTE:**

### Step 1: Read Bug Report
```bash
# Extract bug ID from user input (e.g., "bug-fix-06.md" -> ID = 06)
# Read the bug report file
cat bug-fix-<ID>.md
```

### Step 2: Verify Current State
```bash
# Check git status
git status --porcelain

# Check recent commits to see if fix might already exist
# Look at commits related to affected files from bug report
git log --oneline -20

# Verify current branch
git branch --show-current
```

### Step 3: Create Branch (if fix not already done)
```bash
# Generate branch name from bug description
# Format: fix/<short-description>
git checkout -b fix/<description>
```

### Step 4: Apply Fixes
- Read affected files from bug report
- Apply the suggested fixes
- Use Edit tool to make changes

### Step 5: Build
```bash
# Build the project
make -j$(nproc)

# If build fails, show errors and stop
# If build succeeds, continue
```

### Step 6: Install
```bash
make install
```

### Step 7: Run Tests
```bash
# Run Oracle compatibility tests (includes ivorysql_ora module)
make oracle-pg-check

# Check test results - if tests fail, show failures and ask user
# Parse the output to get actual test count (e.g., "228/228 tests passed")
```

### Step 8: Commit
```bash
# Stage changed files
git add <affected files>

# Create commit with proper format
git commit -m "fix: <short description>

<detailed explanation from bug report>

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 9: Push
```bash
git push -u origin fix/<description>
```

### Step 10: Create PR
```bash
gh pr create \
  --title "fix: <short description>" \
  --body "## Summary
<bug description>

## Bug Report
Resolves: bug-fix-<ID>.md

## Changes
- <list of changes>

## Testing
- [x] Build successful
- [x] Oracle compatibility tests pass (<actual_count>/<total_count>)
- [x] Code follows PostgreSQL conventions

## Affected Files
- <list of files>" \
  --base master \
  --repo IvorySQL/IvorySQL
```

### Step 11: Report Results
```
✅ Bug fix workflow complete
📦 Branch: fix/<description>
🔨 Build: Success
✅ Tests: <actual_count>/<total_count> passed
📝 Commit: <commit hash>
🔗 PR: <PR URL>
```

---

## Workflow 2: Feature Development (EXECUTABLE)

**When triggered:** User mentions creating a feature/package/module

**STEPS TO EXECUTE:**

### Step 1: Parse Feature Arguments
Extract from user input:
- `--name <name>` or package name (e.g., DBMS_MY_PACKAGE)
- `--type <type>` or feature type (plisql-package, sql-function, contrib-module, regression-test)

### Step 2: Verify Feature Doesn't Exist
```bash
# Check if package/module already exists
find . -type d -name "*<name>*"
find . -type f -name "*<name>*"
```

### Step 3: Create Branch
```bash
git checkout -b feat/<name>
```

### Step 4: Generate Code Templates
Based on feature type, generate appropriate files:
1. First, examine existing similar implementations as templates
2. Generate appropriate files based on feature type

**For plisql-package:**
- Examine: `contrib/ivorysql_ora/src/builtin_packages/dbms_*` for reference
- Create: `contrib/ivorysql_ora/src/builtin_packages/dbms_<name>/`
- Generate: `dbms_<name>.sql` (package spec)
- Generate: `dbms_<name>.c` (C implementation)
- Generate: `dbms_<name>--1.0.sql` (extension script)

**For sql-function:**
- Examine: `contrib/ivorysql_ora/src/builtin_functions/*.c` for reference
- Create: `contrib/ivorysql_ora/src/builtin_functions/<name>.c`

**For contrib-module:**
- Examine: `contrib/*/` for existing module patterns
- Create: `contrib/<name>/` with full module structure

**For regression-test:**
- Examine: `src/oracle_test/regress/sql/*.sql` for test patterns
- Create: `src/oracle_test/regress/sql/<name>.sql`
- Create: `src/oracle_test/regress/expected/<name>.out`

### Step 5: Update Build Files (if needed)
Based on feature type, update appropriate Makefiles:
- **plisql-package**: `contrib/ivorysql_ora/Makefile`, `contrib/ivorysql_ora/src/builtin_packages/Makefile`
- **sql-function**: `contrib/ivorysql_ora/Makefile`, `contrib/ivorysql_ora/src/builtin_functions/Makefile`
- **contrib-module**: `contrib/<name>/Makefile`, top-level `Makefile` if needed
- **regression-test**: `src/oracle_test/regress/Makefile` (add to ORA_REGRESS variable)

### Step 6: Build
```bash
make -j$(nproc)
```

### Step 7: Install
```bash
make install
```

### Step 8: Run Tests
```bash
# Run relevant tests based on feature type
# plisql-package, sql-function: make oracle-pg-check
# contrib-module: cd contrib/<name> && make installcheck
# regression-test: make oracle-pg-check

make oracle-pg-check    # Default for most features
# or specific tests based on feature type
```

### Step 9: Commit
```bash
git add .
git commit -m "feat: Add <feature description>

<implementation details>

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 10: Push
```bash
git push -u origin feat/<name>
```

### Step 11: Create PR
```bash
gh pr create \
  --title "feat: Add <feature name>" \
  --body "## Summary
Add <feature type> for IvorySQL Oracle compatibility

## Feature Details
**Type:** <type>
**Name:** <name>

## Changes
- <list of changes>

## Testing
- [x] Build successful
- [x] Tests pass
- [x] Code follows PostgreSQL conventions

## Files Added
<list of files>" \
  --base master \
  --repo IvorySQL/IvorySQL
```

### Step 12: Report Results
```
✅ Feature development workflow complete
📦 Branch: feat/<name>
🔨 Build: Success
✅ Tests: <actual_count>/<total_tests> passed
📝 Commit: <commit hash>
🔗 PR: <PR URL>
```

---

## Workflow 3: Build (EXECUTABLE)

**When triggered:** User mentions "build" or "编译"

**STEPS TO EXECUTE:**

### Step 1: Check Prerequisites
```bash
# Verify configure script exists
test -f configure || echo "Run ./configure first"

# Check for existing build
test -d src/backend && echo "Build directory exists"
```

### Step 2: Clean (if requested)
```bash
# If user specified --clean, run:
make clean
```

### Step 3: Build
```bash
make -j$(nproc)
```

### Step 4: Verify Build
```bash
# Check for errors in build output
# If build failed, show errors and STOP

# If build succeeded, show summary
echo "✅ Build successful"
```

### Step 5: Install
```bash
make install
```

### Step 6: Verify Installation
```bash
# Check if postgres binary exists and is new
stat -c '%Y %n' $PWD/inst/bin/postgres

# Verify version
$PWD/inst/bin/postgres --version
```

### Step 7: Report Results
```
✅ Build workflow complete
📦 Installation prefix: $PWD/inst
🔧 Build: Success
```

---

## Workflow 4: Test (EXECUTABLE)

**When triggered:** User mentions "test" or "测试"

**STEPS TO EXECUTE:**

### Step 1: Determine Test Mode
- Default: Run Oracle compatibility tests (`make oracle-pg-check`)
- If user specified `--mode pg`: Run `make check`
- If user specified `--mode all`: Run `make check-world`

### Step 2: Check Prerequisites
```bash
# Verify IvorySQL is installed
ls -la $PWD/inst/bin/postgres $PWD/inst/bin/psql 2>/dev/null || echo "Binaries not found in $PWD/inst"
```

### Step 3: Run Tests
```bash
# Based on test mode, run appropriate command
make oracle-pg-check    # Default for ivorysql_ora module
# or
make check              # PostgreSQL tests
# or
make check-world        # All tests
```

### Step 4: Parse Test Results
```bash
# Check for failures in test output
# Look for patterns like "failed", "FAILED", "diff"
# Parse test counts from output (e.g., "228/228 tests passed")

# If test output contains regression.diffs:
#   Show the diff files to identify what failed
#   Count: grep -c "^\+" regression.diffs for additions
#          grep -c "^-" regression.diffs for deletions

# Show summary with actual counts from test output
```

### Step 5: Report Results
```
✅ Test workflow complete
📊 Test Mode: <ora|pg|all>
✅ Passed: <actual_passed>/<total_tests>
❌ Failed: <actual_failed> or 0
⏱️  Duration: <actual_time>
```

---

## Workflow 5: Commit (EXECUTABLE)

**When triggered:** User mentions "commit" or "提交"

**STEPS TO EXECUTE:**

### Step 1: Check Status
```bash
git status
```

### Step 2: Determine Commit Type
From user input or analyze changes:
- `feat` - New feature
- `fix` - Bug fix
- `refactor` - Code refactoring
- `docs` - Documentation
- `test` - Test changes
- `chore` - Maintenance

### Step 3: Stage Files
```bash
# If --staged flag, only commit staged files
# Otherwise, add all modified files
git add <files>
```

### Step 4: Create Commit
```bash
git commit -m "<type>: <short description>

<detailed body if provided>

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 5: Verify Commit
```bash
git log -1 --stat
```

### Step 6: Report Results
```
✅ Commit workflow complete
📝 Commit: <hash>
📄 Message: <type>: <description>
📊 Files changed: <count>
```

---

## Workflow 6: Pull Request (EXECUTABLE)

**When triggered:** User mentions "PR" or "pull request"

**STEPS TO EXECUTE:**

### Step 1: Check Current Branch
```bash
git branch --show-current
```

### Step 2: Check for Uncommitted Changes
```bash
git status --porcelain
```

### Step 3: Push to Remote
```bash
git push -u origin $(git branch --show-current)
```

### Step 4: Generate PR Body
Create PR body based on:
- Recent commits in branch: `git log master..HEAD --oneline`
- Comparison with master: `git diff master...HEAD --stat`
- Branch name (infer type: `fix/`, `feat/`, `refactor/`)

Title format from first commit:
- `fix: <description>` for fix/* branches
- `feat: <description>` for feat/* branches
- `<type>: <description>` for others

### Step 5: Create PR
```bash
gh pr create \
  --title "<auto-generated or user-provided title>" \
  --body "<auto-generated body>" \
  --base master \
  --repo IvorySQL/IvorySQL
```

### Step 6: Report Results
```
✅ PR workflow complete
🔗 PR URL: <url>
📦 Branch: <branch>
📊 Base: master
```

---

## Quick Start Commands (For Help Mode)

When no specific workflow is triggered, show this table:

| Command | Purpose |
|---------|---------|
| `/ivorysql-dev:build` | Build and install IvorySQL |
| `/ivorysql-dev:test` | Run regression tests |
| `/ivorysql-dev:commit` | Commit changes with proper format |
| `/ivorysql-dev:pr` | Create pull request |
| **Bug fix**: Mention "bug-fix-XX.md" or "fix bug" | Automated bug fix workflow |
| **Feature**: Mention "create feature" or "add package" | Automated feature development |

---

## Configuration

Default settings (can be overridden in `.claude/ivorysql-dev.local.md`):

```json
{
  "install_prefix": "$PWD/inst",
  "test_mode": "ora",
  "default_base": "master",
  "auto_push": true
}
```

---

## Important Notes

1. **ALWAYS EXECUTE**: When this skill is invoked, you must PERFORM the actions, not just describe them
2. **Use TodoWrite**: Track progress through workflows with todo items
3. **Stop on Errors**: If build or tests fail, stop and report the error - don't continue
4. **Verify**: After each major step (build, test), verify success before continuing
5. **Report**: Always provide a summary at the end with what was accomplished
6. **Git Safety**: Never use `--force` when pushing, never amend commits

---
