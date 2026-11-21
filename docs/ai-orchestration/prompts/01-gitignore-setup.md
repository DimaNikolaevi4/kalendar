# Gitignore Setup

You are setting up git protection for local machine profiles and secrets.

Tasks:
1. Check if a global gitignore is configured: git config --global core.excludesfile
2. If not set, create USERPROFILE\.gitignore_global with the local-secrets block (machine_profile.json, .env, local/tokens.json, local/*.pem, *.local).
3. Add the same block to the repository root .gitignore if missing.
4. Verify with: git check-ignore -v machine_profile.json

Do not commit files that are properly ignored. Do not use git add -f to force-add ignored files.
