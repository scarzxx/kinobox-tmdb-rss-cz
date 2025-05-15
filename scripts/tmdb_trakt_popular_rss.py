import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
from xml.dom import minidom
import os
import sys
import re # Pro robustnější extrakci ID
import time # Pro měření času
# --- ODSTRANĚNÝ IMPORT ---
# from concurrent.futures import ThreadPoolExecutor, as_completed

# --- KONFIGURACE ---
URL = 'https://www.themoviedb.org/movie'  # Stránka s populárními filmy
OUTPUT_FILE = "feed/tmdb_trakt_popular_rss.xml" # Cesta k výstupnímu souboru
PRAGUE_TZ = pytz.timezone('Europe/Prague') # I když pubDate je UTC, ponecháme pro kontext
# Místo napevno zadaného ID čteme Trakt Client ID z proměnné prostředí GitHub Actions
TRAKT_CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID")  # !!! ZADEJ SVOJE TRAKT CLIENT ID ZDE !!!
# Pro TMDB není potřeba dynamické Build ID ani nastavení lokále pro datum.

# Síťové nastavení (ponechány původní hodnoty jako konfigurační proměnné)
REQUESTS_TIMEOUT_TMDB = 15  # Timeout pro stahování hlavní stránky TMDB
REQUESTS_TIMEOUT_TRAKT = 10 # Timeout pro Trakt API volání
# MAX_TRAKT_WORKERS = 10      # Tato proměnná už není použita, protože není ThreadPoolExecutor

# --- FUNKCE PRO ZÍSKÁNÍ TRAKT URL ---
# Funkce stále očekává session, která bude předána z hlavního skriptu
def fetch_trakt_url(session, tmdb_id, client_id):
    """Získá Trakt URL pro dané TMDB ID pomocí předané requests session."""
    # Přidána kontrola na prázdné tmdb_id před sestavením URL
    if not tmdb_id or not client_id or client_id == "ID":
        # print(f"Info: Přeskakuji Trakt volání pro neplatné ID ({tmdb_id}) nebo nenastavený klient ID.", file=sys.stderr)
        return tmdb_id, None, "Invalid config or ID"

    trakt_api_url = f"https://api.trakt.tv/search/tmdb/{tmdb_id}?type=movie"
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id
    }
    try:
        # Používáme předanou session
        response = session.get(trakt_api_url, headers=headers, timeout=REQUESTS_TIMEOUT_TRAKT)
        response.raise_for_status() # Vyvolá HTTPError pro špatné odpovědi (4xx, 5xx)
        trakt_data = response.json()

        if (trakt_data and isinstance(trakt_data, list) and len(trakt_data) > 0 and
            isinstance(trakt_data[0], dict) and 'movie' in trakt_data[0] and
            isinstance(trakt_data[0]['movie'], dict) and 'ids' in trakt_data[0]['movie'] and
            isinstance(trakt_data[0]['movie']['ids'], dict) and 'slug' in trakt_data[0]['movie']['ids']):
            trakt_url = f"https://trakt.tv/movies/{trakt_data[0]['movie']['ids']['slug']}"
            # print(f"Načten Trakt URL pro TMDB ID {tmdb_id}") # Příliš detailní výpis
            return tmdb_id, trakt_url, "Success"
        else:
            # print(f"Info: Trakt data nenalezena nebo nekompletní pro TMDB ID: {tmdb_id}")
            return tmdb_id, None, "Data not found or incomplete"
    except requests.exceptions.RequestException as e:
        # print(f"Chyba při získávání Trakt URL pro TMDB ID {tmdb_id}: {e}", file=sys.stderr) # Příliš detailní výpis
        return tmdb_id, None, f"Request Error: {e}"
    except Exception as e: # Zahrnuje JSONDecodeError, KeyError, IndexError, TypeError
        # print(f"Chyba při zpracování Trakt odpovědi pro TMDB ID {tmdb_id}: {e}", file=sys.stderr) # Příliš detailní výpis
        return tmdb_id, None, f"Processing Error: {e}"


# --- Hlavní skript ---
start_time = time.time()

# --- Stahování a zpracování HTML ---
print(f"1/3: Stahuji a parsuji HTML z: {URL}")
headers_tmdb = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'}
try:
    response = requests.get(URL, headers=headers_tmdb, timeout=REQUESTS_TIMEOUT_TMDB)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    print(f"   HTML staženo a naparsováno ({time.time() - start_time:.2f}s).")
except requests.exceptions.RequestException as e:
    print(f"Chyba při stahování HTML z {URL}: {e}", file=sys.stderr)
    print("Zkontrolujte URL a připojení k internetu.", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Neočekávaná chyba při parsování HTML: {e}", file=sys.stderr)
    sys.exit(1)

# --- Vytvoření RSS struktury kanálu ---
rss = ET.Element('rss', version='2.0')
rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
# Přidáme vlastní namespace pro Trakt URL, pokud ho chceme používat v odděleném elementu
rss.set("xmlns:custom", "http://example.com/rss/custom") # Příklad vlastního namespace
channel = ET.SubElement(rss, 'channel')

ET.SubElement(channel, 'title').text = 'TMDB Populární filmy'
ET.SubElement(channel, 'link').text = URL
ET.SubElement(channel, 'description').text = 'Aktuálně nejoblíbenější filmy na TheMovieDB.org'
ET.SubElement(channel, 'language').text = 'en-us'
atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
# !! DŮLEŽITÉ: Nahraď tuto URL skutečnou finální URL, kde bude feed hostován !!
atom_link.set("href", "https://raw.githubusercontent.com/scarzxx/kinobox-rss/refs/heads/main/feed/tmdb_popular_rss.xml") # Příklad URL
atom_link.set("rel", "self")
atom_link.set("type", "application/rss+xml")
# Použití UTC času pro lastBuildDate je standard pro RSS
ET.SubElement(channel, "lastBuildDate").text = datetime.now(pytz.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

# --- Zpracování filmů z HTML a sběr dat pro Trakt ---
print("   Extrahuji data z filmových karet a sbírám TMDB ID...")
cards = soup.find_all('div', class_='card style_1')

if not cards:
    print("Nenalezeny žádné filmové karty na stránce.", file=sys.stderr)
    # Přesto vygenerujeme prázdný feed, aby se existující soubor nepřepsal chybou
    parsed_cards_data = []
    tmdb_ids_to_fetch_trakt = []
else:
    parsed_cards_data = []
    tmdb_ids_to_fetch_trakt = []

    for card in cards:
        h2_tag = card.find('h2')
        title = h2_tag.get_text(strip=True) if h2_tag else 'Neznámý název'

        a_tag = h2_tag.find('a') if h2_tag else None
        href_relative = a_tag['href'] if a_tag and 'href' in a_tag.attrs else None

        full_link = f"https://www.themoviedb.org{href_relative}" if href_relative else URL
        tmdb_id = None
        if href_relative:
            # Robustnější extrakce ID pomocí regex
            match = re.search(r'/movie/(\d+)-', href_relative)
            if match:
                tmdb_id = match.group(1)
            else:
                 # Zkusíme extrakci z konce URL, pokud regex selže (méně spolehlivé)
                potential_id = href_relative.split('/')[-1].split('-')[0]
                if potential_id.isdigit():
                     tmdb_id = potential_id

            if not tmdb_id:
                 print(f"Varování: Nepodařilo se extrahovat platné TMDB ID z '{href_relative}' pro film '{title}'. Trakt URL nebude získána.")

        score_tag = card.find('div', class_='user_score_chart')
        score = score_tag['data-percent'] if score_tag and 'data-percent' in score_tag.attrs else None

        image_tag = card.find('img')
        image_url = image_tag['data-src'] if image_tag and 'data-src' in image_tag.attrs else (image_tag['src'] if image_tag and 'src' in image_tag.attrs else None)
        if image_url:
            if image_url.startswith('//'):
                image_url = f'https:{image_url}'
            # Kontrola, zda se nejedná o placeholder obrázek
            if 'glyphicons-basic-' in image_url or 'loading.svg' in image_url or not image_url.strip():
                image_url = None
            # TMDB často používá malé náhledy, nahradíme je za větší w342, pokud je URL ve standardním formátu
            # Pouze pokud image_url není None
            if image_url:
                 image_url = image_url.replace('/w94_and_h141_bestv2/', '/w342/').replace('/w185/', '/w342/').replace('/w150_and_h225_bestv2/', '/w342/')


        date_tag = card.find('p')
        date_text = date_tag.get_text(strip=True) if date_tag else ''
        year = None
        date_for_pubdate = None # Datum v UTC pro RSS pubDate
        # date_local = None # Datum pro zobrazení roku - momentálně nevyužito přímo
        if date_text:
            try:
                # Datum na TMDB je ve formátu MM/DD/YYYY
                # Pro pubDate v RSS potřebujeme UTC čas
                # Budeme parsovat datum bez časové zóny a předpokládat UTC pro pubDate
                date_for_pubdate_naive = datetime.strptime(date_text, '%m/%d/%Y')
                date_for_pubdate = pytz.utc.localize(date_for_pubdate_naive) # Převedeme naive na aware v UTC
                year = str(date_for_pubdate.year)
            except (ValueError, TypeError):
                if date_text.strip():
                    print(f"Varování: Nepodařilo se naparsovat datum '{date_text}' pro film '{title}'. PubDate/Rok vynechán.")

        card_data = {
            'title': title,
            'full_link': full_link,
            'tmdb_id': tmdb_id,
            'score': score,
            'image_url': image_url,
            'date_for_pubdate': date_for_pubdate,
            'year': year # Použijeme extrahovaný rok
        }
        parsed_cards_data.append(card_data)
        if tmdb_id: # Přidáme pouze platná TMDB ID pro Trakt volání
            tmdb_ids_to_fetch_trakt.append(tmdb_id)

    print(f"   Extrahováno dat pro {len(parsed_cards_data)} filmů ({time.time() - start_time:.2f}s).")

# --- Sekvenční stahování Trakt URL ---
trakt_urls_map = {}
if tmdb_ids_to_fetch_trakt and TRAKT_CLIENT_ID and TRAKT_CLIENT_ID != "ID":
    print(f"\n2/3: Stahuji Trakt URL pro {len(tmdb_ids_to_fetch_trakt)} filmů (sekvenčně)...")
    trakt_start_time = time.time()
    successful_trakt_fetches = 0
    failed_trakt_fetches = 0

    # Vytvoření jedné requests session pro všechna sekvenční volání Trakt API
    with requests.Session() as session:
        for tmdb_id in tmdb_ids_to_fetch_trakt:
            # Voláme funkci fetch_trakt_url přímo
            _fetched_tmdb_id, trakt_url, status = fetch_trakt_url(session, tmdb_id, TRAKT_CLIENT_ID)

            if trakt_url:
                trakt_urls_map[tmdb_id] = trakt_url
                successful_trakt_fetches += 1
            else:
                failed_trakt_fetches += 1
                # Volitelně logovat, proč selhalo, ale pro každé volání je to detailní
                # if status != "Data not found or incomplete":
                #     print(f"   Varování: Nepodařilo se získat Trakt URL pro TMDB ID {tmdb_id}. Status: {status}", file=sys.stderr)

    trakt_duration = time.time() - trakt_start_time
    print(f"   Trakt URL načteny/zpracovány. Úspěch: {successful_trakt_fetches}, Selhání: {failed_trakt_fetches} ({trakt_duration:.2f}s).")

elif TRAKT_CLIENT_ID == "ID":
    print("\nVarování: TRAKT_CLIENT_ID není nastaveno. Trakt URL nebudou načteny.")
elif not tmdb_ids_to_fetch_trakt:
     print("\nInfo: Nebyla nalezena žádná platná TMDB ID pro dotazování Trakt API.")


# --- Sestavení RSS itemů ---
print("\n3/3: Sestavuji RSS feed...")
for data in parsed_cards_data:
    # print(f"   Přidávám do RSS: {data['title']} (ID: {data['tmdb_id']})") # Příliš detailní výpis
    item = ET.SubElement(channel, 'item')

    ET.SubElement(item, 'title').text = data['title']
    ET.SubElement(item, 'link').text = data['full_link']
    # GUID by měl být unikátní identifikátor itemu. Full link je dobrá volba, pokud se nemění.
    if data['full_link'] and data['full_link'] != URL:
         ET.SubElement(item, 'guid', isPermaLink="true").text = data['full_link']
    elif data['tmdb_id']: # Alternativně použijeme TMDB ID, pokud link chybí nebo je generický
         ET.SubElement(item, 'guid', isPermaLink="false").text = f"tmdb-movie-{data['tmdb_id']}"

    trakt_url = trakt_urls_map.get(data['tmdb_id']) # Použijeme .get pro bezpečný přístup
    if trakt_url:
        # Použijeme vlastní element s prefixem namespace (prefix "custom" je definován v root elementu rss)
        ET.SubElement(item, '{http://example.com/rss/custom}trakt').text = trakt_url

    if data['date_for_pubdate']:
        # RSS pubDate by mělo být v UTC (nebo s offsetem +0000)
        # datetime objekt z pytz.utc.localize už je aware a v UTC
        pub_date_rfc822 = data['date_for_pubdate'].strftime("%a, %d %b %Y %H:%M:%S +0000")
        ET.SubElement(item, 'pubDate').text = pub_date_rfc822

    description_parts_html = []
    if data['image_url']:
        # Přidáme obrázek do popisu s jednoduchým stylem pro responzivitu
        description_parts_html.append(f'<p><img src="{data["image_url"]}" alt="{data["title"]} poster" style="max-width: 100%; height: auto; display: block; margin-bottom: 10px;" /></p>')
    if data['score'] is not None:
        description_parts_html.append(f'<p>Hodnocení: {data["score"]}%</p>')
    if data['year']:
        description_parts_html.append(f'<p>Rok vydání: {data["year"]}</p>')
    # Přidáme odkaz na TMDB stránku do popisu
    if data['full_link'] and data['full_link'] != URL: # Přidáme jen pokud máme specifický link na film
         description_parts_html.append(f'<p><a href="{data["full_link"]}">Více na TMDB</a></p>')
    # Přidáme odkaz na Trakt stránku do popisu, pokud existuje
    if trakt_url:
         description_parts_html.append(f'<p><a href="{trakt_url}">Více na Trakt.tv</a></p>')


    # Sestavíme HTML pro description
    description_html = "".join(description_parts_html)

    # Vytvoříme description element a text do něj vložíme později jako CDATA
    # Toto je potřeba udělat přes minidom, protože ElementTree přímo nepodporuje CDATA
    desc_elem = ET.SubElement(item, 'description')
    desc_elem.text = description_html # Dočasně uložíme HTML jako text

# --- Uložení do souboru s pěkným zalomením a CDATA ---
print("   Ukládám RSS feed do souboru...")
try:
    # Převod ElementTree stromu na bajty pro minidom
    # short_empty_elements=False zajišťuje, že <description></description> není <description/>
    rough_string_bytes = ET.tostring(rss, encoding='utf-8', method='xml', xml_declaration=True, short_empty_elements=False)

    # Parsování pomocí minidom pro pretty printing a CDATA
    reparsed = minidom.parseString(rough_string_bytes)

    # Procházíme všechny description elementy a obalíme jejich obsah do CDATA
    for item_node in reparsed.getElementsByTagName('item'):
        description_nodes = item_node.getElementsByTagName('description')
        if description_nodes:
            desc_node_dom = description_nodes[0]
            # Získáme aktuální textový obsah (HTML)
            current_html_content = ''.join(child.data for child in desc_node_dom.childNodes if child.nodeType == child.TEXT_NODE)

            # Odstraníme původní textové uzly (může být více než jeden, pokud tam byly mezery/newline)
            while desc_node_dom.firstChild:
                desc_node_dom.removeChild(desc_node_dom.firstChild)

            # Vytvoříme a připojíme CDATA sekci s původním HTML obsahem
            cdata_section = reparsed.createCDATASection(current_html_content)
            desc_node_dom.appendChild(cdata_section)

    # Generování finálního XML s pěkným odsazením
    pretty_xml_bytes = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    # Zajištění existence výstupního adresáře
    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"   Vytvořen adresář: {output_dir}")
        except OSError as e:
            print(f"Chyba: Nelze vytvořit adresář '{output_dir}': {e}", file=sys.stderr)
            # Pokusíme se uložit do aktuálního adresáře
            OUTPUT_FILE = os.path.basename(OUTPUT_FILE)
            print(f"Pokusím se uložit do aktuálního adresáře jako '{OUTPUT_FILE}'", file=sys.stderr)
            # output_dir = None # Není potřeba nulovat, nová cesta je jen název souboru

    # Uložení XML do souboru
    try:
        with open(OUTPUT_FILE, "wb") as f: # Zápis binárně (b), protože toprettyxml vrací bytes
            f.write(pretty_xml_bytes)
        print(f"RSS feed byl úspěšně vytvořen jako '{OUTPUT_FILE}' ({time.time() - start_time:.2f}s celkem).")
    except IOError as e:
        print(f"Chyba: Nelze zapsat do souboru '{OUTPUT_FILE}': {e}", file=sys.stderr)
        sys.exit(1)

except Exception as e:
    print(f"Chyba při formátování nebo ukládání XML: {e}", file=sys.stderr)
    sys.exit(1)
