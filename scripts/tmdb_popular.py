import requests
import json
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from dotenv import load_dotenv
import os

# --- Načtení .env souboru ---
load_dotenv()

# Získá absolutní cestu k adresáři, kde se skript nachází (např. .../kinobox_rss/scripts)
script_dir = os.path.dirname(os.path.abspath(__file__))

# --- API klíče ---
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TRAKT_CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID")
OUTPUT_FILE = os.path.join(script_dir, os.pardir, "feed", "tmdb_popular_rss.xml")

# Kontrola, zda je API klíč nastaven
if not TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY není nastavena v prostředí.")
if not TRAKT_CLIENT_ID:
    raise ValueError("TRAKT_CLIENT_ID není nastavena v prostředí.")

if TMDB_API_KEY == "token" or not TMDB_API_KEY:
    exit("API klíč není nastaven. Ukončuji skript.")

# --- TMDB API volání (více stránek) ---
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {TMDB_API_KEY}"
}

data = {"results": []}

for pages in range(1, 3):  # stránka 1 a 2
    url = f"https://api.themoviedb.org/3/discover/movie?include_adult=false&include_video=false&language=cs-CZ&page={pages}&sort_by=popularity.desc"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        page_data = response.json()
        if 'results' in page_data:
            data['results'].extend(page_data['results'])
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP chyba na stránce {pages}: {http_err}")
        print(f"Odpověď serveru: {response.text}")
    except requests.exceptions.RequestException as req_err:
        print(f"Chyba při volání API na stránce {pages}: {req_err}")
    except json.JSONDecodeError:
        print(f"Chyba při dekódování JSON odpovědi na stránce {pages}. Odpověď serveru:\n{response.text}")

# --- Tvorba RSS Feedu ---
fg = FeedGenerator()
fg.title('Oblíbené filmy - TheMovieDB')
fg.link(href='https://www.themoviedb.org/', rel='alternate')
fg.description('Seznam nejoblíbenější filmů z TheMovieDB.')
fg.language('cs-CZ')

IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

if 'results' in data and data['results']:
    for movie in data['results']:
        fe = fg.add_entry()
        fe.id(f"tmdb_movie_{movie['id']}")
        fe.title(movie['title'])  # title = cz | original_title = en

        movie_url = f"https://www.themoviedb.org/movie/{movie['id']}"
        fe.link(href=movie_url)

        description_html = ""
        if movie.get('poster_path'):
            poster_url = f"{IMAGE_BASE_URL}{movie['poster_path']}"
            description_html += f'<img src="{poster_url}" alt="Plakát filmu {movie["title"]}" style="max-width:200px; float:left; margin-right:10px;"/><br/>'

        description_html += f"<p>{movie.get('overview', 'Popis není k dispozici.')}</p>"
        if movie.get('vote_average'):
            description_html += f"<p>Hodnocení: {movie['vote_average']}/10 ({movie.get('vote_count', 0)} hlasů)</p>"

        # --- Trakt API ---
        trakt_url = None
        if TRAKT_CLIENT_ID:
            trakt_api_url = f"https://api.trakt.tv/search/tmdb/{movie['id']}?type=movie"
            trakt_headers = {
                "Content-Type": "application/json",
                "trakt-api-version": "2",
                "trakt-api-key": TRAKT_CLIENT_ID
            }
            try:
                trakt_response = requests.get(trakt_api_url, headers=trakt_headers, timeout=10)
                trakt_response.raise_for_status()
                trakt_data = trakt_response.json()
                if trakt_data:
                    slug = trakt_data[0]['movie']['ids']['slug']
                    trakt_url = f"https://trakt.tv/movies/{slug}"
                    description_html += f"<p><strong>Trakt:</strong> <a href='{trakt_url}'>{trakt_url}</a></p>"
            except requests.exceptions.RequestException as e:
                print(f"Chyba při získávání Trakt URL pro {movie['title']}: {e}")

        fe.description(description_html, isSummary=False)

        if movie.get('release_date'):
            try:
                release_dt = datetime.strptime(movie['release_date'], '%Y-%m-%d')
                release_dt_aware = release_dt.replace(tzinfo=timezone.utc)
                fe.pubDate(release_dt_aware)
            except ValueError:
                print(f"Varování: Neplatný formát data pro film {movie['title']}: {movie['release_date']}")

else:
    print("Nebyly nalezeny žádné filmy pro vytvoření RSS feedu.")

# --- Uložení RSS feedu ---
rss_feed_xml = fg.rss_str(pretty=True)

# Kontrola a vytvoření adresáře, pokud neexistuje
output_dir = os.path.dirname(OUTPUT_FILE)
if output_dir and not os.path.exists(output_dir):
    print(f"Vytvářím adresář: {output_dir}")
    os.makedirs(output_dir)

try:
    with open(OUTPUT_FILE, "wb") as f:
        f.write(rss_feed_xml)
    print(f"\nRSS feed byl úspěšně vygenerován a uložen do souboru '{OUTPUT_FILE}'")
except IOError as e:
    print(f"Chyba při ukládání souboru: {e}")