import os
import sqlite3
from datetime import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
import json
import sys

import requests
from bs4 import BeautifulSoup


NTFY_TOPIC = os.getenv("OPENSEAT_NTFY_TOPIC")

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "openseat.log")

def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("openseat")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.handlers.clear()

    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )

    console_handler = logging.StreamHandler()

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

logger = setup_logger()


def load_watchlist(path="watchlist.json"):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

    except FileNotFoundError:
        logger.error("event=watchlist_missing path=%s", path)
        sys.exit(1)

    except json.JSONDecodeError as error:
        logger.error(
            "event=watchlist_json_invalid path=%s line=%s column=%s message=%s",
            path, 
            error.lineno, 
            error.colno, 
            error.msg,
        )
        sys.exit(1)

    if not isinstance(data, list):
        logger.error(
            "event=watchlist_structure_invalid path=%s expected=list actual=%s",
            path,
            type(data).__name__,
        )
        sys.exit(1)
    
    valid_entries = []
    seen = set()

    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            logger.error(
                "event=watchlist_entry_invalid index=%s reason=not_object actual=%s",
                index,
                type(entry).__name__,
            )
            continue

        missing_fields = []

        for field in ("term", "crn"):
            if not entry.get(field):
                missing_fields.append(field)

        if missing_fields:
            logger.error(
                "event=watchlist_entry_invalid index=%s missing=%s",
                index,
                ",".join(missing_fields),
            )
            continue

        term = str(entry["term"])
        crn = str(entry["crn"])

        key = (term, crn)

        if key in seen:
            logger.error(
                "event=watchlist_entry_duplicate index=%s term=%s crn=%s",
                index,
                term,
                crn,
            )
            continue

        seen.add(key)

        valid_entries.append(
            {
                "term": term,
                "crn": crn,
                "course": entry.get("course", "Unknown course"),
                "section": entry.get("section", "Unknown section"),
                "title": entry.get("title", "Unknown title"),
            }
        )

    if not valid_entries:
        logger.error("event=watchlist_empty path=%s valid_entries=0", path)
        sys.exit(1)
    
    logger.info(
        "event=watchlist_loaded path=%s sections=%s",
        path,
        len(valid_entries),
    )

    return valid_entries


def get_seat_availability(term, crn):

    url = f"https://ssb-prod.ec.tsu.edu/PROD/bwckschd.p_disp_detail_sched?term_in={term}&crn_in={crn}"

    headers = {
        "User-Agent": "OpenSeat/0.1 (student course availability monitor)"
    }

    response = requests.get(url, headers=headers, timeout=20)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch data from {url}. Status code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'html.parser')

    seat_table = soup.find(
        'table', 
        summary="This layout table is used to present the seating numbers."
    )

    if seat_table is None:
        raise Exception(f"No seating table found for term {term}, CRN {crn}.")

    rows = seat_table.find_all('tr')

    for row in rows:
        header = row.find('th')

        if header is None:
            continue

        label = header.get_text(strip=True)

        if label == "Seats":
            cells = row.find_all('td')

            capacity = int(cells[0].get_text(strip=True))
            actual = int(cells[1].get_text(strip=True))
            remaining = int(cells[2].get_text(strip=True))

            return capacity, actual, remaining

    raise Exception(f"No Seats row found for term {term}, CRN {crn}.")


def initialize_database():
    connection = sqlite3.connect("openseat.db")

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seat_state (
            term TEXT NOT NULL,
            crn TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            actual INTEGER NOT NULL,
            remaining INTEGER NOT NULL,
            last_checked TEXT NOT NULL,
            PRIMARY KEY (term, crn)
        )
""")
    connection.commit()
    connection.close()


def load_previous(term, crn):
    connection = sqlite3.connect("openseat.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT remaining
        FROM seat_state
        WHERE term = ? AND crn = ?
    """, (term, crn))

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None
    
    return row[0]


def save_current(term, crn, capacity, actual, remaining):
    connection = sqlite3.connect("openseat.db")
    cursor = connection.cursor()

    last_checked = datetime.now().isoformat(timespec="seconds")

    cursor.execute("""
        INSERT OR REPLACE INTO seat_state (
            term,
            crn,
            capacity,
            actual,
            remaining,
            last_checked
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (term, crn, capacity, actual, remaining, last_checked))
    
    connection.commit()
    connection.close()   


def notify(event_type, section, previous_remaining, current_remaining):
    if event_type != "seat_opened":
        return
    
    if not NTFY_TOPIC:
        raise RuntimeError(
            "OPENSEAT_NTFY_TOPIC is not set. " 
            "Set it in PowerShell with: "
            '$env:OPENSEAT_NTFY_TOPIC="your_topic"'
        )
    
    message = (
        f"Seat opened for {section['course']}-{section['section']}\n"
        f"{section['title']}\n"
        f"Term: {section['term']}\n"
        f"CRN: {section['crn']}\n"
        f"Remaining Seats: {previous_remaining} -> {current_remaining}"
    )
    
    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": "OpenSeat Alert",
            "Priority": "urgent",
            "Tags": "rotating_light",
        },
        timeout=20,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"ntfy notification failed with status code {response.status_code}: {response.text}"
        )
    
    logger.info(
        "event=notification_sent course=%s-%s term=%s crn=%s previous_remaining=%s current_remaining=%s",
        section['course'],
        section['section'],
        section['term'],
        section['crn'],
        previous_remaining,
        current_remaining,
    )


def main():
    initialize_database()

    watchlist = load_watchlist("watchlist.json")

    logger.info("event=run_started sections=%s", len(watchlist))

    for section in watchlist:
        term = section["term"]
        crn = section["crn"]
        course = section["course"]
        section_num = section["section"]
        title = section["title"]

        try:
            capacity, actual, remaining = get_seat_availability(term, crn)

            previous_remaining = load_previous(term, crn)

            if previous_remaining is None:
                logger.info(
                    "event=baseline_saved course=%s-%s title=%r term=%s crn=%s capacity=%s actual=%s remaining=%s",
                    course,
                    section_num,
                    title,
                    term,
                    crn,
                    capacity,
                    actual,
                    remaining,
                )
            elif previous_remaining == 0 and remaining > 0:
                logger.warning(
                    "event=seat_opened course=%s-%s title=%r term=%s crn=%s previous_remaining=%s current_remaining=%s capacity=%s actual=%s",
                    course,
                    section_num,
                    title,
                    term,
                    crn,
                    previous_remaining,
                    remaining,
                    capacity,
                    actual,
                )

                try:
                    notify("seat_opened", section, previous_remaining, remaining)
                except Exception:
                    logger.exception(
                        "event=notification_failed course=%s-%s title=%r term=%s crn=%s previous_remaining=%s current_remaining=%s", 
                        course,
                        section_num,
                        title,
                        term,
                        crn,
                        previous_remaining,
                        remaining,
                    )
                    continue
                
            elif previous_remaining > 0 and remaining == 0:
                logger.warning(
                    "event=section_filled course=%s-%s title=%r term=%s crn=%s previous_remaining=%s current_remaining=%s capacity=%s actual=%s",
                    course,
                    section_num,
                    title,
                    term,
                    crn,
                    previous_remaining,
                    remaining,
                    capacity,
                    actual,
                )


            else:
                logger.info(
                    "event=no_change course=%s-%s title=%r term=%s crn=%s previous_remaining=%s current_remaining=%s capacity=%s actual=%s",
                    course,
                    section_num,
                    title,
                    term,
                    crn,
                    previous_remaining,
                    remaining,
                    capacity,
                    actual,
                )
            save_current(term, crn, capacity, actual, remaining)


        except Exception:
            logger.exception(
                "event=check_failed course=%s-%s title=%r term=%s crn=%s",
                course,
                section_num,
                title,
                term,
                crn,
            )
            continue

    logger.info("event=run_finished")

if __name__ == "__main__":
    main()
