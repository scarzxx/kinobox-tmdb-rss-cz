import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from xml.dom import minidom
import os
import sys

# --- KONFIGURACE ---
URL = 'https://www.themoviedb.org/movie' # Stránka s populárními filmy
OUTPUT_FILE = "feed/tmdb_popular_rss.xml" # Cesta k výstupnímu souboru v adresáři feed/
PRAGUE_TZ = pytz.timezone('Europe/Prague') # Časová zóna pro lastBuildDate kanálu (i když zdroj je anglicky, pro sestavení feedu použijeme místní čas)

# Pro TMDB není potřeba dynamické Build ID ani nastavení lokále pro datum
# (data z TMDB popular stránky jsou v standardním anglickém formátu MM/DD/YYYY).


# --- Stahování a zpracování HTML ---
print(f"Stahuji data z: {URL}")
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'}
try:
    response = requests.get(URL, headers=headers, timeout=15)
    response.raise_for_status() # Zkontroluje chyby HTTP
    soup = BeautifulSoup(response.text, 'html.parser')
    print("HTML staženo a naparsováno.")

except requests.exceptions.RequestException as e:
    print(f"Chyba při stahování HTML z {URL}: {e}", file=sys.stderr)
    print("Zkontrolujte URL a připojení k internetu.", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Neočekávaná chyba při parsování HTML: {e}", file=sys.stderr)
    sys.exit(1)


# --- Vytvoření RSS struktury kanálu ---
rss = ET.Element('rss', version='2.0')
rss.set("xmlns:atom", "http://www.w3.org/2005/Atom") # Namespace pro atom:link
channel = ET.SubElement(rss, 'channel')

ET.SubElement(channel, 'title').text = 'TMDB Populární filmy' # Titulek
ET.SubElement(channel, 'link').text = URL # Odkaz na zdrojovou stránku
ET.SubElement(channel, 'description').text = 'Aktuálně nejoblíbenější filmy na TheMovieDB.org' # Popis kanálu
ET.SubElement(channel, 'language').text = 'en-us' # Jazyk (TMDB je primárně anglicky)
# Přidání odkazu na samotný RSS feed
atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
# !! DŮLEŽITÉ: Nahraď tuto URL skutečnou finální URL, kde bude feed hostován !!
atom_link.set("href", "https://raw.githubusercontent.com/scarzxx/kinobox-rss/refs/heads/main/feed/tmdb_popular_rss.xml") # Příklad URL - NEZAPOMEŇ ZMĚNIT
atom_link.set("rel", "self")
atom_link.set("type", "application/rss+xml")
# Datum poslední sestavení feedu
ET.SubElement(channel, "lastBuildDate").text = datetime.now(PRAGUE_TZ).strftime("%a, %d %b %Y %H:%M:%S %z") # Použijeme Pražskou časovou zónu pro sestavení feedu


# --- Zpracování jednotlivých filmů (itemů) ---
print("Zpracovávám filmy pro RSS feed...")
cards = soup.find_all('div', class_='card style_1')

if not cards:
    print("Nenalezeny žádné filmové karty na stránce.", file=sys.stderr)
else:
    for card in cards:
        item = ET.SubElement(channel, 'item')

        # Získání dat
        title_tag = card.find('h2')
        title = title_tag.get_text(strip=True) if title_tag else 'Neznámý název'

        href_tag = card.find('h2').find('a') if card.find('h2') else None
        href = href_tag['href'] if href_tag and 'href' in href_tag.attrs else None
        full_link = f"https://www.themoviedb.org{href}" if href else URL # Odkaz na detail filmu, fallback na URL kanálu

        score_tag = card.find('div', class_='user_score_chart')
        score = score_tag['data-percent'] if score_tag and 'data-percent' in score_tag.attrs else None # None místo 'N/A' pro případné vynechání v description

        image_tag = card.find('img')
        # TMDB často používá relativní cesty //image.tmdb.org...
        image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else ''
        if image_url.startswith('//'):
             image_url = f'https:{image_url}' # Přidáme https: prefix
        # Někdy se ve src může objevit placeholder
        # Ten pro účely RSS asi nechceme, můžeme ho filtrovat
        if 'glyphicons-basic-' in image_url or image_url == '':
             image_url = None # Nastavíme na None, pokud je to placeholder nebo prázdné


        date_tag = card.find('p')
        date_text = date_tag.get_text(strip=True) if date_tag else ''
        # TMDB na stránce s populárními filmy dává datum v formátu MM/DD/YYYY
        year = None # Inicializujeme rok na None
        date_for_pubdate = None # Inicializujeme datum pro pubDate na None
        if date_text:
             try:
                 # Zkusíme parsovat datum z data_text (očekáváme MM/DD/YYYY)
                 date_for_pubdate = datetime.strptime(date_text, '%m/%d/%Y')
                 year = str(date_for_pubdate.year) # Získáme rok z parsovaného data
             except (ValueError, TypeError):
                  # Print warning only if the text is not empty, to avoid warnings for missing dates
                  if date_text.strip():
                      print(f" Varování: Nepodařilo se naparsovat datum '{date_text}' pro film '{title}' pro pubDate. PubDate vynechán.")
                  pass # date_for_pubdate zůstane None


        # --- Standardní tagy pro item: title, link, description, guid, pubDate (pokud datum dostupné) ---

        # Tag <title>
        ET.SubElement(item, 'title').text = title

        # Tag <link>
        # Tag <link> musí být vždy přítomen v itemu dle RSS 2.0 specifikace
        link_element = ET.SubElement(item, 'link')
        if full_link:
             link_element.text = full_link
        else:
             link_element.text = URL # Fallback na URL kanálu, pokud link není dostupný

        # Tag <guid> - Unikátní identifikátor, použijeme link jako permalink (standardní praxe)
        # GUID by měl být unikátní. Link je dobrá volba, pokud je stabilní.
        # Pokud není full_link, GUID by měl být nějaký jiný unikátní řetězec nebo chybět.
        # Pro jednoduchost a v souladu s tím, co máme, vynecháme, pokud není full_link.
        if full_link:
             ET.SubElement(item, 'guid', isPermaLink="true").text = full_link
        # Else: GUID se nepřidá, pokud není full_link

        # Tag <pubDate> - Použijeme parsované datum, pokud bylo úspěšné
        if date_for_pubdate:
            # Přidáme časovou zónu (např. UTC, protože neznáme přesný čas vydání)
            aware_dt = pytz.utc.localize(date_for_pubdate)
            # Formát RFC 822 s UTC offsetem +0000
            pub_date_rfc822 = aware_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            ET.SubElement(item, 'pubDate').text = pub_date_rfc822


        # Tag <description> - S OBRÁZKEM, HODNOCENÍM A ROKEM V HTML A CDATA
        description_parts_html = []

        # Přidat plakát jako <img> tag, pokud je k dispozici (a není placeholder/None)
        if image_url: # image_url je nyní None, pokud byl placeholder nebo prázdný
            # Přidáme jednoduchý alt text a styl pro responzivitu a odsazení pod obrázkem
            description_parts_html.append(f'<img src="{image_url}" alt="{title} poster" style="max-width: 100%; height: auto; display: block; margin-bottom: 10px;" />')

        # Přidat hodnocení, pokud je k dispozici (None)
        if score is not None: # Kontrolujeme, zda score není None (původně mohlo být 'N/A' nebo None)
             description_parts_html.append(f'<p>Hodnocení: {score}%</p>')

        # Přidat rok, pokud byl parsován z data
        if year: # Kontrolujeme, zda year byl úspěšně extrahován z data (string)
             description_parts_html.append(f'<p>Rok: {year}</p>')


        # Spojení všech částí description do jednoho HTML řetězce
        description_html_content = "".join(description_parts_html)


        # Přidání tagu <description> s obsahem, pokud je nějaký smysluplný obsah
        # Kontrolujeme, jestli list description_parts_html není prázdný.
        if description_parts_html: # Tedy pokud jsme něco přidali (obrázek, hodnocení, rok)
            # ElementTree nativně nepodporuje CDATA, vkládáme čistý HTML string.
            # Zabalení do CDATA proběhne později s minidom.
            desc_elem = ET.SubElement(item, 'description')
            # ElementTree automaticky escapuje znaky jako <, >, & v textu,
            # což je pro nás OK, protože minidom je při parsování zase unescapuje.
            desc_elem.text = description_html_content
        # Else: Pokud není k dispozici žádná doplňující data (obrázek, hodnocení, rok), tag <description> pro tento item nebude přidán.


# --- Uložení do souboru s pěkným zalomením a CDATA ---
print("\nUkládám RSS feed do souboru...")
try:
    # Generujeme XML string S XML deklarací pomocí ElementTree.
    # ElementTree.tostring vrací bytes. short_empty_elements=False pro kompatibilitu.
    # Ponecháme short_empty_elements=False, aby i prázdné description (pokud by se přidalo bez obsahu)
    # bylo <description></description> a ne <description/>, což může být důležité před zabalením do CDATA.
    rough_string_bytes = ET.tostring(rss, encoding='utf-8', method='xml', xml_declaration=True, short_empty_elements=False)

    # Parsujeme string (bytes) pomocí minidom.
    # minidom při parsování stringu obsahujícího <?xml...> PI vytvoří pro ni uzel.
    reparsed = minidom.parseString(rough_string_bytes)

    # Najdeme všechny elementy <description> a jejich obsah zabalíme do CDATA sekce
    # Zkontrolujeme, zda element existuje a má textový obsah (i prázdný string je textový obsah)
    for item_elem in reparsed.getElementsByTagName('item'): # Správné použití reparsed
        description_elements = item_elem.getElementsByTagName('description')
        if description_elements:
            desc_elem_dom = description_elements[0]
            # Získáme aktuální textový obsah z DOM elementu.
            # minidom.parseString by měl správně převést escapované entity zpět na znaky.
            current_text = ''.join(node.data for node in desc_elem_dom.childNodes if node.nodeType == node.TEXT_NODE)

            # Odstraníme stávající textové uzly
            for node in list(desc_elem_dom.childNodes):
                desc_elem_dom.removeChild(node)

            # Vytvoříme novou CDATA sekci s textovým obsahem (může být i prázdná)
            cdata_section = reparsed.createCDATASection(current_text) # Správné použití reparsed

            # Připojíme CDATA sekci k description elementu
            desc_elem_dom.appendChild(cdata_section)

    # Hezky naformátujeme upravený minidom dokument.
    # Metoda toprettyxml na objektu DOCUMENT (který vratil parseString)
    # automaticky zahrne <?xml...> PI, pokud v dokumentu existuje.
    # Argument xml_declaration zde NENÍ potřeba a způsobil by chybu.
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