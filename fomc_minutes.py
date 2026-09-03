"""FOMC minutes reader and GitHub Actions updater.

Recipient usage:
    from fomc_minutes import pull_fomc_minutes, pull_latest_fomc_minutes
    text = pull_fomc_minutes("2026-07-29")

Repository updater usage (run by GitHub Actions):
    python fomc_minutes.py update

Dependencies:
    requests
    beautifulsoup4
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# IMPORTANT: Replace this once with your GitHub username before uploading.
GITHUB_OWNER = "will-j3ff"
GITHUB_REPOSITORY = "fomc-minutes"
GITHUB_BRANCH = "main"

GITHUB_API_ROOT = "https://api.github.com"
FED_BASE_URL = "https://www.federalreserve.gov"
FED_CALENDAR_URL = (
    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
)
MINUTES_DIRECTORY = Path("minutes")


def _create_session(github_token: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    retry_policy = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_policy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
    )
    if github_token:
        session.headers["Authorization"] = f"Bearer {github_token}"
    return session


def _normalise_date(date_value: str) -> str:
    return datetime.strptime(date_value, "%Y-%m-%d").strftime("%Y-%m-%d")


def _minutes_filename(meeting_date: str) -> str:
    return f"fomc_minutes_{_normalise_date(meeting_date)}.json"


def _minutes_repository_path(meeting_date: str) -> str:
    return f"minutes/{_minutes_filename(meeting_date)}"


def _validate_github_configuration() -> None:
    if GITHUB_OWNER == "REPLACE_WITH_YOUR_GITHUB_USERNAME":
        raise ValueError(
            "Open fomc_minutes.py and replace "
            "REPLACE_WITH_YOUR_GITHUB_USERNAME with the owner of the "
            "public GitHub repository."
        )


def _github_contents_url(repository_path: str) -> str:
    _validate_github_configuration()
    return (
        f"{GITHUB_API_ROOT}/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/"
        f"contents/{repository_path}?ref={GITHUB_BRANCH}"
    )


def _github_get_json(session: requests.Session, url: str) -> object:
    response = session.get(
        url,
        timeout=(20, 90),
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if response.status_code == 404:
        raise FileNotFoundError(f"GitHub resource not found: {url}")
    response.raise_for_status()
    return response.json()


def _download_github_file(session: requests.Session, repository_path: str) -> str:
    metadata = _github_get_json(session, _github_contents_url(repository_path))
    if not isinstance(metadata, dict):
        raise ValueError("GitHub returned unexpected file metadata.")

    encoded_content = metadata.get("content")
    encoding = metadata.get("encoding")
    if encoded_content and encoding == "base64":
        return base64.b64decode(encoded_content).decode("utf-8-sig")

    git_url = metadata.get("git_url")
    if not git_url:
        raise ValueError("GitHub returned neither inline content nor a blob URL.")

    blob = _github_get_json(session, git_url)
    if not isinstance(blob, dict):
        raise ValueError("GitHub returned unexpected blob metadata.")
    encoded_content = blob.get("content")
    encoding = blob.get("encoding")
    if not encoded_content or encoding != "base64":
        raise ValueError("GitHub blob did not contain Base64 file content.")
    return base64.b64decode(encoded_content).decode("utf-8-sig")


def pull_fomc_minutes(
    meeting_date: str,
    save_path: Optional[str] = None,
    return_metadata: bool = False,
) -> str | dict:
    """Return minutes for a specific meeting date from the public repository."""
    meeting_date = _normalise_date(meeting_date)
    session = _create_session()
    try:
        try:
            json_text = _download_github_file(
                session, _minutes_repository_path(meeting_date)
            )
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"No stored FOMC minutes were found for {meeting_date}. "
                "Confirm the meeting date and check that the repository's "
                "Update FOMC minutes workflow has completed successfully."
            ) from error
    finally:
        session.close()

    result = json.loads(json_text)
    minutes_text = str(result.get("text", "")).strip()
    if not minutes_text:
        raise ValueError("The stored minutes record contains no text.")

    if save_path:
        output_path = Path(save_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(minutes_text, encoding="utf-8")

    return result if return_metadata else minutes_text


def list_available_minutes() -> list[dict]:
    """List all meeting-minute records currently stored in the repository."""
    session = _create_session()
    try:
        items = _github_get_json(session, _github_contents_url("minutes"))
    finally:
        session.close()

    if not isinstance(items, list):
        raise ValueError("GitHub returned an unexpected minutes directory response.")

    pattern = re.compile(r"^fomc_minutes_(\d{4}-\d{2}-\d{2})\.json$")
    available = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("name", ""))
        match = pattern.match(filename)
        if match:
            available.append(
                {"meeting_date": match.group(1), "filename": filename}
            )
    return sorted(available, key=lambda item: item["meeting_date"], reverse=True)


def pull_latest_fomc_minutes(
    save_path: Optional[str] = None,
    return_metadata: bool = False,
) -> str | dict:
    """Return the latest meeting minutes currently stored in the repository."""
    available = list_available_minutes()
    if not available:
        raise FileNotFoundError("The repository does not contain any FOMC minutes.")
    return pull_fomc_minutes(
        available[0]["meeting_date"],
        save_path=save_path,
        return_metadata=return_metadata,
    )


def _download_html(
    session: requests.Session,
    url: str,
) -> str:
    """
    Download one Federal Reserve HTML page
    and decode it as UTF-8.
    """
    response = session.get(
        url,
        timeout=(30, 120),
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.content.decode(
        "utf-8"
    )


def _extract_meeting_date_from_url(url: str) -> Optional[str]:
    match = re.search(
        r"fomcminutes(\d{4})(\d{2})(\d{2})", url, flags=re.IGNORECASE
    )
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return _normalise_date(f"{year}-{month}-{day}")
    except ValueError:
        return None


def _extract_minutes_text(
    html: str,
) -> str:
    """
    Extract clean FOMC minutes text from Federal Reserve HTML.
    """
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    article = soup.find(
        "div",
        id="article",
    )

    if article is None:
        article = soup.find("main")

    if article is None:
        raise RuntimeError(
            "The Federal Reserve page loaded, but the "
            "minutes article could not be located."
        )

    # Remove browser-navigation links such as
    # "Return to text".
    for link in article.find_all("a"):
        if link.get_text(
            " ",
            strip=True,
        ).lower() == "return to text":
            link.decompose()

    # Remove inline footnote markers such as:
    #
    # <sup>2</sup>
    #
    # The actual footnote text at the bottom of the
    # document is retained.
    for sup in article.find_all("sup"):
        sup.decompose()

    blocks = []

    # Extract the document title.
    title = article.find("h3")

    if title is not None:
        title_text = title.get_text(
            " ",
            strip=True,
        )

        if title_text:
            blocks.append(
                title_text
            )

    # Extract ordinary prose and list items.
    #
    # <p> captures the main minutes text.
    # <li> captures policy-directive list items.
    for element in article.find_all(
        [
            "p",
            "li",
        ]
    ):
        text = element.get_text(
            " ",
            strip=True,
        )

        if text:
            blocks.append(
                text
            )

    minutes_text = "\n\n".join(
        blocks
    ).strip()

    if not minutes_text:
        raise RuntimeError(
            "The Federal Reserve minutes page contained no text."
        )

    if (
        "minutes of the federal open market committee"
        not in minutes_text.lower()
    ):
        raise RuntimeError(
            "The page does not appear to contain FOMC minutes."
        )

    return minutes_text


def _find_minutes_links(calendar_html: str) -> list[str]:
    soup = BeautifulSoup(calendar_html, "html.parser")
    links = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        href_lower = href.lower()
        if "fomcminutes" in href_lower and href_lower.endswith((".htm", ".html")):
            links.add(urljoin(FED_BASE_URL, href))
    return sorted(links)


def _save_minutes_record(
    meeting_date: str,
    source_url: str,
    minutes_text: str,
) -> Path:
    MINUTES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_path = MINUTES_DIRECTORY / _minutes_filename(meeting_date)
    record = {
        "meeting_date": meeting_date,
        "type": "Minute",
        "source": "Federal Reserve",
        "source_url": source_url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "text": minutes_text,
    }
    output_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def update_repository_minutes() -> int:
    """Scrape Fed calendar and create any missing minutes JSON files."""
    session = _create_session()
    try:
        calendar_html = _download_html(session, FED_CALENDAR_URL)
        minutes_links = _find_minutes_links(calendar_html)
        if not minutes_links:
            raise RuntimeError("No FOMC minutes links were found on the Fed calendar.")

        created_count = 0
        for minutes_url in minutes_links:
            meeting_date = _extract_meeting_date_from_url(minutes_url)
            if meeting_date is None:
                print(f"Skipped unrecognised URL: {minutes_url}")
                continue

            output_path = MINUTES_DIRECTORY / _minutes_filename(meeting_date)
            if output_path.exists():
                continue

            print(f"Downloading {meeting_date}: {minutes_url}")
            minutes_html = _download_html(session, minutes_url)
            minutes_text = _extract_minutes_text(minutes_html)
            saved_path = _save_minutes_record(
                meeting_date, minutes_url, minutes_text
            )
            print(f"Saved: {saved_path}")
            created_count += 1

        return created_count
    finally:
        session.close()


def _run_command_line() -> None:
    parser = argparse.ArgumentParser(description="FOMC minutes utility")
    parser.add_argument("command", choices=["update", "latest", "pull"])
    parser.add_argument("--meeting-date", default=None)
    parser.add_argument("--save", default=None)
    arguments = parser.parse_args()

    if arguments.command == "update":
        count = update_repository_minutes()
        print(f"New minutes files created: {count}")
    elif arguments.command == "latest":
        result = pull_latest_fomc_minutes(
            save_path=arguments.save, return_metadata=True
        )
        print(f"Meeting date: {result['meeting_date']}")
        print(f"Characters: {len(result['text']):,}")
    else:
        if not arguments.meeting_date:
            raise ValueError("--meeting-date is required for the pull command.")
        result = pull_fomc_minutes(
            arguments.meeting_date,
            save_path=arguments.save,
            return_metadata=True,
        )
        print(f"Meeting date: {result['meeting_date']}")
        print(f"Characters: {len(result['text']):,}")


if __name__ == "__main__":
    _run_command_line()
