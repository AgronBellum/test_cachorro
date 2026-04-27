import json
from datetime import datetime, timedelta, date

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

CHANNEL = "globo-rbs-tv-poa"


def fetch_day(day_offset=0):
    target_date = date.today() + timedelta(days=day_offset)

    url = f"http://api.mi.tv/v1/channels/{CHANNEL}/broadcasts"

    params = {
        "country": "br",
        "lang": "pt",
        "start": target_date.strftime("%Y-%m-%d"),
        "end": target_date.strftime("%Y-%m-%d"),
    }

    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()

    data = r.json()

    programs = []

    for item in data.get("broadcasts", []):
        start_ts = item.get("start_datetime")

        if not start_ts:
            continue

        dt = datetime.fromisoformat(start_ts.replace("Z", ""))

        programs.append({
            "desc": item.get("description") or "",
            "start_date": dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
            "title": item.get("title")
        })

    return programs


def build():
    all_programs = []

    # hoje + amanhã
    all_programs.extend(fetch_day(0))
    all_programs.extend(fetch_day(1))

    all_programs.sort(key=lambda x: x["start_date"])

    start_date = all_programs[0]["start_date"][:10]
    end_date = all_programs[-1]["start_date"][:10]

    return {
        "end_date": end_date,
        "name": "Globo RBS TV POA",
        "provider": "mi.tv",
        "epg_list": all_programs,
        "start_date": start_date
    }


def save(data):
    with open("RS_BR.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    data = build()
    save(data)

    print(f"OK - {len(data['epg_list'])} programas")
    print(f"Periodo: {data['start_date']} ate {data['end_date']}")
