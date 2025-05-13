import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from xml.dom import minidom # Stále potřebujeme pro pěkné formátování a manipulaci s CDATA
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
BASE_KINOBOX_URL = "https://www.kinobox.cz" # Opraveno překlep "KINOBEX"
TARGET_DATA_PATH = "/cs/filmy/trendy.json" # Tento skript se týká TRENDY filmů
OUTPUT_FILE = "feed/kinobox_trendy_rss.xml" # Cesta k výstupnímu souboru
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

ET.SubElement(channel, "title").text = "Trendy filmy – Kinobox.cz" # Titulek pro TRENDY
ET.SubElement(channel, "link").text = f"{BASE_KINOBOX_URL}/filmy/trendy"
ET.SubElement(channel, "description").text = "Aktuálně nejvíce trendy filmy na Kinobox.cz" # Popis pro TRENDY
ET.SubElement(channel, "language").text = "cs-cz"
atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
# !! DŮLEŽITÉ: Nahraď tuto URL skutečnou finální URL, kde bude feed hostován !!
# URL by měla odkazovat na tento konkrétní feed soubor (trendy)
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
        # Načítáme data pro title, link a description
        genres_list = film.get("genres", [])
        poster_url = film.get("poster") # Potřebujeme pro description

        if not film_id:
            print(f"Varování: Přeskakuji film '{film_name}' bez ID.")
            continue

        # --- Standardní tagy pro item: title, link, description ---

        # Tag <title>
        ET.SubElement(item, "title").text = film_name

        # Tag <link>
        link_url = f'{BASE_KINOBOX_URL}/film/{film_id}'
        ET.SubElement(item, "link").text = link_url

        # Tag <description> - S OBRÁZKEM A ŽÁNRY V HTML A CDATA
        description_parts_html = []

        # Přidat plakát jako <img> tag, pokud je k dispozici
        if poster_url:
            # Přidáme jednoduchý alt text a styl pro responzivitu a odsazení pod obrázkem
            # style="display: block; margin-bottom: 10px;" přidá obrázku blokový styl a trochu mezery pod ním
            description_parts_html.append(f'<img src="{poster_url}" alt="{film_name} plagát" style="max-width: 100%; height: auto; display: block; margin-bottom: 10px;" />')

        # Přidat žánry, pokud jsou k dispozici
        genre_names = [g.get("name") for g in genres_list if g.get("name")]
        if genre_names:
            genres_text = f"Žánry: {', '.join(genre_names)}"
            # Přidáme žánry jako odstavec pod obrázek (nebo jen text, pokud obrázek chybí)
            description_parts_html.append(f'<p>{genres_text}</p>')

        # Spojení všech částí description do jednoho HTML řetězce
        # Pokud je jen obrázek a žánry, spojíme je prázdným řetězcem, protože <p> už zalomí řádek
        description_html_content = "".join(description_parts_html)

        # Přidání tagu <description> s obsahem, pokud je nějaký smysluplný obsah
        # Použijeme strip() pro kontrolu, jestli obsah není jen prázdné znaky nebo prázdné HTML tagy
        if description_html_content.strip():
            # ElementTree nativně nepodporuje CDATA, vkládáme čistý HTML string.
            # Zabalení do CDATA proběhne později s minidom.
            desc_elem = ET.SubElement(item, "description")
            # ElementTree automaticky escapuje znaky jako <, >, & v textu,
            # což je pro nás OK, protože minidom je při parsování zase unescapuje.
            desc_elem.text = description_html_content
        # Else: Pokud není k dispozici ani plakát, ani žánry, tag <description> pro tento item nebude přidán.


        # --- Ostatní standardní i vlastní tagy pro item jsou VYNECHÁNY ---
        # Původní <guid> tag je odstraněn podle požadavku na jen title, link, description.
        # Pokud byste ho chtěli vrátit:
        # ET.SubElement(item, "guid", isPermaLink="true").text = link_url


# --- Uložení do souboru s pěkným zalomením a CDATA ---
print("\nUkládám RSS feed do souboru...")
try:
    # Generujeme XML string S XML deklarací pomocí ElementTree.
    # ElementTree.tostring vrací bytes.
    rough_string_bytes = ET.tostring(rss, encoding='utf-8', method='xml', xml_declaration=True)

    # Parsujeme string (bytes) pomocí minidom.
    # minidom při parsování stringu obsahujícího <?xml...> PI vytvoří pro ni uzel.
    reparsed = minidom.parseString(rough_string_bytes)

    # Najdeme všechny elementy <description> a jejich obsah zabalíme do CDATA sekce
    for item_elem in reparsed.getElementsByTagName('item'):
        description_elements = item_elem.getElementsByTagName('description')
        if description_elements:
            desc_elem_dom = description_elements[0]
            # Získáme aktuální textový obsah z DOM elementu.
            # minidom.parseString by měl správně převést escapované entity zpět na znaky.
            current_text = ''.join(node.data for node in desc_elem_dom.childNodes if node.nodeType == node.TEXT_NODE)

            # Odstraníme stávající textové uzly
            for node in list(desc_elem_dom.childNodes):
                desc_elem_dom.removeChild(node)

            # Vytvoříme novou CDATA sekci s textovým obsahem
            cdata_section = reparsed.createCDATASection(current_text)

            # Připojíme CDATA sekci k description elementu
            desc_elem_dom.appendChild(cdata_section)

    # Hezky naformátujeme upravený minidom dokument.
    # Metoda toprettyxml na objektu DOCUMENT (který vratil parseString)
    # automaticky zahrne <?xml...> PI, pokud v dokumentu existuje (a my jsme zajistili, že existuje).
    # Argument xml_declaration zde NENÍ potřeba.
    pretty_xml_bytes = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    # Decode bytes na string pro zápis do souboru
    pretty_xml_str = pretty_xml_bytes.decode('utf-8')

    # Kontrola a vytvoření adresáře, pokud neexistuje
    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir and not os.path.exists(output_dir):
        print(f"Vytvářím adresář: {output_dir}")
        os.makedirs(output_dir)

    # Uložení souboru - použijeme 'w' režim s encoding="utf-8" pro textový výstup
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(pretty_xml_str) # Zapisujeme string

    print(f"RSS feed byl úspěšně vytvořen jako '{OUTPUT_FILE}'")

except Exception as e:
    print(f"Chyba při formátování nebo ukládání XML: {e}", file=sys.stderr)
    sys.exit(1)