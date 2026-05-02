import json
import re
import time
import random
from datetime import datetime, date, timedelta

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURAÇÃO DE "DISFARCE" ---
# Um Header real contém mais do que apenas o User-Agent.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/", # Simula que você veio do Google
    "DNT": "1", # Do Not Track
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

def clean_title(title: str) -> str | None:
    if not title: return None
    title = title.strip()
    if re.fullmatch(r"\(\d{1,2}/\d{1,2}\)", title): return None
    if not re.search(r"[A-Za-zÀ-ÿ]", title): return None
    return title

def get_session():
    """Cria uma sessão que mantém cookies e tenta reconectar em erros leves."""
    session = requests.Session()
    retry = Retry(
        total=3, 
        backoff_factor=2, # Espera 2s, 4s, 8s entre tentativas
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def scrape(session):
    url = "https://tvinside.com.br/programacao_tv/investigacao_discovery"
    
    # Simula um delay humano antes de acessar (entre 1 a 4 segundos)
    time.sleep(random.uniform(1.5, 4.2))
    
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Erro ao acessar: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    programs = []
    blocks = soup.select(".registro.programa_data")

    for b in blocks:
        time_tag = b.select_one("time")
        title_tag = b.select_one(".titulo")

        if not time_tag or not title_tag:
            continue

        time_str = time_tag.text.strip()
        title = clean_title(title_tag.text)

        if title:
            programs.append({"time": time_str, "title": title})

    return programs

def build(today: date):
    session = get_session()
    all_programs = []

    # Se você for pegar vários dias, o delay é CRUCIAL entre as requisições
    for offset in [0, 1]:
        day = today + timedelta(days=offset)
        print(f"🔍 Coletando dados para: {day.strftime('%d/%m/%Y')}...")
        
        progs = scrape(session)

        for p in progs:
            try:
                h, m = map(int, p["time"].split(":"))
                dt = datetime(day.year, day.month, day.day, h, m)
                all_programs.append({
                    "desc": "",
                    "start_date": dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                    "title": p["title"]
                })
            except ValueError:
                continue

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
    print(f"✅ Finalizado - {len(data['epg_list'])} programas salvos.")