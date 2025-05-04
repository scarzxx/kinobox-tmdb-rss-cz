import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz # Přidáno pro korektní časovou zónu v pubDate
from xml.dom import minidom
import json # Pro případnou chybu při parsování

# --- KONFIGURACE ---
# VAROVÁNÍ: Tato URL obsahuje build ID a pravděpodobně brzy přestane fungovat!
JSON_URL = "https://www.kinobox.cz/_next/data/1qG7m8WJ-AtZ5GALF4npj/cs/filmy/novinky.json"
OUTPUT_FILE = "feed/kinobox_novinky_rss.xml"
PRAGUE_TZ = pytz.timezone('Europe/Prague') # Časová zóna pro data

def format_duration(total_minutes):
    """Převede celkový počet minut na formát 'Xh Ym' nebo 'Ym'."""
    if total_minutes is None or not isinstance(total_minutes, int) or total_minutes <= 0:
        return None # Vracíme None, pokud není platná délka
    hours = total_minutes // 60
    minutes = total_minutes % 60
    duration_str = ""
    if hours > 0:
        duration_str += f"{hours}h"
    if minutes > 0:
        if duration_str: # Přidá mezeru, pokud už máme hodiny
             duration_str += " "
        duration_str += f"{minutes}m"
    return duration_str if duration_str else None # Vracíme None, pokud je výsledek prázdný

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


# --- Vytvoření RSS struktury ---
rss = ET.Element("rss", version="2.0")
rss.set("xmlns:atom", "http://www.w3.org/2005/Atom") # Namespace pro atom:link
channel = ET.SubElement(rss, "channel")

ET.SubElement(channel, "title").text = "Novinky filmy – Kinobox.cz"
ET.SubElement(channel, "link").text = "https://www.kinobox.cz/filmy/novinky"
ET.SubElement(channel, "description").text = "Nejnovější trendující filmy na Kinoboxu (data v samostatných tazích)"
ET.SubElement(channel, "language").text = "cs-cz"
# Přidání odkazu na samotný RSS feed
atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
# !! DŮLEŽITÉ: Nahraď tuto URL skutečnou finální URL, kde bude feed hostován !!
atom_link.set("href", "githuburl")
atom_link.set("rel", "self")
atom_link.set("type", "application/rss+xml")
ET.SubElement(channel, "lastBuildDate").text = datetime.now(PRAGUE_TZ).strftime("%a, %d %b %Y %H:%M:%S %z")


for film in films:
    item = ET.SubElement(channel, "item")
    film_name = film.get("name", "Neznámý název")
    film_id = film.get("id")
    poster_url = film.get("poster")
    score = film.get("score")
    year_val = film.get("year") # Hodnota roku
    duration_minutes = film.get("duration")
    genres_list = film.get("genres", [])
    providers_list = film.get("providers", [])
    release_cz_str = film.get("releaseCz")

    if not film_id:
        print(f"Varování: Přeskakuji film '{film_name}' bez ID.")
        continue

    # --- Základní tagy ---
    ET.SubElement(item, "title").text = film_name
    link_url = f'https://www.kinobox.cz/film/{film_id}'
    ET.SubElement(item, "link").text = link_url
    #ET.SubElement(item, "guid", isPermaLink="true").text = link_url # GUID

    # --- Vlastní tagy podle tvé specifikace ---
    if poster_url:
        ET.SubElement(item, "poster").text = poster_url

    if score is not None:
        ET.SubElement(item, "hodnoceni").text = f"{score}%"

    duration_formatted = format_duration(duration_minutes)
    if duration_formatted:
        ET.SubElement(item, "delka").text = f"{duration_formatted}"

    if year_val:
        ET.SubElement(item, "year").text = f"{year_val}"

    provider_names = [p.get("name") for p in providers_list if p.get("name")]
    providers_str = ", ".join(provider_names)
    if providers_str:
        ET.SubElement(item, "providers").text = providers_str

    genre_names = [g.get("name") for g in genres_list if g.get("name")]
    genres_str = ", ".join(genre_names)
    if genres_str:
        ET.SubElement(item, "genres").text = genres_str

    # --- Datum vydání ---
    if release_cz_str:
        try:
            naive_dt = datetime.strptime(release_cz_str, '%Y-%m-%d')
            aware_dt = PRAGUE_TZ.localize(naive_dt)
            # Formát s offsetem +0100 (nebo +0200 v létě)
            pub_date_rfc822 = aware_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
            # Pokud bys trval na UTC (+0000), použij:
            # pub_date_rfc822 = aware_dt.astimezone(pytz.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
            ET.SubElement(item, "pubDate").text = pub_date_rfc822
        except (ValueError, TypeError) as e:
            print(f" Varování: Nepodařilo se naparsovat datum '{release_cz_str}' pro film '{film_name}'. Chyba: {e}")

    # Tag <description> se nepřidává


# --- Uložení do souboru s pěkným zalomením ---
try:
    rough_string = ET.tostring(rss, encoding='utf-8', method='xml')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    with open(OUTPUT_FILE, "wb") as f:
        f.write(pretty_xml)

    print(f"RSS feed byl úspěšně vytvořen jako '{OUTPUT_FILE}'")

except Exception as e:
    print(f"Chyba při formátování nebo ukládání XML: {e}")
