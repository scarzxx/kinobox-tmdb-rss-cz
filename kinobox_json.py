import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import os

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

    # Sestavení popisu (plakát, hodnocení, žánry)
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

    # Datum vydání jako pubDate (RSS formát)
    release = film.get("releaseCz")
    if release:
        pub_date = datetime.strptime(release, "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000")
        ET.SubElement(item, "pubDate").text = pub_date

# Uložení do souboru
output_file = 'feed/kinobox_trendy_rss.xml'
tree = ET.ElementTree(rss)
tree.write(output_file, encoding="utf-8", xml_declaration=True)

print(f"RSS feed byl vytvořen jako '{output_file}'")
