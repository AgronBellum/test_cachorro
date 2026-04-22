# epg_discovery.py
import asyncio
import json
import re
from datetime import datetime, date, timedelta
from playwright.async_api import async_playwright


async def scrape_day(page, day_label: str, base_date: date):
    """Scrapes a single day (Hoje or Amanhã)"""
    
    # Click on the day tab
    print(f"  📅 Clicando em '{day_label}'...")
    
    # Try multiple selectors for the tab
    tab_selectors = [
        f'a:has-text("{day_label}")',
        f'button:has-text("{day_label}")',
        f'[role="tab"]:has-text("{day_label}")',
        f'.day:has-text("{day_label}")',
        f'li:has-text("{day_label}")',
    ]
    
    tab_clicked = False
    for sel in tab_selectors:
        try:
            tab = await page.query_selector(sel)
            if tab:
                await tab.click()
                await asyncio.sleep(2)  # Wait for content to load
                tab_clicked = True
                print(f"  ✅ Tab '{day_label}' clicado")
                break
        except:
            continue
    
    if not tab_clicked:
        # If "Hoje" is already active, we might not need to click
        if day_label == "Hoje":
            print(f"  ℹ️ Tab 'Hoje' já está ativa")
        else:
            print(f"  ⚠️ Não consegui clicar no tab '{day_label}'")
    
    # Extract programs - based on the screenshot structure
    programs = await page.evaluate("""
        () => {
            const items = [];
            
            // The page likely has a list of program items
            // Each item has: time (like "03:46"), title, and description
            
            // Try to find all program containers
            const allElements = document.querySelectorAll('*');
            let programContainers = [];
            
            // Look for elements that contain time patterns like "03:46" or "04:30"
            allElements.forEach(el => {
                const text = el.textContent || '';
                // Match time pattern HH:MM
                if (/^\\d{1,2}:\\d{2}$/.test(text.trim())) {
                    const parent = el.parentElement;
                    if (parent && !programContainers.includes(parent)) {
                        programContainers.push(parent);
                    }
                }
            });
            
            // If that didn't work, try common container selectors
            if (programContainers.length === 0) {
                const selectors = [
                    '.program', '.schedule-item', '.tv-program',
                    '[data-program]', '.listing-item', '.event',
                    '.show', '.guide-item', 'article', '.item'
                ];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        programContainers = Array.from(els);
                        break;
                    }
                }
            }
            
            programContainers.forEach(container => {
                // Try to find time
                let timeText = '';
                const timeEl = container.querySelector('.time, .hour, [class*="time"], [class*="hora"]');
                if (timeEl) {
                    timeText = timeEl.textContent.trim();
                } else {
                    // Try regex on container text
                    const match = container.textContent.match(/(\\d{1,2}:\\d{2})/);
                    if (match) timeText = match[1];
                }
                
                // Try to find title
                let titleText = '';
                const titleEl = container.querySelector('.title, .name, [class*="title"], [class*="nome"], h3, h4, h2');
                if (titleEl) {
                    titleText = titleEl.textContent.trim();
                } else {
                    // Title is usually the text after the time
                    const lines = container.innerText.split('\\n').map(l => l.trim()).filter(l => l);
                    const timeIdx = lines.findIndex(l => l.match(/^\\d{1,2}:\\d{2}$/));
                    if (timeIdx >= 0 && lines[timeIdx + 1]) {
                        titleText = lines[timeIdx + 1];
                    }
                }
                
                if (timeText && titleText) {
                    items.push({
                        time: timeText,
                        title: titleText
                    });
                }
            });
            
            return items;
        }
    """)
    
    print(f"  📺 {len(programs)} programas encontrados em '{day_label}'")
    return programs


async def scrape_discovery_id_mitv(target_date: date = None):
    if target_date is None:
        target_date = date.today()
    
    url = "https://mi.tv/br/canais/investigacao-discovery"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        page = await context.new_page()
        
        # Block heavy resources
        await page.route("**/*", lambda route, request: 
            route.abort() if any(x in request.url for x in [
                'google-analytics', 'googletagmanager', 'facebook',
                'doubleclick', 'adsystem', 'analytics', 'tracker'
            ]) else route.continue_()
        )
        
        print("⏳ Carregando página...")
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)  # Extra wait for JS rendering
            
            # Take debug screenshot
            # await page.screenshot(path="debug_page.png")
            
        except Exception as e:
            print(f"❌ Erro ao carregar página: {e}")
            await browser.close()
            raise
        
        # Scrape "Hoje" (today)
        print("\n🔍 Scraping 'Hoje'...")
        programs_today = await scrape_day(page, "Hoje", target_date)
         
        await browser.close()
        
        # Combine and convert to epg.pw format
        all_programs = []
        
        # Process today
        base_date = target_date
        for i, prog in enumerate(programs_today):
            hour, minute = map(int, prog['time'].split(':'))
            start_dt = datetime(base_date.year, base_date.month, base_date.day, hour, minute, 0)
            start_dt_utc = start_dt + timedelta(hours=3)  # BR -> UTC
            
            all_programs.append({
                "desc": "",
                "start_date": start_dt_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "title": prog['title']
            })
        
        # Sort by start_date
        all_programs.sort(key=lambda x: x['start_date'])
        
        result = {
            "end_date": (timedelta(days=1)).strftime("%Y-%m-%d"),
            "name": "Discovery ID",
            "info_url": url,
            "country": "Brazil",
            "description": None,
            "error_message": "",
            "provider": "mi.tv",
            "source_url": url,
            "epg_list": all_programs,
            "offset": "+00:00",
            "timezone": "None",
            "error_code": 0,
            "start_date": target_date.strftime("%Y-%m-%d"),
            "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Investigation_Discovery_Logo_2018.svg/512px-Investigation_Discovery_Logo_2018.svg.png"
        }
        
        return result


def save_json(data: dict, filename: str = None):
    if filename is None:
        date_str = data['start_date']
        filename = f"ID_BR.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return filename


if __name__ == "__main__":
    today = date.today()
    print(f"🔍 Buscando programação Discovery ID para {today} e amanhã...")
    
    try:
        data = asyncio.run(scrape_discovery_id_mitv(today))
        filename = save_json(data)
        print(f"\n✅ Scraping concluído!")
        print(f"📁 Arquivo salvo: {filename}")
        print(f"📺 Total de programas: {len(data['epg_list'])}")
        print(f"\n📄 Primeiros 3 programas:")
        for p in data['epg_list'][:3]:
            print(f"   {p['start_date']} - {p['title']}")
    except Exception as e:
        print(f"\n❌ Falha: {e}")
        import traceback
        traceback.print_exc()
