import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from xml.dom import minidom
import json
import re
import sys
import os # Přidáno pro os.path a os.makedirs

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
            if len(build_id) > 10:
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
            build_id = matches_generic[0]
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
TARGET_DATA_PATH = "/cs/filmy/trendy.json"
OUTPUT_FILE = "feed/kinobox_trendy_rss.xml"
PRAGUE_TZ = pytz.timezone('Europe/Prague')
BASE_KINOBEX_URL = "https://www.kinobox.cz"

# --- Získání aktuálního Build ID ---
print("-" * 30)
print("Získávám aktuální Kinobox Build ID...")
build_id_source_url = f"{BASE_KINOBEX_URL}/filmy/trendy"
actual_build_id = get_kinobox_build_id(source_url=build_id_source_url)

if not actual_build_id:
    print(f"\nNepodařilo se získat Build ID z {build_id_source_url}, zkouším {BASE_KINOBEX_URL}/filmy...")
    actual_build_id = get_kinobox_build_id(source_url=f"{BASE_KINOBEX_URL}/filmy")

if not actual_build_id:
    print("Chyba: Nepodařilo se získat aktuální Kinobox Build ID. Skript nemůže pokračovat.", file=sys.stderr)
    sys.exit(1)

print(f"Aktuální Build ID: {actual_build_id}")
print("-" * 30)

# --- Sestavení dynamické URL pro JSON data ---
JSON_URL = f"{BASE_KINOBEX_URL}/_next/data/{actual_build_id}{TARGET_DATA_PATH}"
print(f"Sestavená URL pro JSON data: {JSON_URL}")


# --- Stahování a zpracování JSON dat ---
print(f"\nStahuji JSON data z dynamicky sestavené URL...")
films = [] # Inicializace pro případ chyby
try:
    response = requests.get(JSON_URL, timeout=15)
    response.raise_for_status()
    data = response.json()

    if "pageProps" not in data or "filmsOut" not in data["pageProps"] or "items" not in data["pageProps"]["filmsOut"]:
         raise KeyError("Chybějící klíč v očekávané cestě k filmům ('pageProps.filmsOut.items') v JSON datech.")
    films = data["pageProps"]["filmsOut"]["items"]
    print(f"Nalezeno {len(films)} filmů v JSON.")

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


# --- Vytvoření RSS struktury kanálu ---
rss = ET.Element("rss", version="2.0")
rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
channel = ET.SubElement(rss, "channel")

ET.SubElement(channel, "title").text = "Trendy filmy – Kinobox.cz"
ET.SubElement(channel, "link").text = f"{BASE_KINOBEX_URL}/filmy/trendy"
ET.SubElement(channel, "description").text = "Aktuálně nejvíce trendy filmy na Kinobox.cz"
ET.SubElement(channel, "language").text = "cs-cz"
atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
atom_link.set("href", "https://raw.githubusercontent.com/scarzxx/kinobox-rss/refs/heads/main/feed/kinobox_trendy_rss.xml")
atom_link.set("rel", "self")
atom_link.set("type", "application/rss+xml")
ET.SubElement(channel, "lastBuildDate").text = datetime.now(PRAGUE_TZ).strftime("%a, %d %b %Y %H:%M:%S %z")


# --- Zpracování jednotlivých filmů (itemů) ---
print("\nZpracovávám filmy pro RSS feed...")
if not films: # Pokud se nepodařilo načíst filmy
    print("Žádné filmy k zpracování.", file=sys.stderr)
else:
    for film in films:
        item = ET.SubElement(channel, "item")
        film_name = film.get("name", "Neznámý název")
        film_id = film.get("id")
        genres_list = film.get("genres", [])

        if not film_id:
            print(f"Varování: Přeskakuji film '{film_name}' bez ID.")
            continue

        ET.SubElement(item, "title").text = film_name
        link_url = f'{BASE_KINOBEX_URL}/film/{film_id}'
        ET.SubElement(item, "link").text = link_url

        genre_names = [g.get("name") for g in genres_list if g.get("name")]
        description_text = ""
        if genre_names:
             description_text = f"Žánry: {', '.join(genre_names)}"
        if description_text:
             ET.SubElement(item, "description").text = description_text

        # Přidání <guid> tagu s URL jako permalinkem
        ET.SubElement(item, "guid", isPermaLink="true").text = link_url


# --- Uložení do souboru s pěkným zalomením ---
print("\nUkládám RSS feed do souboru...")
try:
    rough_string = ET.tostring(rss, encoding='utf-8', method='xml', xml_declaration=True)
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    pretty_xml_lines = pretty_xml.decode('utf-8').splitlines()
    clean_xml_output = "\n".join([line for line in pretty_xml_lines if line.strip()])

    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir and not os.path.exists(output_dir):
        print(f"Vytvářím adresář: {output_dir}")
        os.makedirs(output_dir)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(clean_xml_output)

    print(f"RSS feed byl úspěšně vytvořen jako '{OUTPUT_FILE}'")

except Exception as e:
    print(f"Chyba při formátování nebo ukládání XML: {e}", file=sys.stderr)
    sys.exit(1)
