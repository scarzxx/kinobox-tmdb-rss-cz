import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree

url = 'https://www.themoviedb.org/movie'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, 'html.parser')

rss = Element('rss')
rss.set('version', '2.0')
channel = SubElement(rss, 'channel')
SubElement(channel, 'title').text = 'TMDB trendy'
SubElement(channel, 'link').text = url

cards = soup.find_all('div', class_='card style_1')
for card in cards:
    title_tag = card.find('h2')
    title = title_tag.get_text(strip=True)

    href = title_tag.find('a')['href']
    full_link = f"https://www.themoviedb.org{href}"

    score_tag = card.find('div', class_='user_score_chart')
    score = score_tag['data-percent'] if score_tag else 'N/A'

    image_tag = card.find('img')
    image_url = image_tag['src'] if image_tag else ''

    date_tag = card.find('p')
    date_text = date_tag.get_text(strip=True) if date_tag else ''
    year = date_text[-4:] if len(date_text) >= 4 else 'N/A'

    item = SubElement(channel, 'item')
    SubElement(item, 'title').text = title
    SubElement(item, 'link').text = full_link
    SubElement(item, 'poster').text = image_url
    SubElement(item, 'hodnoceni').text = f"{score}%"
    SubElement(item, 'year').text = year

# Uložení do souboru
ElementTree(rss).write("tmdb_trendy.xml", encoding="utf-8", xml_declaration=True)
