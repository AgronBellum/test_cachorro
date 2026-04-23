import json
import re
from datetime import datetime, date, timedelta

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "pt-BR,pt;q=0.9"
}


def clean_title(title: str) -> str | None:
    if not title:
        return None

    title = title.strip()

    # remove lixo tipo datas escondidas (caso escape)
    if re.fullmatch(r"\(\d{1,2}/\d{1,2}\)", title):
        return None

    if not re.search(r"[A-Za-zÀ-ÿ]", title):
        return None

    return title


def scrape():
    url = "https://tvinside.com.br/programacao_tv/investigacao_discovery"

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    programs = []

    # 🔥 PEGA SÓ OS BLOCOS REAIS DO SITE
    blocks = soup.select(".registro.programa_data")

    for b in blocks:
        time_tag = b.select_one("time")
        title_tag = b.select_one(".titulo")

        if not time_tag or not title_tag:
            continue

        time_str = time_tag.text.strip()
        title = clean_title(title_tag.text)

        if not title:
            continue

        programs.append({
            "time": time_str,
            "title": title
        })

    print(f"📺 Programas válidos: {len(programs)}")

    return programs


def build(today: date):
    all_programs = []

    for offset in [0, 1]:
        day = today + timedelta(days=offset)

        progs = scrape()

        for p in progs:
            h, m = map(int, p["time"].split(":"))

            dt = datetime(day.year, day.month, day.day, h, m)

            all_programs.append({
                "desc": "",
                "start_date": dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                "title": p["title"]
            })

    all_programs.sort(key=lambda x: x["start_date"])

    return {
        "end_date": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
        "name": "Discovery ID",
        "provider": "tvinside.com.br",
        "epg_list": all_programs,
        "start_date": today.strftime("%Y-%m-%d")
    }


def save(data):
    with open("ID_BR.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    today = date.today()

    data = build(today)
    save(data)

    print(f"✅ OK - {len(data['epg_list'])} programas")