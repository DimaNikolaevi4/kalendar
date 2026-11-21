# Environment Rules

- OS: Windows, PowerShell 5.1.
- Forbidden: &&, ||, base64, bash-style head, tail, ls, and redirect with 2>/dev/null.
- Use only ; and if/else as command separators.
- FAIL-FAST: if the exit code is not 0 and it is not a pipeline artifact, stop and show the error.
