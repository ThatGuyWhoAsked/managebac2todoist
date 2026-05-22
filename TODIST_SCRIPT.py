#!/usr/bin/env python3
"""ManageBac → Todoist Sync Script"""

import sys
import time
from datetime import date, datetime, timedelta

import requests
from icalendar import Calendar
from tqdm import tqdm

# ── Configuration ──────────────────────────────────────────────────────────────
ICAL_URL = "https://ishamburg.managebac.com/student/events/token/47fdf330-2948-013c-d6a0-067aabdaee26.ics"
TODOIST_API_KEY = "c4f2fb96f28963ed4efc8a9f523b87fe9c81c57f"
DAYS_WINDOW = 14
PROJECT_ID = None

# ── Colours ────────────────────────────────────────────────────────────────────
RED, YELLOW, GREEN, BLUE, RESET = (
    "\033[91m",
    "\033[93m",
    "\033[92m",
    "\033[94m",
    "\033[0m",
)
PRIORITY_COLOUR = {1: RED, 2: YELLOW, 3: GREEN}


def print_status(message, colour=BLUE):
    print(f"{colour}{message}{RESET}")


# ── Todoist helpers ────────────────────────────────────────────────────────────
HEADERS = {
    "Authorization": f"Bearer {TODOIST_API_KEY}",
    "Content-Type": "application/json",
}


def test_api():
    response = requests.get(
        "https://api.todoist.com/api/v1/projects", headers=HEADERS, timeout=10
    )
    if response.ok:
        print_status("✓ Todoist API key is valid", GREEN)
        return True
    print_status(f"✗ API test failed: {response.status_code}", RED)
    return False


def create_task(title, due_date, priority, labels):
    payload = {
        "content": title,
        "due_date": due_date,
        "priority": priority,
        "labels": labels,
    }
    if PROJECT_ID:
        payload["project_id"] = PROJECT_ID
    response = requests.post(
        "https://api.todoist.com/api/v1/tasks",
        headers=HEADERS,
        json=payload,
        timeout=10,
    )
    return response.ok


# ── Calendar helpers ───────────────────────────────────────────────────────────
def download_events():
    response = requests.get(ICAL_URL, timeout=15)
    if not response.ok:
        print_status("Failed to download calendar", RED)
        sys.exit(1)

    today = date.today()
    cutoff = today + timedelta(days=DAYS_WINDOW)
    events = []

    for component in Calendar.from_ical(response.content).walk("VEVENT"):
        due = component.get("DTSTART")
        if due is None:
            continue
        due_date = due.dt.date() if isinstance(due.dt, datetime) else due.dt
        if today <= due_date <= cutoff:
            events.append(
                {
                    "title": str(component.get("SUMMARY", "No Title")),
                    "due_date": due_date,
                }
            )

    return events


def get_priority(days_left):
    if days_left <= 2:
        return 1
    if days_left <= 7:
        return 2
    return 3


def get_labels(title):
    labels = []
    if "summative" in title.lower():
        labels.append("Summative")
    if "formative" in title.lower():
        labels.append("Formative")
    return labels


def get_subject(title):
    first_word = title.split()[0] if title else "General"
    return first_word.split("(")[0]


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    start = time.time()

    print_status("Connecting to ManageBac iCal feed...")
    if not test_api():
        sys.exit(1)

    print_status(f"Fetching events for the next {DAYS_WINDOW} days...")
    events = download_events()

    if not events:
        print_status("No upcoming events found. Nothing to sync.", YELLOW)
        return

    created_tasks = []
    for event in tqdm(events, desc="Creating tasks", unit="task", colour="cyan"):
        days_left = (event["due_date"] - date.today()).days
        priority = get_priority(days_left)
        labels = get_labels(event["title"])
        due_str = event["due_date"].strftime("%Y-%m-%d")

        if create_task(event["title"], due_str, priority, labels):
            created_tasks.append(
                (
                    event["title"],
                    get_subject(event["title"]),
                    priority,
                    event["due_date"],
                )
            )

    # Print summary table
    print("\n" + "=" * 70)
    print(f"{'TASK':<45} {'SUBJECT':<10} {'PRI':<5} {'DUE DATE'}")
    print("-" * 70)
    for title, subject, priority, due_date in created_tasks:
        short_title = title[:42] + ".." if len(title) > 42 else title
        priority_str = f"{PRIORITY_COLOUR[priority]}P{priority}{RESET}"
        print(
            f"{short_title:<45} {subject:<10} {priority_str:<5} {due_date.strftime('%Y-%m-%d')}"
        )
    print("=" * 70)

    elapsed = time.time() - start
    print_status(f"Done! Synced {len(created_tasks)} tasks in {elapsed:.2f}s", GREEN)
    print_status(f"Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", GREEN)


if __name__ == "__main__":
    main()
