# epg_discovery.py
import asyncio
import json
from datetime import datetime, date, timedelta
from playwright.async_api import async_playwright


async def scrape_day(page, day_label: str, base_date: date):
    """Scrapes a single day from mi.tv — garantindo que só pega o painel ATIVO"""

    print(f"  📅 Clicando em '{day_label}'...")

    # Clica no tab usando texto exato
    tab = await page.locator(f'[role="tab"]:has-text("{day_label}")').first
    if await tab.count() > 0:
        await tab.click()
        await asyncio.sleep(2)
        print(f"  ✅ Tab '{day_label}' clicado")
    else:
        # Fallback: pode já estar ativo se for "Hoje" no primeiro load
        active_tab = await page.locator('[role="tab"][aria-selected="true"]').text_content()
        if day_label in (active_tab or ""):
            print(f"  ℹ️ Tab '{day_label}' já está ativa")
        else:
            print(f"  ⚠️ Não consegui clicar no tab '{day_label}'")
            return []

    # ESPERA CRÍTICA: garante que o conteúdo do novo dia renderizou
    # e que o painel antigo sumiu do DOM ou ficou hidden
    await page.wait_for_timeout(1500)

    # Agora extrai SÓ do painel ativo/visível
    # Baseado na screenshot: lista com hora + título em sequência
    programs = await page.evaluate("""
        (dayLabel) => {
            const items = [];
            
            // 1. Encontra o painel ativo (tabpanel com aria-hidden="false" ou sem hidden)
            // ou o container que está visível e contém a programação
            let activePanel = null;
            
            // Tenta achar pelo ARIA
            const panels = document.querySelectorAll('[role="tabpanel"]');
            for (const panel of panels) {
                if (panel.getAttribute('aria-hidden') !== 'true' && 
                    panel.offsetParent !== null) {
                    activePanel = panel;
                    break;
                }
            }
            
            // Fallback: procura o container visível que tem horários
            if (!activePanel) {
                const allContainers = document.querySelectorAll('div, section, article');
                for (const container of allContainers) {
                    // Container visível com múltiplos elementos de hora
                    if (container.offsetParent === null) continue;
                    const timeElements = container.querySelectorAll('div, span, p, li');
                    let timeCount = 0;
                    for (const el of timeElements) {
                        if (/^\\d{1,2}:\\d{2}$/.test(el.textContent.trim())) {
                            timeCount++;
                        }
                    }
                    if (timeCount >= 3) { // Pelo menos 3 programas = painel de grade
                        activePanel = container;
                        break;
                    }
                }
            }
            
            if (!activePanel) {
                console.log('Nenhum painel ativo encontrado');
                return [];
            }
            
            // 2. Dentro do painel ativo, extrai os programas
            // Estrutura da screenshot: elementos irmãos ou container com hora+título
            
            // Primeiro: tenta achar containers de programa estruturados
            const programElements = activePanel.querySelectorAll('div, li, article, section');
            const candidates = [];
            
            for (const el of programElements) {
                const text = el.textContent || '';
                // Procura padrão: começa com hora HH:MM
                const timeMatch = text.trim().match(/^(\\d{1,2}:\\d{2})\\s+/);
                if (timeMatch) {
                    // Verifica se não é um anúncio (contém "Anúncio" ou imagem de ad)
                    if (text.includes('Anúncio') || text.includes('BETMGM') || 
                        text.includes('cassino') || text.includes('Jogue')) {
                        continue;
                    }
                    candidates.push(el);
                }
            }
            
            // 3. Extrai hora e título de cada candidato
            for (const el of candidates) {
                const text = el.textContent.trim();
                
                // Pula anúncios definitivamente
                if (text.includes('Anúncio') || text.includes('Aposta') || 
                    text.includes('BET') || text.includes('cassino')) {
                    continue;
                }
                
                // Extrai hora
                const timeMatch = text.match(/^(\\d{1,2}:\\d{2})/);
                if (!timeMatch) continue;
                const timeText = timeMatch[1];
                
                // Extrai título: texto após a hora, primeira linha significativa
                let titleText = '';
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l && l !== timeText);
                
                // Pula linhas que são metadados (como "23 min restantes")
                for (const line of lines) {
                    if (line.match(/^\\d+\\s+min/)) continue; // "23 min restantes"
                    if (line.match(/^\\+\\s*Mostrar/)) continue; // botão expandir
                    if (line.length > 2 && !line.includes('Anúncio')) {
                        titleText = line;
                        break;
                    }
                }
                
                // Fallback: regex para pegar título após hora na mesma linha
                if (!titleText) {
                    const titleMatch = text.match(/^\\d{1,2}:\\d{2}\\s+(.+?)(?:\\s+\\d+\\s+min|$)/);
                    if (titleMatch) titleText = titleMatch[1].trim();
                }
                
                if (timeText && titleText && titleText.length > 1) {
                    items.push({
                        time: timeText,
                        title: titleText
                    });
                }
            }
            
            // 4. Fallback se não achou nada: procura todos os textos com padrão hora+título
            if (items.length === 0) {
                const walker = document.createTreeWalker(activePanel, NodeFilter.SHOW_TEXT);
                const texts = [];
                let node;
                while (node = walker.nextNode()) {
                    texts.push(node.textContent.trim());
                }
                
                for (let i = 0; i < texts.length; i++) {
                    const t = texts[i];
                    const timeMatch = t.match(/^(\\d{1,2}:\\d{2})$/);
                    if (timeMatch && i + 1 < texts.length) {
                        const nextText = texts[i + 1];
                        if (nextText && nextText.length > 2 && 
                            !nextText.includes('Anúncio') && 
                            !nextText.includes('min restantes')) {
                            items.push({
                                time: timeMatch[1],
                                title: nextText
                            });
                        }
                    }
                }
            }
            
            return items;
        }
    """, day_label)

    print(f"  📺 {len(programs)} programas encontrados em '{day_label}'")
    for p in programs[:3]:
        print(f"     {p['time']} - {p['title']}")
    return programs


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

        # Block recursos pesados mas deixa o conteúdo principal
        await page.route("**/*", lambda route, request: 
            route.abort() if any(x in request.url for x in [
                'google-analytics', 'googletagmanager', 'facebook',
                'doubleclick', 'adsystem', 'analytics', 'tracker',
                'gtm.js', 'gtag'
            ]) else route.continue_()
        )

        print("⏳ Carregando página...")

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Espera os tabs de dia carregarem
            await page.wait_for_selector('[role="tab"]:has-text("Hoje")', timeout=10000)
            
        except Exception as e:
            print(f"❌ Erro ao carregar página: {e}")
            await browser.close()
            raise

        # Scrape "Hoje" (today)
        print("\n🔍 Scraping 'Hoje'...")
        programs_today = await scrape_day(page, "Hoje", target_date)

        # Scrape "Amanhã" (tomorrow)
        print("\n🔍 Scraping 'Amanhã'...")
        tomorrow_date = target_date + timedelta(days=1)
        programs_tomorrow = await scrape_day(page, "Amanhã", tomorrow_date)

        await browser.close()

        # Combine e converte para formato epg.pw
        all_programs = []

        # Process today
        for prog in programs_today:
            try:
                hour, minute = map(int, prog['time'].split(':'))
                start_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, 0)
                all_programs.append({
                    "desc": "",
                    "start_date": start_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                    "title": prog['title']
                })
            except ValueError:
                continue

        # Process tomorrow
        for prog in programs_tomorrow:
            try:
                hour, minute = map(int, prog['time'].split(':'))
                start_dt = datetime(tomorrow_date.year, tomorrow_date.month, tomorrow_date.day, hour, minute, 0)
                all_programs.append({
                    "desc": "",
                    "start_date": start_dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                    "title": prog['title']
                })
            except ValueError:
                continue

        # Sort by start_date
        all_programs.sort(key=lambda x: x['start_date'])

        result = {
            "end_date": (tomorrow_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "name": "Discovery ID",
            "info_url": url,
            "country": "Brazil",
            "description": None,
            "error_message": "",
            "provider": "mi.tv",
            "source_url": url,
            "epg_list": all_programs,
            "offset": "-03:00",
            "timezone": "America/Sao_Paulo",
            "error_code": 0,
            "start_date": target_date.strftime("%Y-%m-%d"),
            "icon": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Investigation_Discovery_Logo_2018.svg/512px-Investigation_Discovery_Logo_2018.svg.png"
        }

        return result


def save_json(data: dict, filename: str = None):
    if filename is None:
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
        print(f"\n📄 Primeiros 5 programas:")
        for p in data['epg_list'][:5]:
            print(f"   {p['start_date']} - {p['title']}")
    except Exception as e:
        print(f"\n❌ Falha: {e}")
        import traceback
        traceback.print_exc()