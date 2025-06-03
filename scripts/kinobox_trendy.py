import requests
import json
from datetime import datetime
import pytz
from feedgen.feed import FeedGenerator # <--- NOVÝ IMPORT
import re
import sys
import os

# --- Funkce pro získání aktuálního Build ID ---
def get_kinobox_build_id(source_url="https://www.kinobox.cz/filmy"):
    """
    Stáhne HTML stránky Kinoboxu a pokusí se z něj extrahovat
    aktuální Next.js build ID.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
        }
        print(f"Stahuji HTML pro získání Build ID z: {source_url}")
        response = requests.get(source_url, headers=headers, timeout=15)
        response.raise_for_status()
        html_content = response.text

        pattern_next_data = r'<script id="__NEXT_DATA__".*?>.*?"buildId":"([a-zA-Z0-9_-]+)".*?</script>'
        match_next_data = re.search(pattern_next_data, html_content, re.DOTALL)
        if match_next_data:
            build_id = match_next_data.group(1)
            if len(build_id) > 10: # Základní kontrola, jestli ID vypadá rozumně
                print(f"Build ID nalezeno v __NEXT_DATA__: {build_id}")
                return build_id

        pattern_static = r'/_next/static/([a-zA-Z0-9_-]{15,})/_(?:buildManifest|ssgManifest)\.js'
        match_static = re.search(pattern_static, html_content)
        if match_static:
            build_id = match_static.group(1)
            print(f"Build ID nalezeno ve statické cestě k manifestu: {build_id}")
            return build_id

        pattern_static_generic = r'/_next/static/([a-zA-Z0-9_-]{15,})/'
        matches_generic = re.findall(pattern_static_generic, html_content)
        if matches_generic:
            build_id = matches_generic[0] # Vezmeme první nalezené
            print(f"Nalezeno potenciální Build ID (obecný vzor): {build_id}")
            return build_id

        print("Build ID nenalezeno žádnou z metod.", file=sys.stderr)
        return None
    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování URL {source_url} pro získání Build ID: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Neočekávaná chyba při získávání Build ID: {e}", file=sys.stderr)
        return None


# --- KONFIGURACE ---
script_dir = os.path.dirname(os.path.abspath(__file__))
BASE_KINOBOX_URL = "https://www.kinobox.cz"
TARGET_DATA_PATH = "/cs/filmy/trendy.json" # Tento skript se týká TRENDY filmů
OUTPUT_FILE = os.path.join(script_dir, os.pardir, "feed", "kinobox_trendy_rss.xml")# Cesta k výstupnímu souboru
PRAGUE_TZ = pytz.timezone('Europe/Prague') # Časová zóna pro lastBuildDate


# --- Získání aktuálního Build ID ---
print("-" * 30)
print("Získávám aktuální Kinobox Build ID...")
# Zkusíme získat ID přímo ze stránky /filmy/trendy, pokud selže, zkusíme /filmy
build_id_source_url_trendy = f"{BASE_KINOBOX_URL}/filmy/trendy"
actual_build_id = get_kinobox_build_id(source_url=build_id_source_url_trendy)

if not actual_build_id:
    print(f"\nNepodařilo se získat Build ID z {build_id_source_url_trendy}, zkouším {BASE_KINOBOX_URL}/filmy...")
    build_id_source_url_filmy = f"{BASE_KINOBOX_URL}/filmy"
    actual_build_id = get_kinobox_build_id(source_url=build_id_source_url_filmy)

if not actual_build_id:
    print("Chyba: Nepodařilo se získat aktuální Kinobox Build ID. Skript nemůže pokračovat.", file=sys.stderr)
    sys.exit(1)

print(f"Použité Build ID: {actual_build_id}")
print("-" * 30)

# --- Sestavení dynamické URL pro JSON data ---
JSON_URL = f"{BASE_KINOBOX_URL}/_next/data/{actual_build_id}{TARGET_DATA_PATH}"
print(f"Sestavená URL pro JSON data: {JSON_URL}")


# --- Stahování a zpracování JSON dat ---
print(f"\nStahuji JSON data z dynamicky sestavené URL...")
films_data = [] # Změněno z 'films' na 'films_data' pro jasnější rozlišení
try:
    response = requests.get(JSON_URL, timeout=15)
    response.raise_for_status()
    data = response.json()

    # PŘÍMÉ PARSOVÁNÍ KINOBOX STRUKTURY
    if "pageProps" not in data or "filmsOut" not in data["pageProps"] or "items" not in data["pageProps"]["filmsOut"]:
         raise KeyError("Chybějící klíč v očekávané cestě k filmům ('pageProps.filmsOut.items') v JSON datech.")
    films_data = data["pageProps"]["filmsOut"]["items"] # Získání seznamu filmů
    print(f"Nalezeno {len(films_data)} filmů v JSON.")

except requests.exceptions.HTTPError as e:
    print(f"Chyba HTTP {e.response.status_code} při stahování JSON z {JSON_URL}", file=sys.stderr)
    print(f"   -> Zkontrolujte, zda cesta '{TARGET_DATA_PATH}' stále existuje pro aktuální Build ID.", file=sys.stderr)
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"Chyba při stahování JSON: {e}", file=sys.stderr)
    print("   -> Zkontrolujte připojení k internetu.", file=sys.stderr)
    sys.exit(1)
except (json.JSONDecodeError, KeyError) as e:
    print(f"Chyba při zpracování JSON nebo chybějící klíč: {e}", file=sys.stderr)
    print(f"   -> Struktura JSON dat na {JSON_URL} se mohla změnit.", file=sys.stderr)
    sys.exit(1)
except Exception as e:
     print(f"Neočekávaná chyba při stahování/zpracování JSON: {e}", file=sys.stderr)
     sys.exit(1)


# --- Vytvoření RSS feedu pomocí FeedGenerator ---
print("\nVytvářím RSS feed...")
fg = FeedGenerator()
fg.title('Trendy filmy – Kinobox.cz')
fg.link(href=f'{BASE_KINOBOX_URL}/filmy/trendy', rel='alternate')
fg.description('Aktuálně nejvíce trendy filmy na Kinobox.cz')
fg.language('cs-cz')

# Důležité: self-referenční odkaz pro RSS čtečky
# Ujistěte se, že tato URL odpovídá finální URL, kde bude váš feed hostován!
fg.link(href='https://raw.githubusercontent.com/scarzxx/kinobox-rss/refs/heads/main/feed/kinobox_trendy_rss.xml', rel='self', type='application/rss+xml')

# lastBuildDate se nastaví automaticky při generování feedu, ale můžeme ho nastavit i explicitně
fg.lastBuildDate(datetime.now(PRAGUE_TZ))


# --- Zpracování jednotlivých filmů (itemů) ---
if not films_data: # Pokud se nepodařilo načíst filmy
    print("Žádné filmy k zpracování.", file=sys.stderr)
else:
    # Kinobox JSON vrací filmy od nejtrendyjšího po nejméně trendy.
    # RSS čtečky často zobrazují nejnovější/nejrelevantnější itemy nahoře.
    # Proto obrátíme seznam, aby nejtrendyjší film byl přidán jako poslední do fg,
    # a tím se objevil nahoře ve výsledném RSS feedu.
    processed_films = list(films_data) # Vytvoří kopii
    processed_films.reverse()           # Obrátí pořadí

    for film in processed_films: # Iterujeme přes obrácený seznam
        fe = fg.add_entry() # Vytvoří nový 'item' (položku)

        film_name = film.get("name", "Neznámý název")
        film_id = film.get("id")
        poster_url = film.get("poster")

        if not film_id:
            print(f"Varování: Přeskakuji film '{film_name}' bez ID.")
            continue

        # ID položky (guid v RSS)
        fe.id(f'kinobox_film_{film_id}')

        # Titulek položky
        fe.title(film_name)

        # Odkaz na položku
        fe.link(href=f'{BASE_KINOBOX_URL}/film/{film_id}')

        # Popis položky (s HTML obsahem a automatickým CDATA)
        description_parts_html = []

        if poster_url:
            # max-width: 100%; height: auto; pro responzivní obrázek
            # display: block; margin-bottom: 10px; pro oddělení textu pod obrázkem
            description_parts_html.append(f'<img src="{poster_url}" alt="{film_name} plakát" style="max-width:100%; height:auto; margin-bottom:10px; display:block;" />')

        if film.get('score') is not None: # Kontrola, zda skóre existuje
            description_parts_html.append(f'<p><strong>Hodnocení:</strong> {film["score"]}%</p>')
        if film.get('year'):
            description_parts_html.append(f'<p><strong>Rok výroby:</strong> {film["year"]}</p>')

        genres_list = film.get("genres", [])
        genre_names = [g.get("name") for g in genres_list if g.get("name")]
        if genre_names:
            description_parts_html.append(f'<p><strong>Žánry:</strong> {", ".join(genre_names)}</p>')

        if film.get('duration'):
            description_parts_html.append(f'<p><strong>Délka:</strong> {film["duration"]} min</p>')

        if film.get('minimalAge'):
            description_parts_html.append(f'<p><strong>Minimální věk:</strong> {film["minimalAge"]}+</p>')

        # Spojení všech částí description do jednoho HTML řetězce
        description_html_content = "".join(description_parts_html)

        # Nastavení popisu. isSummary=False zajistí, že FeedGenerator použije CDATA.
        fe.description(description_html_content, isSummary=False)

        # Datum publikace (pubDate)
        # Preferujeme 'releaseCz', pak 'releasedToCinema'
        release_date_str = film.get('releaseCz') or film.get('releasedToCinema')
        if release_date_str:
            try:
                # Kinobox data nemají časovou zónu, předpokládáme UTC nebo se dá nastavit Praha
                # Pro pubDate je vhodné použít timezone-aware datetime objekt
                release_dt = datetime.strptime(release_date_str, '%Y-%m-%d').replace(tzinfo=pytz.utc)
                fe.pubDate(release_dt)
            except ValueError:
                print(f"Varování: Neplatný formát data pro film {film_name}: {release_date_str}")
        else:
            # Pokud není datum vydání, můžeme použít current time nebo varování
            print(f"Varování: Film '{film_name}' nemá datum vydání, pubDate nebude nastaveno.")


# --- Uložení RSS feedu do souboru ---
print("\nUkládám RSS feed do souboru...")
try:
    # feedgenerator.rss_str() vrací bytes, proto použijeme 'wb' režim
    rss_feed_xml_bytes = fg.rss_str(pretty=True, encoding='utf-8')

    # Kontrola a vytvoření adresáře, pokud neexistuje
    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir and not os.path.exists(output_dir):
        print(f"Vytvářím adresář: {output_dir}")
        os.makedirs(output_dir)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(rss_feed_xml_bytes)

    print(f"RSS feed byl úspěšně vytvořen jako '{OUTPUT_FILE}'")

except Exception as e:
    print(f"Chyba při generování nebo ukládání RSS feedu: {e}", file=sys.stderr)
    sys.exit(1)