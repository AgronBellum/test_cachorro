# epg_id.py
import json
import re
import sys
from datetime import datetime, date, timedelta

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def is_invalid_title(title: str) -> bool:
    """
    Retorna True se o título for apenas número, data, hora, ou padrões
    técnicos (episódio, temporada, etc.) sem nome de programa real.
    """
    t = title.strip()
    
    # Vazio ou muito curto
    if len(t) < 2:
        return True
    
    # Apenas número (incluindo com ponto, vírgula, espaço)
    if re.fullmatch(r'[\d\s.,]+', t):
        return True
    
    # Padrões de data: 2024-04-23, 23/04/2024, 23-04-2024, etc.
    if re.fullmatch(r'\d{1,4}[\-/]\d{1,2}[\-/]\d{1,4}', t):
        return True
    
    # Apenas hora: 06:00, 6:00
    if re.fullmatch(r'\d{1,2}:\d{2}', t):
        return True
    
    # Padrões tipo "S01E05", "E05", "T1", "3ª Temporada" sozinho
    if re.fullmatch(r'[Ss]\d+[Ee]\d+', t):
        return True
    if re.fullmatch(r'[Ee]\d+', t):
        return True
    if re.fullmatch(r'\d+[ªº°a]?\s*[Tt]emporada', t):
        return True
    if re.fullmatch(r'[Tt]\d+', t):
        return True
    
    # "Episódio X" ou "Ep. X" sozinho
    if re.fullmatch(r'[Ee]pis[oó]dio\s*\d+', t):
        return True
    if re.fullmatch(r'[Ee]p\.?\s*\d+', t):
        return True
    
    return False


def clean_title(raw_title: str) -> str | None:
    """
    Limpa e valida o título do programa.
    Retorna None se o título for inválido (número, data, etc.).
    """
    # Remove categorias como "; Séries/Reality Show"
    title = re.split(r'[;|•]', raw_title)[0].strip()
    
    # Remove sujeira comum
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Verifica se é inválido
    if is_invalid_title(title):
        return None
        
    return title


def scrape_tvinside(day_offset: int = 0):
    """
    day_offset: 0 = hoje, 1 = amanhã, etc.
    Retorna lista de dicts: [{"time": "06:00", "title": "..."}, ...]
    """
    base_url = "https://tvinside.com.br/programacao_tv/investigacao_discovery"
    
    url = base_url
    # TODO: se o site suportar data via query string, adicionar aqui

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Erro ao buscar tvinside: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    
    programs = []
    text = soup.get_text(separator="\n")
    
    # Regex melhorada: evita capturar intervalos "06:00 - 07:00" como título
    pattern = re.compile(r'^(\d{1,2}:\d{2})[.\s\-h]*(?!\d{1,2}:\d{2})(.+)$', re.MULTILINE)
    
    for match in pattern.finditer(text):
        time_str = match.group(1)
        raw_title = match.group(2).strip()
        
        title = clean_title(raw_title)
        if title is None:
            continue
            
        programs.append({
            "time": time_str,
            "title": title
        })

    # Remove duplicatas mantendo ordem
    seen = set()
    unique = []
    for p in programs:
        key = (p["time"], p["title"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    
    print(f"  📺 {len(unique)} programas encontrados (offset={day_offset})")
    for p in unique[:3]:
        print(f"     {p['time']} - {p['title']}")
    
    return unique


def build_epg(today: date):
    all_programs = []
    
    # Scrape hoje e amanhã
    for offset in [0, 1]:
        target_date = today + timedelta(days=offset)
        print(f"\n🔍 Buscando programação para {target_date}...")
        
        progs = scrape_tvinside(offset)
        
        for prog in progs:
            try:
                hour, minute = map(int, prog['time'].split(':'))
                start_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, 0)
                all_programs.append({
                    "desc": "",
                    "start_date": start_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                    "title": prog['title']
                })
            except (ValueError, KeyError):
                continue
    
    all_programs.sort(key=lambda x: x['start_date'])
    
    tomorrow = today + timedelta(days=1)
    end_date = tomorrow + timedelta(days=1)
    
    return {
        "end_date": end_date.strftime("%Y-%m-%d"),
        "name": "Discovery ID",
        "info_url": "https://tvinside.com.br/programacao_tv/investigacao_discovery",
        "country": "Brazil",
        "description": None,
        "error_message": "",
        "provider": "tvinside.com.br",
        "source_url": "https://tvinside.com.br/programacao_tv/investigacao_discovery",
        "epg_list": all_programs,
        "offset": "-03:00",
        "timezone": "America/Sao_Paulo",
        "error_code": 0,
        "start_date": today.strftime("%Y-%m-%d"),
        "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Investigation_Discovery_Logo_2018.svg/512px-Investigation_Discovery_Logo_2018.svg.png"
    }


def save_json(data: dict, filename: str = "ID_BR.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filename


if __name__ == "__main__":
    today = date.today()
    print(f"🔍 Buscando programação Discovery ID para {today} e amanhã...")

    try:
        data = build_epg(today)
        filename = save_json(data)
        print(f"\n✅ Scraping concluído!")
        print(f"📁 Arquivo salvo: {filename}")
        print(f"📺 Total de programas: {len(data['epg_list'])}")
        print(f"\n📄 Primeiros 5 programas:")
        for p in data['epg_list'][:5]:
            print(f"   {p['start_date']} - {p['title']}")
    except Exception as e:
        print(f"\n❌ Falha: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
