---
description: Run IvorySQL regression tests (local mode, defaults to all tests)
argument-hint: [--mode MODE] [--module PATH]
allowed-tools: [Bash]
---

# /ivorysql:test

Run IvorySQL regression tests. Defaults to running all tests to match GitHub workflow coverage.

## Usage

```bash
# Run all tests (PostgreSQL and Oracle)
/ivorysql:test --mode all

# Run only PostgreSQL compatibility tests
/ivorysql:test -m pg

# Run only Oracle compatibility tests
/ivorysql:test -m ora

# Run tests for a specific module
/ivorysql:test --mode all --module contrib/ivorysql_ora
```

## Arguments

| Argument | Short | Required | Description |
|----------|-------|----------|-------------|
| `--mode` | `-m` | No | Test mode: `pg` (PostgreSQL), `ora` (Oracle), or `all` (both). Default: `all` |
| `--module` | No | No | Path to specific module (e.g., `contrib/ivorysql_ora`, `src/pl/plisql/src`) |

## Test Modes

The test mode (`--mode`) determines which tests to run:

| Mode | Tests Run | Command |
|------|-----------|---------|
| `pg` | PostgreSQL compatibility tests | `make check` |
| `ora` | Oracle PostgreSQL compatibility tests | `make oracle-pg-check` |
| `all` | Both PostgreSQL and Oracle tests | `make check-world` |

**Note:** These test commands match the `.github/workflows`:
- `pg_regression.yml` uses `make check-world`
- `oracle_pg_regression.yml` uses `make check` and `make oracle-pg-check`
- **Default (`all`) runs `make check-world` to match full CI coverage**

## Oracle Compatibility Mode Testing

**Important:** The `contrib/ivorysql_ora` module requires Oracle compatibility mode to work correctly.

When testing `contrib/ivorysql_ora`, the test framework automatically:
1. Creates a temporary database with `initdb -m oracle` (Oracle mode)
2. Sets the `compatible_db` parameter
3. Uses the Oracle-compatible parser

**Test commands for `contrib/ivorysql_ora`:**

```bash
# Option 1: Using make check (creates Oracle temp instance)
cd contrib/ivorysql_ora && make check

# Option 2: Using oracle-pg-check from project root
make oracle-pg-check

# Option 3: Manual pg_regress with Oracle mode
cd contrib/ivorysql_ora
../../src/test/regress/pg_regress \
  --temp-instance=./tmp_check \
  --temp-config=./oracle_test.conf \
  --dbname=contrib_regression \
  ora_interval ora_datetime ...
```

**Oracle test configuration:**
- Tests use `initdb -m oracle` for Oracle compatibility
- Port: 1521 (can be overridden via `REGRESS_OPTS = --port=XXXX`)
- The `INITDB_TEMPLATE` points to an Oracle-mode database template

## Prerequisites

- IvorySQL built and installed locally
- PostgreSQL/IvorySQL binaries in `$PATH`

**Set PATH if needed:**
```bash
export PATH=$PWD/inst/bin:$PATH
```

## Behavior

### 1. Determine Test Mode

Uses `--mode` argument if provided, otherwise defaults to `all` (runs `make check-world` to match full CI coverage).

### 2. Check Prerequisites

```bash
# Check if IvorySQL is installed
which postgres
which psql

# Check version
postgres --version
```

### 3. Run Tests

**Without --module:**

| Test Mode | Command |
|-----------|---------|
| `pg` | `make check` |
| `ora` | `make oracle-pg-check` |
| `all` | `make check-world` |

**With --module:**

```bash
cd <module> && make check
# or
cd <module> && make installcheck
```

**For `contrib/ivorysql_ora` (requires Oracle mode):**
```bash
cd contrib/ivorysql_ora && make check
```

## Module Testing

When a specific module is specified with `--module`:

### PL/iSQL Tests

```bash
/ivorysql:test --module src/pl/plisql/src --mode ora
```

```bash
cd src/pl/plisql/src && make oracle-pg-check
```

### Oracle Extension Tests

```bash
/ivorysql:test --module contrib/ivorysql_ora
```

```bash
cd contrib/ivorysql_ora && make check
```

**Important:** `contrib/ivorysql_ora` tests require Oracle compatibility mode:
- Uses `initdb -m oracle` for test database
- Tests are defined in `ORA_REGRESS` variable in Makefile
- Key tests: `ora_interval`, `ora_datetime`, `ora_character`, `ora_number`, `dbms_utility`, etc.

### Backend Tests

```bash
/ivorysql:test --module src/test/regress --mode pg
```

```bash
cd src/test/regress && make check
```

## Return Format

Returns a summary with:

```
Test Mode: ora
Tests Passed: 142/145
Tests Failed: 3

Failed Tests:
- plisql_array: Unexpected output at line 45
- plisql_package: Test timeout
- ora_interval: Assertion failed

Duration: 5m 23s
```

## Configuration

Uses settings from `.claude/ivorysql-dev.local.md`:

```json
{
  "test_mode": "all",
  "install_prefix": "/usr/local/ivorysql"
}
```

## Examples

```bash
# Run all tests
/ivorysql:test --mode all

# Run only Oracle tests
/ivorysql:test -m ora

# Test specific module
/ivorysql:test --module contrib/ivorysql_ora
```

## Test Suites

### 1. PostgreSQL Compatibility Tests

**Location:** `src/test/regress/`

**Runner:** `pg_regress`

Tests standard PostgreSQL features to ensure compatibility with upstream PostgreSQL.

**Common tests:**
- `test_sql` - Basic SQL functionality
- `uuid` - UUID data type
- `numeric` - Numeric operations

### 2. Oracle Compatibility Tests

**Location:** `src/oracle_test/regress/`

**Runner:** `ora_pg_regress`

Key tests include:
- `ora_plisql.sql` - PL/iSQL language tests
- `ora_package.sql` - Oracle package tests
- `ora_interval.sql` - Interval data type tests
- Oracle SQL syntax compatibility

### 3. PL/iSQL Language Tests

**Location:** `src/pl/plisql/src/`

Tests PL/iSQL procedural language internals.

**Common tests:**
- `plisql_array` - Array operations
- `plisql_control` - Control structures
- `plisql_dbms_output` - DBMS_OUTPUT package

### 4. Oracle Extension Tests

**Location:** `contrib/ivorysql_ora/`

Tests Oracle compatibility packages (DBMS_UTILITY, datatypes, functions).

**Test files:** `sql/*.sql` and expected outputs in `expected/*.out`

## Exit Conditions

**Success:**
- All tests pass
- No regression failures

**Failure:**
- Tests fail
- Timeouts
- Unexpected output

**Prerequisites Not Met:**
- IvorySQL not installed

## Troubleshooting

### Command Not Found

```bash
# Add IvorySQL to PATH
export PATH=/usr/local/ivorysql/bin:$PATH

# Or add to ~/.bashrc
echo 'export PATH=/usr/local/ivorysql/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### Permission Denied

```bash
# Some tests may need to create temporary files
# Ensure you have write permissions in the test directory
```

### Tests Fail with "Database Already Running"

```bash
# Stop any running test databases
# Tests usually manage their own test databases

# Check for running postgres processes
ps aux | grep postgres
```

### Tests Timeout

```bash
# Increase timeout (if supported by test runner)
# Or run with more verbose output to see where it hangs
```

### Oracle Mode Tests Fail

If `contrib/ivorysql_ora` tests fail with PostgreSQL-style output:

```bash
# The test framework should automatically create an Oracle-mode database
# Check that the test is using the correct initdb template:
# It should use: initdb -m oracle

# Manual verification:
cd contrib/ivorysql_ora
make check

# Check regression.diffs for specific failures
cat regression.diffs
```

**Common Oracle mode test issues:**
- Syntax errors on `YEAR(n) TO MONTH` - means test is running in PostgreSQL mode instead of Oracle mode
- Output showing `interval` instead of `yminterval`/`dsinterval` - PostgreSQL mode active
- Relation does not exist errors - Caused by CREATE TABLE syntax failures due to mode mismatch

## Test Performance

| Test Suite | Time | Tests |
|------------|------|-------|
| PostgreSQL (check) | 2m - 5m | ~150 |
| Oracle (oracle-check) | 3m - 7m | ~100 |
| PL/iSQL | 1m - 3m | ~50 |
| Contrib module | 10s - 1m | ~10-20 |

## Manual Testing with Oracle Compatibility

For interactive manual testing:

```bash
# 1. Initialize a test database in Oracle mode
export PATH=/usr/local/ivorysql/bin:$PATH
initdb -D /tmp/test_oracle --auth=trust -m oracle

# 2. Start the server
pg_ctl -D /tmp/test_oracle -l /tmp/test_oracle/logfile start

# 3. Create a test database
createdb testdb

# 4. Connect (use port 1521 for Oracle mode)
psql -h localhost -p 1521 -d testdb

# 5. Stop when done
pg_ctl -D /tmp/test_oracle stop -m fast
```

## Notes

- Tests must be built first (run `/ivorysql:build` or `make install`)
- Oracle compatibility tests use `initdb -m oracle` for proper Oracle mode
- `contrib/ivorysql_ora` module specifically requires Oracle compatibility mode
- Tests create temporary databases and data directories
- The `oracle-check` and `oracle-pg-check` targets set `INITDB_TEMPLATE` to an Oracle-mode template

## See Also

- `references/testing.md` - Detailed testing guide
- `/ivorysql:build` - Build before running tests
- `/ivorysql:commit` - Commit after tests pass
