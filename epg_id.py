
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


def scrape_tvinside(day_offset: int = 0):
    """
    day_offset: 0 = hoje, 1 = amanhã, etc.
    Retorna lista de dicts: [{"time": "06:00", "title": "..."}, ...]
    """
    base_url = "https://tvinside.com.br/programacao_tv/investigacao_discovery"
    # O site pode aceitar ?dia=YYYY-MM-DD ou similar, mas vamos tentar sem query primeiro
    # Se precisar de data específica, ajustamos depois
    
    url = base_url
    if day_offset > 0:
        target = date.today() + timedelta(days=day_offset)
        # Tentativa: o site pode usar ?date= ou similar, mas vamos inspecionar
        # Por enquanto, scrape a página atual e vemos se tem tabs de dia
        pass

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Erro ao buscar tvinside: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Tenta encontrar a programação do dia correto
    # Estrutura típica: lista com hora e título
    programs = []
    
    # Procura por elementos que contenham horários no formato HH:MM
    text = soup.get_text(separator="\n")
    
    # Regex para capturar linhas como "06:00. Vivendo com o Inimigo" ou "06:00 h - Título"
    # Padrões encontrados: "06:00. Título" ou "06:00 h" ou "06:00 - Título"
    pattern = re.compile(r'^(\d{1,2}:\d{2})[.\s\-h]*(.+)$', re.MULTILINE)
    
    for match in pattern.finditer(text):
        time_str = match.group(1)
        title = match.group(2).strip()
        
        # Limpa título (remove categorias como "; Séries/Reality Show")
        title = re.split(r'[;|•]', title)[0].strip()
        
        # Remove sujeira
        if len(title) < 2 or title.lower() in ['h', '']:
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
