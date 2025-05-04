import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import hashlib

# Funkce na výpočet SHA256 hash z textu
def get_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

# URL Kinobox trendy JSON
url = "https://www.kinobox.cz/_next/data/1qG7m8WJ-AtZ5GALF4npj/cs/filmy/trendy.json"

# Stažení dat
response = requests.get(url)
data = response.json()
films = data["pageProps"]["filmsOut"]["items"]

# Vytvoření RSS struktury
rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")

ET.SubElement(channel, "title").text = "Trendy filmy – Kinobox.cz"
ET.SubElement(channel, "link").text = "https://www.kinobox.cz/filmy/trendy"
ET.SubElement(channel, "description").text = "Nejnovější trendující filmy na Kinoboxu"

for film in films:
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = film.get("name", "Neznámý název")
    ET.SubElement(item, "link").text = f'https://www.kinobox.cz/film/{film["id"]}'
    
    # Popis
    description = f'<img src="{film["poster"]}" width="100"/><br/>'
    if "score" in film:
        description += f'Hodnocení: {film["score"]}%<br/>'
    if "genres" in film:
        genres = ", ".join([g["name"] for g in film["genres"]])
        description += f'Žánry: {genres}<br/>'
    if "providers" in film:
        providers = ", ".join([p["name"] for p in film["providers"]])
        description += f'Dostupné na: {providers}<br/>'
    ET.SubElement(item, "description").text = description

    release = film.get("releaseCz")
    if release:
        pub_date = datetime.strptime(release, "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000")
        ET.SubElement(item, "pubDate").text = pub_date

# Serializace XML jako string (abychom ho mohli porovnat)
new_xml_str = ET.tostring(rss, encoding="utf-8", method="xml").decode("utf-8")
new_hash = get_hash(new_xml_str)

# Cesta k feedu
os.makedirs("feed", exist_ok=True)
rss_path = "feed/kinobox_trendy_rss.xml"

# Porovnání s existujícím souborem
if os.path.exists(rss_path):
    with open(rss_path, "r", encoding="utf-8") as f:
        old_xml_str = f.read()
    old_hash = get_hash(old_xml_str)

    if new_hash == old_hash:
        print("RSS feed se nezměnil – neukládám.")
        exit(0)

# Uložení nového XML
with open(rss_path, "w", encoding="utf-8") as f:
    f.write(new_xml_str)
print("RSS feed byl aktualizován.")
