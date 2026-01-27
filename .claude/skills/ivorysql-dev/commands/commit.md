---
description: Commit changes with proper IvorySQL commit message format
argument-hint: [--type TYPE] [--message MESSAGE] [--staged]
allowed-tools: [Bash, Grep]
---

# /ivorysql:commit

Commit changes following the IvorySQL commit message specification.

## Usage

```bash
# Interactive commit (prompts for type and message)
/ivorysql:commit

# Specify commit type and message directly
/ivorysql:commit --type fix --message "Handle NULL in array indexing"

# Commit only staged files
/ivorysql:commit -t feat -m "Add DBMS_MY_PACKAGE" --staged

# Quick commit with all changes
/ivorysql:commit -t fix -m "Buffer overflow in dsinterval.c"
```

## Arguments

| Argument | Short | Required | Description |
|----------|-------|----------|-------------|
| `--type` | `-t` | No | Commit type: `feat`, `fix`, `refactor`, `chore`, `docs`, `build`, `test` |
| `--message` | `-m` | No | Commit message (description) |
| `--staged` | No | No | Only commit staged files (default: all modified files) |

## Commit Message Format

**IMPORTANT - IvorySQL Commit Policy:**

```
<type>: <short description>

[optional body explaining why/what changed]

AI-Assisted-By: Claude <noreply@anthropic.com>
```

**RULES:**
- **REQUIRED**: Must include `AI-Assisted-By: Claude <noreply@anthropic.com>` line
- This acknowledges AI assistance in the development process
- Be transparent about AI contribution
- Keep messages short (1-5 lines preferred for description)

**Commit types:**
- `feat` - New feature
- `fix` - Bug fix
- `refactor` - Code refactoring
- `chore` - Maintenance tasks
- `docs` - Documentation changes
- `build` - Build system changes
- `test` - Test changes

## Behavior

### 1. Validate Changes

First, checks what files have changed:

```bash
git status --porcelain
```

### 2. Format Commit Message

If `--type` and `--message` provided, formats as:
```
<type>: <message>

AI-Assisted-By: Claude <noreply@anthropic.com>
```

If interactive mode, prompts for:
1. Commit type (with descriptions)
2. Short description
3. Optional detailed body
4. Auto-adds AI attribution line

### 4. Stage and Commit

```bash
# Add files (unless --staged)
git add <modified-files>

# Commit with formatted message
git commit -m "<formatted_message>"
```

## Interactive Mode Flow

When run without arguments:

```
? Select commit type:
  feat     New feature
  fix      Bug fix
  refactor Code refactoring
  chore    Maintenance
  docs     Documentation
  build    Build system
  test     Test changes

? Enter short description (50 chars max):
? Enter detailed description (optional, press Enter to skip):

Will commit with:
fix: Handle NULL in array indexing

[Enter] to confirm, [Ctrl+C] to cancel
```

## Examples

### Bug Fix

```bash
/ivorysql:commit --type fix --message "Handle NULL in array indexing"
```

Result:
```
fix: Handle NULL in array indexing

Added NULL checks before array access in PL/iSQL
to prevent crashes when indexing with NULL values.

AI-Assisted-By: Claude <noreply@anthropic.com>
```

### New Feature

```bash
/ivorysql:commit -t feat -m "Add DBMS_UTILITY.GET_HASH_VALUE"
```

Result:
```
feat: Add DBMS_UTILITY.GET_HASH_VALUE

Implements Oracle-compatible hash function for
string-to-number conversion.

AI-Assisted-By: Claude <noreply@anthropic.com>
```

### Refactoring

```bash
/ivorysql:commit -t refactor -m "Simplify memory allocation in query executor"
```

Result:
```
refactor: Simplify memory allocation in query executor

Replace multiple palloc calls with single allocation
for improved performance and readability.

AI-Assisted-By: Claude <noreply@anthropic.com>
```

## Pre-commit Checks

Before committing, the command verifies:

1. **AI attribution included** - Ensures AI-Assisted-By line is present
2. **Valid type** - Ensures type is one of: feat, fix, refactor, chore, docs, build, test
3. **Description length** - Warns if description > 72 characters
4. **No trailing whitespace** - Warns if found
5. **Build status** - (Optional) Prompts to run tests if not already done

## Configuration

Uses settings from `.claude/ivorysql-dev.local.md`:

```json
{
  "auto_add_files": true,
  "require_test_pass": false,
  "check_whitespace": true,
  "max_line_length": 72,
  "always_add_ai_attribution": true
}
```

## Exit Conditions

**Success:**
- Changes committed
- Commit message follows specification
- AI attribution included

**Failure:**
- AI attribution missing (must add)
- Invalid commit type
- No changes to commit
- User cancels

## Notes

- Always review commit message before confirming
- Use present tense ("Add" not "Added")
- Capitalize first letter of description
- Don't end description with period
- Keep body lines < 72 characters

## See Also

- `references/git-workflow.md` - Git workflow conventions
- `/ivorysql:pr` - Create pull request after committing
- `/ivorysql:test` - Run tests before committing
