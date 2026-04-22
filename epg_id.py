# epg_discovery.py
import asyncio
import json
import sys
from datetime import datetime, date, timedelta
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


async def scrape_day(page, day_label: str, base_date: date, max_retries: int = 3):
    """Scrapes a single day from mi.tv com retry e detecção robusta do painel ativo"""
    
    for attempt in range(max_retries):
        try:
            print(f"  📅 Clicando em '{day_label}' (tentativa {attempt + 1}/{max_retries})...")
            
            # Clica no tab
            tab = page.locator(f'[role="tab"]:has-text("{day_label}")').first
            count = await tab.count()
            
            if count > 0:
                await tab.click()
                await asyncio.sleep(2)
                print(f"  ✅ Tab '{day_label}' clicado")
            else:
                # Fallback: verifica se já está ativo
                active_tab = await page.locator('[role="tab"][aria-selected="true"]').text_content()
                if active_tab and day_label in active_tab:
                    print(f"  ℹ️ Tab '{day_label}' já está ativa")
                else:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    print(f"  ⚠️ Não consegui clicar no tab '{day_label}'")
                    return []

            # Espera o painel ativo renderizar com conteúdo
            await page.wait_for_timeout(2000)
            
            # Verifica se o painel tem conteúdo antes de extrair
            active_panel = page.locator('[role="tabpanel"][aria-hidden="false"]').first
            if await active_panel.count() == 0:
                if attempt < max_retries - 1:
                    continue
                return []

            programs = await page.evaluate("""
                () => {
                    const items = [];
                    
                    // Encontra painel ativo
                    let panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                    if (!panel) {
                        // Fallback: procura container visível com programas
                        const containers = document.querySelectorAll('div, section');
                        for (const c of containers) {
                            if (c.offsetParent === null) continue;
                            const times = c.querySelectorAll('*');
                            let count = 0;
                            for (const t of times) {
                                if (/^\\d{1,2}:\\d{2}$/.test(t.textContent.trim())) count++;
                            }
                            if (count >= 3) { panel = c; break; }
                        }
                    }
                    if (!panel) return [];
                    
                    // Extrai programas - estratégia: procura elementos com hora como primeiro texto
                    const allElements = panel.querySelectorAll('div, li, article');
                    
                    for (const el of allElements) {
                        const text = el.textContent.trim();
                        
                        // Filtra anúncios
                        if (/Anúncio|BETMGM|Aposta|cassino|Jogue/i.test(text)) continue;
                        
                        // Match hora + título
                        const match = text.match(/^(\\d{1,2}:\\d{2})\\s*[\\n\\s]+(.+?)(?:\\s+\\d+\\s*min|$)/s);
                        if (match) {
                            const time = match[1];
                            let title = match[2].split('\\n')[0].trim();
                            
                            // Limpa título
                            title = title.replace(/^\\+\\s*Mostrar.*/, '').trim();
                            
                            if (title && title.length > 1 && !/min restantes/i.test(title)) {
                                items.push({ time, title });
                            }
                        }
                    }
                    
                    // Fallback: tree walker para texto solto
                    if (items.length === 0) {
                        const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
                        const texts = [];
                        let node;
                        while (node = walker.nextNode()) {
                            const t = node.textContent.trim();
                            if (t) texts.push(t);
                        }
                        
                        for (let i = 0; i < texts.length - 1; i++) {
                            const timeMatch = texts[i].match(/^(\\d{1,2}:\\d{2})$/);
                            if (timeMatch) {
                                const next = texts[i + 1];
                                if (next && next.length > 2 && !/Anúncio|min restantes/i.test(next)) {
                                    items.push({ time: timeMatch[1], title: next });
                                }
                            }
                        }
                    }
                    
                    return items;
                }
            """)
            
            if programs:
                print(f"  📺 {len(programs)} programas encontrados em '{day_label}'")
                for p in programs[:3]:
                    print(f"     {p['time']} - {p['title']}")
                return programs
                
            elif attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            else:
                return []
                
        except Exception as e:
            print(f"  ⚠️ Erro na tentativa {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                return []
    
    return []


async def scrape_discovery_id_mitv(target_date: date = None):
    if target_date is None:
        target_date = date.today()

    url = "https://mi.tv/br/canais/investigacao-discovery"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-BR',
            timezone_id='America/Sao_Paulo',
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        # Block recursos pesados
        await page.route("**/*", lambda route, request: 
            route.abort() if any(x in request.url.lower() for x in [
                'google-analytics', 'googletagmanager', 'facebook',
                'doubleclick', 'adsystem', 'analytics', 'tracker',
                'gtm.js', 'gtag', 'ads', 'advertising'
            ]) else route.continue_()
        )

        print("⏳ Carregando página...")

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Espera tabs carregarem
            await page.wait_for_selector('[role="tab"]:has-text("Hoje")', timeout=15000)
            
        except PlaywrightTimeout:
            print("❌ Timeout ao carregar página")
            await browser.close()
            raise
        except Exception as e:
            print(f"❌ Erro ao carregar página: {e}")
            await browser.close()
            raise

        # Scrape Hoje
        print("\n🔍 Scraping 'Hoje'...")
        programs_today = await scrape_day(page, "Hoje", target_date)

        # Scrape Amanhã
        print("\n🔍 Scraping 'Amanhã'...")
        tomorrow_date = target_date + timedelta(days=1)
        programs_tomorrow = await scrape_day(page, "Amanhã", tomorrow_date)

        await browser.close()

        # Validação: precisa ter pelo menos alguns programas
        if not programs_today and not programs_tomorrow:
            raise Exception("Nenhum programa encontrado para hoje ou amanhã")

        # Constrói resultado com timezone BRASÍLIA (-03:00)
        all_programs = []

        for prog in programs_today:
            try:
                hour, minute = map(int, prog['time'].split(':'))
                # Cria datetime NA timezone de Brasília (não converte, cria direto)
                start_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, 0)
                # Formata com offset -03:00 explicitamente
                all_programs.append({
                    "desc": "",
                    "start_date": start_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                    "title": prog['title']
                })
            except (ValueError, KeyError):
                continue

        for prog in programs_tomorrow:
            try:
                hour, minute = map(int, prog['time'].split(':'))
                start_dt = datetime(tomorrow_date.year, tomorrow_date.month, tomorrow_date.day, hour, minute, 0)
                all_programs.append({
                    "desc": "",
                    "start_date": start_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                    "title": prog['title']
                })
            except (ValueError, KeyError):
                continue

        all_programs.sort(key=lambda x: x['start_date'])

        # Calcula end_date corretamente
        end_date = tomorrow_date + timedelta(days=1)

        result = {
            "end_date": end_date.strftime("%Y-%m-%d"),
            "name": "Discovery ID",
            "info_url": url,
            "country": "Brazil",
            "description": None,
            "error_message": "",
            "provider": "mi.tv",
            "source_url": url,
            "epg_list": all_programs,
            "offset": "-03:00",  # <-- CORRIGIDO: Brasília
            "timezone": "America/Sao_Paulo",  # <-- CORRIGIDO
            "error_code": 0,
            "start_date": target_date.strftime("%Y-%m-%d"),
            "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Investigation_Discovery_Logo_2018.svg/512px-Investigation_Discovery_Logo_2018.svg.png"
        }

        return result


def save_json(data: dict, filename: str = "ID_BR.json"):
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
        print(f"\n📄 Primeiros 5 programas:")
        for p in data['epg_list'][:5]:
            print(f"   {p['start_date']} - {p['title']}")
    except Exception as e:
        print(f"\n❌ Falha: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
