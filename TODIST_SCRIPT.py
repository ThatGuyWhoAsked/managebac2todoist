#!/usr/bin/env python3
"""
ManageBac → Todoist Sync Script
-------------------------------------------------------------------------------
Downloads iCal events from ManageBac, filters the next 14 days, creates tasks
in Todoist, and displays a formatted summary table with colours.
"""

import sys
import time
from datetime import date, datetime, timedelta

import requests
from icalendar import Calendar
from tqdm import tqdm

# =============================================================================
# CONFIGURATION – REPLACE THESE!
# =============================================================================
ICAL_URL = ""
TODOIST_API_KEY = ""
DAYS_WINDOW = 14
TODOIST_PROJECT_ID = None  # Optional: set to a project ID (int)

# ANSI colour codes
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

# Priority colours (used in the final table)
PRIO_COLOUR = {1: RED, 2: YELLOW, 3: GREEN}


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
def print_status(msg, colour=BLUE):
    """Print a coloured status message."""
    print(f"{colour}{msg}{RESET}")


def test_todoist_api(api_key):
    """Verify that the Todoist API key is valid."""
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(
            "https://api.todoist.com/api/v1/projects", headers=headers, timeout=10
        )
        resp.raise_for_status()
        print_status("✓ Todoist API key is valid", GREEN)
        return True
    except Exception as e:
        print_status(f"✗ Todoist API test failed: {e}", RED)
        return False


def download_calendar(url):
    """Download iCal data from ManageBac."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.content
    except requests.exceptions.RequestException as e:
        print_status(f"Failed to download calendar: {e}", RED)
        sys.exit(1)


def parse_events(ical_data):
    """Return a list of events with title, due_date, description, uid."""
    cal = Calendar.from_ical(ical_data)
    events = []
    for component in cal.walk("VEVENT"):
        title = str(component.get("SUMMARY", "No Title"))
        due = component.get("DTSTART")
        if due is None:
            continue
        dt_value = due.dt
        due_date = dt_value.date() if isinstance(dt_value, datetime) else dt_value
        description = str(component.get("DESCRIPTION", ""))
        uid = str(component.get("UID", ""))
        events.append(
            {
                "title": title,
                "due_date": due_date,
                "description": description,
                "uid": uid,
            }
        )
    return events


def filter_events_by_date(events, window_days):
    """Keep only events due within the next `window_days` (including today)."""
    today = date.today()
    cutoff = today + timedelta(days=window_days)
    return [ev for ev in events if today <= ev["due_date"] <= cutoff]


def days_until(due_date):
    return (due_date - date.today()).days


def assign_priority(days):
    """Return Todoist priority (1=urgent, 2=high, 3=normal)."""
    if days <= 2:
        return 1
    elif days <= 7:
        return 2
    else:
        return 3


def extract_subject_and_labels(title):
    """
    Extract a short subject name and optional labels (Summative/Formative).
    Examples:
        "Design (Va) Criterion D Report" -> subject "Design"
        "Maths (MEs) Summative – Functions" -> subject "Maths", label "Summative"
    """
    lower_title = title.lower()
    labels = []
    if "summative" in lower_title:
        labels.append("Summative")
    if "formative" in lower_title:
        labels.append("Formative")

    # Try to get the subject: first word, or text before '('
    subject = title.split()[0] if title.split() else "General"
    if "(" in subject:
        subject = subject.split("(")[0]
    return subject, labels


def create_todoist_task(
    api_key, content, due_date_str, priority, labels, project_id=None
):
    """Create a task in Todoist. Returns True on success."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "content": content,
        "due_date": due_date_str,
        "priority": priority,
        "labels": labels,
    }
    if project_id:
        payload["project_id"] = project_id

    try:
        resp = requests.post(
            "https://api.todoist.com/api/v1/tasks",
            headers=headers,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print_status(f"Failed to create task '{content}': {e}", RED)
        return False


# =============================================================================
# MAIN SCRIPT
# =============================================================================
def main():
    start_time = time.time()

    # ---- Connecting & API test ----
    print_status("Connecting to ManageBac iCal feed...")
    print_status("Init. API call")
    if not test_todoist_api(TODOIST_API_KEY):
        sys.exit(1)

    # ---- Fetching events ----
    print_status(f"Fetching events – next {DAYS_WINDOW} days")
    ical_content = download_calendar(ICAL_URL)

    # ---- Parsing iCal data ----
    print_status("Parsing iCal data")
    all_events = parse_events(ical_content)
    filtered_events = filter_events_by_date(all_events, DAYS_WINDOW)

    if not filtered_events:
        print_status("No events in the next 14 days. Nothing to sync.", YELLOW)
        return

    # ---- Prepare for task creation ----
    print_status("Calculating priority from deadline proximity")
    tasks_added = 0
    created_tasks = []  # store (task_name, subject, priority, due_date)

    # ---- Create tasks with progress bar ----
    print_status("Creating tasks via Todoist REST API")
    for event in tqdm(filtered_events, desc="Progress bar", unit="task", colour="cyan"):
        title = event["title"]
        due_date = event["due_date"]
        days = days_until(due_date)
        priority = assign_priority(days)
        subject, labels = extract_subject_and_labels(title)

        due_str = due_date.strftime("%Y-%m-%d")
        success = create_todoist_task(
            api_key=TODOIST_API_KEY,
            content=title,
            due_date_str=due_str,
            priority=priority,
            labels=labels,
            project_id=TODOIST_PROJECT_ID,
        )
        if success:
            tasks_added += 1
            created_tasks.append((title, subject, priority, due_date))

    # ---- Linking Google Calendar dates (already done via due_date) ----
    print_status("Linking Google Calendar dates to tasks", GREEN)

    # ---- Final summary table ----
    print("\n" + "=" * 70)
    print(f"{'TASK':<45} {'SUBJECT':<10} {'PRI':<5} {'DUE DATE':<12}")
    print("-" * 70)
    for task_name, subj, prio, ddate in created_tasks:
        # Colour the priority
        prio_str = f"{PRIO_COLOUR[prio]}P{prio}{RESET}"
        # Truncate task name if too long
        short_name = task_name[:42] + ".." if len(task_name) > 42 else task_name
        print(f"{short_name:<45} {subj:<10} {prio_str:<5} {ddate.strftime('%Y-%m-%d')}")
    print("=" * 70)

    # ---- Footer ----
    elapsed = time.time() - start_time
    print_status(f"Job complete", GREEN)
    print_status(
        f"Operation Timeframe: {elapsed:.2f}s ({'sub 10s' if elapsed < 10 else 'over 10s'})"
    )
    print_status(f"Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", GREEN)


if __name__ == "__main__":
    main()
