---
description: Build IvorySQL with verification (local mode)
argument-hint: [--clean] [--verify] [--target TARGET] [--jobs JOBS]
allowed-tools: [Bash]
---

# /ivorysql:build

Build and install IvorySQL with optional verification.

## Usage

```bash
# Standard build (configure + make + install)
/ivorysql:build

# Clean build (removes old artifacts first)
/ivorysql:build --clean

# Build with verification (checks installed files)
/ivorysql:build --verify

# Build specific target
/ivorysql:build --target contrib/ivorysql_ora

# Full clean build with verification
/ivorysql:build --clean --verify
```

## Arguments

| Argument | Short | Required | Description |
|----------|-------|----------|-------------|
| `--clean` | `-c` | No | Run `make clean` before building |
| `--verify` | `-v` | No | Verify installed files are newer than sources |
| `--target` | `-t` | No | Build specific target (e.g., `contrib/ivorysql_ora`) |
| `--jobs` | `-j` | No | Number of parallel jobs (default: $(nproc)) |

## Prerequisites

Builds directly on your host system. Requires build dependencies installed.

**Ubuntu/Debian:**
```bash
sudo apt install build-essential libreadline-dev zlib1g-dev flex bison libxml2-dev libxslt-dev libssl-dev libxml2-utils xsltproc ccache pkg-config
```

**Fedora/RHEL:**
```bash
sudo dnf install make gcc flex bison readline-devel zlib-devel libxml2-devel libxslt-devel openssl-devel libxml2-utils xsltproc ccache pkgconf
```

## Configure

First time configuration (if `Makefile` doesn't exist):

**For development:**
```bash
./configure \
  --prefix=$PWD/inst \
  --enable-cassert --enable-debug --enable-rpath --with-tcl \
  --with-python --with-gssapi --with-pam --with-ldap \
  --with-openssl --with-libedit-preferred --with-uuid=e2fs \
  --with-ossp-uuid --with-libxml --with-libxslt --with-perl \
  --with-icu --with-libnuma --enable-injection-points
```

**For testing (includes --enable-tap-tests and --prefix):**
```bash
./configure \
  --prefix=$PWD/inst \
  --enable-cassert --enable-debug --enable-tap-tests --enable-rpath \
  --with-tcl --with-python --with-gssapi --with-pam --with-ldap \
  --with-openssl --with-libedit-preferred --with-uuid=e2fs \
  --with-ossp-uuid --with-libxml --with-libxslt --with-perl \
  --with-icu --with-libnuma --enable-injection-points
```

## Behavior

### 1. Configure (if needed)

Checks if `Makefile` exists. If not, runs configure with development flags.

### 2. Clean (if --clean)

```bash
# If --target specified
cd <target> && make clean

# Otherwise
make clean
```

### 3. Build

```bash
# If --target specified
cd <target> && make -j$(nproc)

# Otherwise
make -j$(nproc)
```

### 4. Install

```bash
# If --target specified
cd <target> && make install

# Otherwise
make install
```

### 5. Verify (if --verify)

**CRITICAL:** Verifies that installed files are actually newer than source files.

```bash
# Compare timestamps
stat -c '%Y %n' src/backend/main.c
stat -c '%Y %n' /usr/local/ivorysql/bin/postgres
```

If installed files are older, automatically runs:
```bash
cd <target> && make clean && make && make install
```

## Build Targets

| Target | Description |
|--------|-------------|
| (none) | Build entire project from root |
| `src/bin/initdb` | Build initdb utility |
| `src/bin/psql` | Build psql client |
| `src/backend` | Build PostgreSQL backend |
| `src/pl/plisql` | Build PL/iSQL language |
| `contrib/ivorysql_ora` | Build Oracle compatibility extension |
| `contrib/<module>` | Build specific contrib module |

## Verification Process

### Why Verification is Needed

The make system uses file timestamps. If timestamps are stale (from git checkout, file copies, etc.), `make install` may copy old files instead of new builds.

### Common Targets Requiring Verification

| Installed File | Source File | Install Path |
|----------------|-------------|--------------|
| `bin/postgres` | `src/backend/*.c` | `/usr/local/ivorysql/bin/` (local) |
| `bin/initdb` | `src/bin/initdb/*.c` | `/usr/local/ivorysql/bin/` (local) |
| `lib/plisql.so` | `src/pl/plisql/src/*.c` | `/usr/local/ivorysql/lib/` (local) |
| `share/extension/*.sql` | `src/pl/plisql/src/*.sql` | `/usr/local/ivorysql/share/` (local) |

## Examples

```bash
# Full clean build
/ivorysql:build --clean

# Rebuild specific target with verification
/ivorysql:build --target src/pl/plisql/src --verify

# After editing contrib module
/ivorysql:build --target contrib/ivorysql_ora --clean --verify
```

## Return Format

```
Build Status: Success
Duration: 2m 34s
Files Built: 142
Files Installed: 89

Verification:
- /usr/local/ivorysql/bin/postgres: OK
- /usr/local/ivorysql/bin/initdb: OK
- /usr/local/ivorysql/lib/plisql.so: OK
```

## Configuration

Uses settings from `.claude/ivorysql-dev.local.md`:

```json
{
  "install_prefix": "/usr/local/ivorysql",
  "configure_flags": "--enable-debug --enable-cassert --with-uuid=e2fs --with-libxml",
  "default_jobs": 0
}
```

**Note:** `default_jobs: 0` means use `$(nproc)`.

## Exit Conditions

**Success:**
- Build completes without errors
- All files installed
- Verification passes (if enabled)

**Failure:**
- Dependencies not installed
- Configure fails
- Compile errors detected
- Install fails

**Verification Failed:**
- Automatically triggers clean rebuild
- Returns success if rebuild works
- Returns failure if rebuild also fails

## Troubleshooting

### Dependencies Missing

```bash
# Ubuntu/Debian
sudo apt install build-essential libreadline-dev zlib1g-dev flex bison libxml2-dev libxslt-dev libssl-dev libxml2-utils xsltproc ccache

# Check for specific errors
./configure --help
```

### Permission Denied on Install

```bash
# Need sudo for /usr/local/ivorysql
sudo make install

# Or use different prefix
./configure --prefix=$HOME/ivorysql
```

### Build Fails with "Timestamps Out of Order"

```bash
/ivorysql:build --clean --verify
```

### Extension SQL Not Updated

```bash
cd contrib/ivorysql_ora
rm -f /usr/local/ivorysql/share/postgresql/extension/ivorysql_ora--1.0.sql
make clean && make && sudo make install
```

## Build Performance

| Build Type | Time | Notes |
|------------|------|-------|
| Incremental | 20s - 1m | Only changed files |
| Clean | 3m - 10m | Entire project |
| Single target | 5s - 30s | Specific module |

## Setting Up Build Environment

### First Time Setup

```bash
# 1. Install dependencies (Ubuntu/Debian)
sudo apt install -y build-essential libreadline-dev zlib1g-dev \
  flex bison libxml2-dev libxslt-dev libssl-dev \
  libxml2-utils xsltproc ccache pkg-config git

# 2. Configure (if not already done)
./configure --prefix=/usr/local/ivorysql --enable-debug --enable-cassert

# 3. Build
make -j$(nproc)

# 4. Install (may need sudo)
sudo make install

# 5. Add to PATH (optional)
echo 'export PATH=/usr/local/ivorysql/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### Alternative: User Directory Install

```bash
# Install in home directory (no sudo needed)
./configure --prefix=$HOME/ivorysql --enable-debug --enable-cassert
make -j$(nproc)
make install

# Add to PATH
echo 'export PATH=$HOME/ivorysql/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

## Notes

- Use `--verify` after fixing bugs to ensure changes are applied
- Use `--clean` when changing build configuration
- Use `--target` for faster rebuilds of specific modules

## See Also

- `references/build.md` - Detailed build guide
- `/ivorysql:test` - Run tests after building
- `/ivorysql:commit` - Commit after successful build and test
