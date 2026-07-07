import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime


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

initialize_database()

watchlist = [
    {
        "term": "202710", 
        "crn": "14402", 
        "course": "CS 120",
        "section": "01",
        "title": "Introduction to Programming using C++"
    },
    {
        "term": "202710", 
        "crn": "14401",
        "course": "COSC 1145L",
        "section": "01",
        "title": "Comp. Program. in Python Lab"
    },
]

for section in watchlist:
    term = section["term"]
    crn = section["crn"]
    course = section["course"]
    section_num = section["section"]
    title = section["title"]

    try:
        capacity, actual, remaining = get_seat_availability(term, crn)

        previous_remaining = load_previous(term, crn)

        print("Course:", f"{course}-{section_num}: {title}")
        print("Term:", term)
        print("CRN:", crn)
        print("Capacity:", capacity)
        print("Actual:", actual)
        print("Remaining:", remaining)

        if previous_remaining is None:
            print("Status: First time checking this section. Saving baseline.")
        elif previous_remaining == 0 and remaining > 0:
            print("Status: SEAT OPENED!")
        elif previous_remaining > 0 and remaining == 0:
            print("Status: Section is now full.")
        else:
            print("Status: No alert-worthy change.")
        
        save_current(term, crn, capacity, actual, remaining)

        print("-" * 30)

    except Exception as error:

        print("Error checking section:")
        print("Course:", f"{course}-{section_num}: {title}")
        print("Term:", term)
        print("CRN:", crn)
        print("Error:", error)
        print("-" * 30)
        continue