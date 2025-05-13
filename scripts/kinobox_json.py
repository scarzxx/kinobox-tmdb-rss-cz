import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from xml.dom import minidom
import json

# --- KONFIGURACE ---
# VAROVÁNÍ: Tato URL obsahuje build ID a pravděpodobně brzy přestane fungovat!
# Může být nutné ji aktualizovat z https://www.kinobox.cz/_next/data/[build_id]/cs/filmy/trendy.json
# kde [build_id] najdete ve zdrojovém kódu stránky https://www.kinobox.cz/filmy/trendy
JSON_URL = "https://www.kinobox.cz/_next/data/QElPo9wDTJ4y2ojoTuYqm/cs/filmy/trendy.json"
OUTPUT_FILE = "feed/kinobox_trendy_rss.xml"
PRAGUE_TZ = pytz.timezone('Europe/Prague') # Tato se už nepoužije pro pubDate v itemu, ale necháme ji pro lastBuildDate kanálu

# Funkce format_duration už není potřeba, protože délka nebude v description
# def format_duration(total_minutes): ...

print(f"Stahuji JSON data z: {JSON_URL}")
print("VAROVÁNÍ: Pokud skript selže, zkontrolujte, zda se nezměnila URL (build ID).")

try:
    response = requests.get(JSON_URL, timeout=15)
    response.raise_for_status() # Zkontroluje chyby HTTP
    data = response.json()
    # Ověření cesty k filmům
    if "pageProps" not in data or "filmsOut" not in data["pageProps"] or "items" not in data["pageProps"]["filmsOut"]:
         raise KeyError("Chybějící klíč v očekávané cestě k filmům ('pageProps.filmsOut.items')")
    films = data["pageProps"]["filmsOut"]["items"]
    print(f"Nalezeno {len(films)} filmů v JSON.")

except requests.exceptions.RequestException as e:
    print(f"Chyba při stahování JSON: {e}")
    print("Zkontrolujte URL a připojení k internetu.")
    exit()
except (json.JSONDecodeError, KeyError) as e:
    print(f"Chyba při zpracování JSON nebo chybějící klíč: {e}")
    print("Struktura JSON dat se mohla změnit nebo URL již není platná.")
    exit()
except Exception as e:
     print(f"Neočekávaná chyba: {e}")
     exit()


# --- Vytvoření RSS struktury kanálu ---
rss = ET.Element("rss", version="2.0")
rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
channel = ET.SubElement(rss, "channel")

# Informace o kanálu (ponechány standardní)
ET.SubElement(channel, "title").text = "Trendy filmy – Kinobox.cz"
ET.SubElement(channel, "link").text = "https://www.kinobox.cz/filmy/trendy"
ET.SubElement(channel, "description").text = "Aktuálně nejvíce trendy filmy na Kinobox.cz"
ET.SubElement(channel, "language").text = "cs-cz"
# Odkaz na samotný RSS feed (ponechán)
atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
# !! DŮLEŽITÉ: Nahraď tuto URL skutečnou finální URL, kde bude feed hostován !!
atom_link.set("href", "https://raw.githubusercontent.com/scarzxx/kinobox-rss/refs/heads/main/feed/kinobox_trendy_rss.xml")
atom_link.set("rel", "self")
atom_link.set("type", "application/rss+xml")
# Datum poslední sestavení feedu (ponecháno standardní)
ET.SubElement(channel, "lastBuildDate").text = datetime.now(PRAGUE_TZ).strftime("%a, %d %b %Y %H:%M:%S %z")


# --- Zpracování jednotlivých filmů (itemů) ---
for film in films:
    item = ET.SubElement(channel, "item")
    film_name = film.get("name", "Neznámý název")
    film_id = film.get("id")
    # Načítáme data, ale pro item použijeme jen žánry
    genres_list = film.get("genres", [])

    if not film_id:
        print(f"Varování: Přeskakuji film '{film_name}' bez ID.")
        continue

    # --- Standardní tagy pro item: title, link, description ---

    # Tag <title>
    ET.SubElement(item, "title").text = film_name

    # Tag <link>
    link_url = f'https://www.kinobox.cz/film/{film_id}'
    ET.SubElement(item, "link").text = link_url

   #permalink
   ET.SubElement(item, "guid", isPermaLink="true").text = link_url

    # Tag <description> - POUZE ŽÁNRY
    genre_names = [g.get("name") for g in genres_list if g.get("name")]
    description_text = "" # Inicializace prázdného textu pro description
    if genre_names:
         # V description bude jen řádek s žánry
         description_text = f"Žánry: {', '.join(genre_names)}"

    # Přidání tagu <description> - jen pokud description_text není prázdný (tj. pokud film má žánry)
    if description_text:
         ET.SubElement(item, "description").text = description_text
    # Else: Pokud film nemá žánry, tag <description> pro tento item nebude přidán.

    # --- Ostatní standardní tagy pro item (guid, pubDate) jsou VYNECHÁNY podle požadavku ---
    # Pokud bys je v budoucnu chtěl vrátit, odkomentuj příslušné řádky:
     #ET.SubElement(item, "guid", isPermaLink="true").text = link_url
    # ... logika pro pubDate ...
    # ET.SubElement(item, "pubDate").text = pub_date_rfc822


# --- Uložení do souboru s pěkným zalomením (nemění se) ---
try:
    rough_string = ET.tostring(rss, encoding='utf-8', method='xml', xml_declaration=True)
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    pretty_xml_lines = pretty_xml.decode('utf-8').splitlines()
    first_content_line_index = 0
    for i, line in enumerate(pretty_xml_lines):
        if line.strip().startswith('<rss'):
             first_content_line_index = i
             break
    clean_xml_output = '\n'.join(pretty_xml_lines[:1] + pretty_xml_lines[first_content_line_index:])


    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(clean_xml_output)

    print(f"RSS feed byl úspěšně vytvořen jako '{OUTPUT_FILE}'")

except Exception as e:
    print(f"Chyba při formátování nebo ukládání XML: {e}")