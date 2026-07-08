# OpenSeat

OpenSeat monitors TSU Banner course registration pages and sends an alert when a full class section opens up.

## Why I Built This

In the past, while trying to register for online classes I needed to graduate on time, I ran into issues with either time conflicts or classes filling up quickly. During Spring 2026 and Summer I 2026, I was lucky enough to get into classes I needed because someone either dropped the course or was dropped from it at the last minute.

I was able to register for those classes the day they started because I kept manually checking to see if a seat had opened. I realized how tedious that process was and thought it could be automated.

I built OpenSeat so students can be notified when a full course gains an available seat, instead of constantly refreshing the same registration page. Getting into a class you need should not have to depend on luck.

## How It Works

```text
TSU Banner page → parser → SQLite state → comparison logic → ntfy alert → logs
```

OpenSeat uses the term and CRN for each watched class section to build the TSU Banner detail URL and fetch the public course page. It parses the seating table, loads the previous seat count from SQLite, compares the previous remaining seats to the current remaining seats, and then saves the latest state after the check.

If a section previously had 0 seats and now has more than 0, OpenSeat sends an ntfy alert. Each run is also logged so the checks, changes, notifications, and failures can be reviewed later.

## Key Design Decisions

* I use `term + crn` to identify a section instead of only using CRN because CRNs can repeat across different terms.
* The first time OpenSeat checks a section, it saves a baseline instead of sending an alert. That prevents false alerts when the script has no previous data yet.
* `None` and `0` are treated differently. `None` means OpenSeat has never checked that section before. `0` means it checked before and the class was full.
* OpenSeat only sends a notification when remaining seats go from `0` to a positive number because that is the actual moment a full class opens up.
* The current state is saved after a notification succeeds. If the notification fails, the old state stays in the database so the next run can try to alert again instead of silently missing the opening.

## Example Log Output

```text
2026-07-07 23:04:40 - INFO - openseat - event=watchlist_loaded path=watchlist.json sections=2
2026-07-07 23:04:40 - INFO - openseat - event=run_started sections=2
2026-07-07 23:04:41 - INFO - openseat - event=no_change course=CS 120-01 title='Introduction to Programming using C++' term=202710 crn=14402 previous_remaining=9 current_remaining=9 capacity=35 actual=26
2026-07-07 23:04:42 - INFO - openseat - event=no_change course=COSC 1145L-01 title='Comp. Program. in Python Lab' term=202710 crn=14401 previous_remaining=23 current_remaining=23 capacity=30 actual=7
2026-07-07 23:04:42 - INFO - openseat - event=run_finished
```

## Setup

1. Clone the repo.

```bash
git clone https://github.com/doitformyset/OpenSeat.git
cd OpenSeat
```

2. Create and activate a virtual environment.

```bash
python -m venv .venv
```

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Set your ntfy topic as an environment variable.

OpenSeat uses [ntfy](https://ntfy.sh/) for push notifications. To use it, install the ntfy app or use the ntfy web app, subscribe to a topic name you choose, and use that same topic name for `OPENSEAT_NTFY_TOPIC`.

Choose a topic name that is hard to guess. Anyone who knows the topic name can publish messages to it on the public ntfy.sh service.

PowerShell:

```powershell
$env:OPENSEAT_NTFY_TOPIC="your-random-topic-name"
```

5. Create your watchlist.

Copy the example watchlist file.

```powershell
Copy-Item watchlist.example.json watchlist.json
```

Edit `watchlist.json` with the sections you want to monitor. Each watched section needs a `term` and `crn`, which can be found from TSU Banner's class schedule search.

Example:

```json
[
  {
    "term": "202710",
    "crn": "14402",
    "course": "CS 120",
    "section": "01",
    "title": "Introduction to Programming using C++"
  }
]
```

`term` and `crn` are required. `course`, `section`, and `title` are optional labels used for cleaner logs and notifications.

6. Run the monitor.

```bash
python monitor.py
```

## Roadmap

* Add support for additional Banner-based schools
* Explore HCC support, which may require Playwright because HCC uses PeopleSoft instead of the same Banner page flow
* Deploy OpenSeat on a Linux VM or home lab with cron
* Explore self-hosted ntfy for notifications
