# FOMC Minutes

This repository automatically stores Federal Reserve FOMC meeting minutes as JSON files. A scheduled GitHub Actions workflow scrapes the official Federal Reserve calendar and commits newly available minutes.

## One-time setup

1. Create a **public** GitHub repository named `fomc-minutes`.
2. Upload every file and folder from this package, preserving the folder structure.
3. In `fomc_minutes.py`, replace:

   ```python
   GITHUB_OWNER = "REPLACE_WITH_YOUR_GITHUB_USERNAME"
   ```

   with your GitHub username.
4. Commit the change to the `main` branch.
5. Go to **Settings > Actions > General**.
6. Ensure GitHub Actions is enabled.
7. Under **Workflow permissions**, select **Read and write permissions** and save.
8. Go to **Actions > Update FOMC minutes > Run workflow** and run it on `main`.
9. Confirm JSON files appear in the `minutes` directory.

## Recipient installation

```python
%pip install requests beautifulsoup4
```

## Pull a specific meeting

```python
from fomc_minutes import pull_fomc_minutes

minutes = pull_fomc_minutes(
    meeting_date="2026-07-29",
    save_path="fomc_minutes_july_2026.txt",
)

print(minutes[:3000])
```

## Pull the latest stored minutes

```python
from fomc_minutes import pull_latest_fomc_minutes

minutes = pull_latest_fomc_minutes(
    save_path="latest_fomc_minutes.txt",
)

print(minutes[:3000])
```

## Repository structure

```text
fomc-minutes/
├── .github/
│   └── workflows/
│       └── update_minutes.yml
├── minutes/
│   └── .gitkeep
├── .gitignore
├── README.md
├── fomc_minutes.py
└── requirements.txt
```

## Notes

- Normal users read minute files through `api.github.com`.
- The scheduled workflow performs the official Federal Reserve scraping on GitHub-hosted infrastructure.
- The workflow can also be run manually from the repository's Actions tab.
- Keep the repository public if recipients should read it without GitHub authentication.
