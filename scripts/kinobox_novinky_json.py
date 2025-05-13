import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from xml.dom import minidom # Stále potřebujeme pro pěkné formátování a manipulaci s CDATA
import json
import os

# --- KONFIGURACE ---
# VAROVÁNÍ: Tato URL obsahuje build ID a pravděpodobně brzy přestane fungovat!
# Může být nutné ji aktualizovat z https://www.kinobox.cz/_next/data/[build_id]/cs/filmy/novinky.json
# kde [build_id] najdete ve zdrojovém kódu stránky https://www.kinobox.cz/filmy/novinky
JSON_URL = "https://www.kinobox.cz/_next/data/f5npQT84kcgxw3mp0b84H/cs/filmy/novinky.json"
OUTPUT_FILE = "feed/kinobox_novinky_rss.xml"
PRAGUE_TZ = pytz.timezone('Europe/Prague')

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

ET.SubElement(channel, "title").text = "Novinky – Kinobox.cz"
ET.SubElement(channel, "link").text = "https://www.kinobox.cz/filmy/novinky"
ET.SubElement(channel, "description").text = "Nejnovější filmy přidané na Kinobox.cz" # Můžeme upravit popis kanálu, když description položek je bohatší
ET.SubElement(channel, "language").text = "cs-cz"
atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
# !! DŮLEŽITÉ: Nahraď tuto URL skutečnou finální URL, kde bude feed hostován !!
atom_link.set("href", "githuburl") # Zde stále "githuburl" - NEZAPOMEŇ ZMĚNIT
atom_link.set("rel", "self")
atom_link.set("type", "application/rss+xml")
ET.SubElement(channel, "lastBuildDate").text = datetime.now(PRAGUE_TZ).strftime("%a, %d %b %Y %H:%M:%S %z")


# --- Zpracování jednotlivých filmů (itemů) ---
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
    link_url = f'https://www.kinobox.cz/film/{film_id}'
    ET.SubElement(item, "link").text = link_url

    # Tag <description> - NYNÍ S OBRÁZKEM A ŽÁNRY V HTML A CDATA
    description_parts_html = []

    # Přidat plakát jako <img> tag, pokud je k dispozici
    if poster_url:
        # Přidáme jednoduchý alt text a styl pro responzivitu
        description_parts_html.append(f'<img src="{poster_url}" alt="{film_name} plagát" style="max-width: 100%; height: auto;" />')

    # Přidat žánry, pokud jsou k dispozici
    genre_names = [g.get("name") for g in genres_list if g.get("name")]
    if genre_names:
        genres_text = f"Žánry: {', '.join(genre_names)}"
        # Můžeme přidat žánry jako odstavec pod obrázek
        description_parts_html.append(f'<p>{genres_text}</p>')
        # Nebo jednoduše na nový řádek pomocí <br/>, pokud nechceme <p>
        # description_parts_html.append(f'{genres_text}') # A pak joinovat pomocí "<br/>"

    # Spojení všech částí description do jednoho HTML řetězce
    # Použijeme "<br/>" pro oddělení obrázku a textu, pokud jsou oba přítomny
    description_html_content = "<br/>".join(description_parts_html)


    # Přidání tagu <description> s obsahem v CDATA, pokud je nějaký obsah
    if description_html_content:
        # ElementTree nativně nepodporuje CDATA v textových uzlech,
        # takže vložíme HTML obsah jako text a CDATA zabalení provedeme
        # následně při zpracování minidom pro pretty-printing.
        desc_elem = ET.SubElement(item, "description")
        desc_elem.text = description_html_content


# --- Uložení do souboru s pěkným zalomením a CDATA ---
try:
    # Generujeme XML string z ElementTree
    # ElementTree.tostring bude escapovat HTML znaky uvnitř description textu (< na < atd.)
    rough_string = ET.tostring(rss, encoding='utf-8', method='xml')

    # Parsujeme string pomocí minidom pro pěkné formátování a manipulaci s CDATA
    reparsed = minidom.parseString(rough_string)

    # Najdeme všechny elementy <description> a jejich obsah zabalíme do CDATA sekce
    for item_elem in reparsed.getElementsByTagName('item'):
        description_elements = item_elem.getElementsByTagName('description')
        if description_elements:
            desc_elem_dom = description_elements[0]
            # Získáme aktuální textový obsah (který byl escapován ElementTree)
            # Musíme ho "unescapovat" před zabalením do CDATA, pokud ET provedlo escapování.
            # Nicméně, minidom parseString by měl escapované entity převést zpět na znaky.
            # Takže stačí vzít textový obsah z DOM elementu.
            # Spojíme všechny textové uzly uvnitř description elementu
            current_text = ''.join(node.data for node in desc_elem_dom.childNodes if node.nodeType == node.TEXT_NODE)

            # Odstraníme stávající textové uzly
            for node in list(desc_elem_dom.childNodes):
                desc_elem_dom.removeChild(node)

            # Vytvoříme novou CDATA sekci s (již snad unescapovaným) textovým obsahem
            cdata_section = reparsed.createCDATASection(current_text)

            # Připojíme CDATA sekci k description elementu
            desc_elem_dom.appendChild(cdata_section)

    # Hezky naformátujeme upravený minidom dokument
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    # Odstraníme potenciální prázdné řádky na začátku od toprettyxml a zajistíme <?xml...> hlavičku
    pretty_xml_lines = pretty_xml.decode('utf-8').splitlines()
    first_content_line_index = 0
    for i, line in enumerate(pretty_xml_lines):
        if line.strip().startswith('<rss'):
             first_content_line_index = i
             break
    clean_xml_output = '\n'.join(pretty_xml_lines[:1] + pretty_xml_lines[first_content_line_index:])

    # Zkontrolujeme, zda existuje adresář pro výstup, a pokud ne, vytvoříme ho
    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir and not os.path.exists(output_dir):
        print(f"Vytvářím adresář: {output_dir}")
        os.makedirs(output_dir)

    # Uložení souboru - použijeme 'w' režim s encoding="utf-8" pro textový výstup
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(clean_xml_output)

    print(f"RSS feed byl úspěšně vytvořen jako '{OUTPUT_FILE}'")

except Exception as e:
    print(f"Chyba při formátování nebo ukládání XML: {e}")