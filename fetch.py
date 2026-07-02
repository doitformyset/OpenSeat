import requests
from bs4 import BeautifulSoup


def get_seat_availability(term, crn):

    url = f"https://ssb-prod.ec.tsu.edu/PROD/bwckschd.p_disp_detail_sched?term_in={term}&crn_in={crn}"

    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch data from {url}. Status code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'html.parser')

    seat_table = soup.find(
    'table', 
    summary="This layout table is used to present the seating numbers."
    )

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

    capacity, actual, remaining = get_seat_availability(term, crn)

    print("Course:", f"{course}-{section_num}: {title}")
    print("Term:", term)
    print("CRN:", crn)
    print("Capacity:", capacity)
    print("Actual:", actual)
    print("Remaining:", remaining)
    print("-" * 30)