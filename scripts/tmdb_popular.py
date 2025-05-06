import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import os

url = 'https://www.themoviedb.org/movie?language=cs-CZ'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, 'html.parser')

rss = Element('rss')
rss.set('version', '2.0')
channel = SubElement(rss, 'channel')
SubElement(channel, 'title').text = 'TMDB Popular'
SubElement(channel, 'link').text = url
SubElement(channel, 'description').text = 'Top filmy z TMDB'

cards = soup.find_all('div', class_='card style_1')
for card in cards:
    title_tag = card.find('h2')
    if not title_tag:
        continue
    title = title_tag.get_text(strip=True)
    link_tag = title_tag.find('a')
    if not link_tag:
        continue
    href = link_tag['href']
    full_link = f"https://www.themoviedb.org{href}"

    score_tag = card.find('div', class_='user_score_chart')
    score = score_tag['data-percent'] if score_tag else 'N/A'

    date_tag = card.find('p')
    date_text = date_tag.get_text(strip=True) if date_tag else ''

    description = f"{date_text} | Hodnocení: {score}%"

    item = SubElement(channel, 'item')
    SubElement(item, 'title').text = title
    SubElement(item, 'link').text = full_link
    SubElement(item, 'description').text = description

# Zajištění složky
os.makedirs("feed", exist_ok=True)

# Uložení do souboru s formátováním
xml_str = tostring(rss, 'utf-8')
parsed_str = minidom.parseString(xml_str)
with open("feed/tmdb_popular_rss.xml", "w", encoding="utf-8") as f:
    f.write(parsed_str.toprettyxml(indent="  "))
