# What is ivorysql_ora?

TODO 

# How do I build the extensions?

TODO

# Updating NUMBER default output

Version 1.1 removes insignificant fractional trailing zeros from the default
text output of `sys.number`. Column precision, scale, rounding and binary output
are unchanged. Explicit number format models still control `TO_CHAR` output.

After installing the updated library and SQL scripts, restart the server to
load the new library, then run this command in each existing database:

```sql
ALTER EXTENSION ivorysql_ora UPDATE TO '1.1';
```

New clusters automatically install the default version, 1.1. Existing expression
indexes or persisted expressions that depend on NUMBER's old text representation
need to be rebuilt or refreshed when upgrading.
