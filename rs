import json
import re
from datetime import datetime, date, timedelta

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
}


# Mapeia os IDs das tabelas para os dias da semana (0=Segunda, 6=Domingo)
DIA_MAP = {
    "SEG": 0,
    "TER": 1,
    "QUA": 2,
    "QUI": 3,
    "SEX": 4,
    "SAB": 5,
    "DOM": 6,
}


def clean_title(title: str) -> str | None:
    if not title:
        return None
    title = title.strip()
    if re.fullmatch(r"\(\d{1,2}/\d{1,2}\)", title):
        return None
    if not re.search(r"[A-Za-zÀ-ÿ]", title):
        return None
    return title


def scrape():
    url = "https://clicrbs.com.br/especial/rs/rbstvrs/58,508,0,Programacao.html"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    programs = []

    tables = soup.find_all("table", class_="tabela-programacao")
    for table in tables:
        day_id = table.get("id", "")
        if day_id not in DIA_MAP:
            continue

        weekday = DIA_MAP[day_id]

        for row in table.find_all("tr"):
            time_cell = row.find("td", class_="hora")
            if not time_cell:
                continue

            time_str = time_cell.get_text(strip=True)
            if not re.match(r"^\d{1,2}:\d{2}$", time_str):
                continue

            title_cell = None
            for td in row.find_all("td"):
                classes = td.get("class", [])
                if "hora" in classes or "space" in classes:
                    continue
                title_cell = td
                break

            if not title_cell:
                continue

            title = clean_title(title_cell.get_text(strip=True))
            if not title:
                continue

            programs.append({
                "weekday": weekday,
                "time": time_str,
                "title": title
            })

    print(f"📺 Programas válidos: {len(programs)}")
    for p in programs[:5]:
        print(f"   [{p['weekday']}] {p['time']} - {p['title']}")

    return programs


def calcular_datas(today: date, weekday: int) -> list[date]:
    """
    Retorna as datas REAIS para esse dia da semana:
    - A data da semana atual (passada, presente ou futura)
    - A data da próxima semana
    """
    # Dias até o próximo dia da semana (0=seg, 6=dom)
    # Se hoje é domingo (6) e queremos segunda (0): (0 - 6) % 7 = 1 dia à frente
    days_ahead = (weekday - today.weekday()) % 7
    data_esta_semana = today + timedelta(days=days_ahead)

    # Próxima semana
    data_prox_semana = data_esta_semana + timedelta(days=7)

    return [data_esta_semana, data_prox_semana]


def build(today: date):
    all_programs = []
    progs = scrape()

    for p in progs:
        datas = calcular_datas(today, p["weekday"])

        for prog_date in datas:
            h, m = map(int, p["time"].split(":"))
            dt = datetime(prog_date.year, prog_date.month, prog_date.day, h, m)

            all_programs.append({
                "desc": "",
                "start_date": dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                "title": p["title"]
            })

    all_programs.sort(key=lambda x: x["start_date"])

    if not all_programs:
        start_date = today.strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        start_date = all_programs[0]["start_date"][:10]
        end_date = all_programs[-1]["start_date"][:10]

    return {
        "end_date": end_date,
        "name": "RBS TV RS",
        "provider": "clicrbs.com.br",
        "epg_list": all_programs,
        "start_date": start_date
    }


def save(data):
    with open("RS_BR.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    today = date.today()

    data = build(today)
    save(data)

    print(f"✅ OK - {len(data['epg_list'])} programas")
    print(f"📅 Período: {data['start_date']} até {data['end_date']}")
