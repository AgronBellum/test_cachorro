import json
from datetime import datetime, date, timedelta

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BASE_URL = "https://mi.tv/br/async/channel/globo-rbs-tv-poa"


def scrape_day(url, target_date):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    programs = []

    items = soup.select("ul.broadcasts li")

    for li in items:
        # ignora propaganda
        if "native" in li.get("class", []):
            continue

        time_el = li.select_one(".time")
        title_el = li.select_one("h2")
        desc_el = li.select_one(".synopsis")

        if not time_el or not title_el:
            continue

        time_str = time_el.get_text(strip=True)
        title = title_el.get_text(strip=True)
        desc = desc_el.get_text(strip=True) if desc_el else ""

        try:
            h, m = map(int, time_str.split(":"))
        except:
            continue

        dt = datetime(target_date.year, target_date.month, target_date.day, h, m)

        programs.append({
            "desc": desc,
            "start_date": dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
            "title": title
        })

    return programs


def build():
    today = date.today()
    tomorrow = today + timedelta(days=1)

    all_programs = []

    # HOJE
    all_programs.extend(scrape_day(
        f"{BASE_URL}/-180",
        today
    ))

    # AMANHÃ
    all_programs.extend(scrape_day(
        f"{BASE_URL}/amanha",
        tomorrow
    ))

    all_programs.sort(key=lambda x: x["start_date"])

    return {
        "end_date": all_programs[-1]["start_date"][:10],
        "name": "Globo RBS TV POA",
        "provider": "mi.tv",
        "epg_list": all_programs,
        "start_date": all_programs[0]["start_date"][:10]
    }


def save(data):
    with open("RS_BR.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    data = build()
    save(data)

    print(f"OK - {len(data['epg_list'])} programas")
    print(f"Periodo: {data['start_date']} ate {data['end_date']}")
