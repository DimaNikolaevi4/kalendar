# AI Orchestration

How to set up an AI agent on a new machine in 5 minutes.

1. Clone the repository.
2. Copy templates/machine_profile.example.json to machine_profile.json and fill in real values. The file is gitignored and must never be committed.
3. Create the global gitignore at USERPROFILE\.gitignore_global with the local-secrets block (machine_profile.json, .env, local/tokens.json, local/*.pem, *.local).
4. Run prompt 03-morning-sync.md to load the current plan context.
5. Review prompt 04-stop-hallucination.md rules before answering questions about code.
6. Daily ainow post at 12:00 — prompt 05-ainow-daily-12.md (задача `orch-ainow-boot-gptoss-1200`, первое включение машины, 06:00–11:00 МСК).

All AI agent methodology for this repository lives in this folder.
