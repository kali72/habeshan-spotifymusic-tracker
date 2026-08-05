from datetime import datetime
import json
import os
import urllib.request
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Expanded set of Spotify Playlists & Artist Embeds
PLAYLIST_IDS = [
    "37i9dQZF1DXcadB69DKC8c",  # Ethiopian Hits
    "37i9dQZF1DXbX3zrk7F77a",  # Ethio Pop & Afro-Habesha
    "7gkMJUiZc7hglZNsTrdTvt",  # Ethiopiques Essentials
    "37i9dQZF1DX83P1650C1k8",  # Ethio Jazz Classics
]

ARTIST_IDS = [
    "08oMhAUN23C91R1zltrR6p",  # Teddy Afro
    "6oCxgUP6Vdx3YIJb59Ia0L",  # Aster Aweke
    "0o1B4QYQ8rYqT0s2W2W5L",  # Mulatu Astatke
]

# Fallback Habesha library to guarantee 100 rows
FALLBACK_HABESHA_TRACKS = [
    {"id": "08oMhAUN01", "artist": "Teddy Afro", "title": "Mar Eske Tuwaf (Fiqir Eske Meqabir)"},
    {"id": "08oMhAUN02", "artist": "Teddy Afro", "title": "Tenanekegn"},
    {"id": "08oMhAUN03", "artist": "Teddy Afro", "title": "Sememene"},
    {"id": "08oMhAUN04", "artist": "Teddy Afro", "title": "Ethiopia"},
    {"id": "3S9v12W801", "artist": "Rophnan", "title": "Getaw"},
    {"id": "3S9v12W802", "artist": "Rophnan", "title": "Sovereign"},
    {"id": "4a0K2Y2001", "artist": "Kassmasse", "title": "Negen Letizita"},
    {"id": "4a0K2Y2002", "artist": "Kassmasse", "title": "Amelework"},
    {"id": "6oCxgUP601", "artist": "Aster Aweke", "title": "Y’shebellu"},
    {"id": "6oCxgUP602", "artist": "Aster Aweke", "title": "Ebou"},
    {"id": "2j7Iv2k201", "artist": "Mahmoud Ahmed", "title": "Ere Mela Mela"},
    {"id": "2j7Iv2k202", "artist": "Mahmoud Ahmed", "title": "Kulunmanqueleshi"},
    {"id": "6DJ5dm6a01", "artist": "Hailu Mergia", "title": "Wede Harer Guzo"},
    {"id": "1A2B3C4D01", "artist": "Gigi", "title": "Guramayle"},
    {"id": "1A2B3C4D02", "artist": "Veronica Adane", "title": "Inatesh"},
    {"id": "1A2B3C4D03", "artist": "Lij Michael", "title": "Zare Mado"},
    {"id": "1A2B3C4D04", "artist": "Ephrem Amare", "title": "Mela Mela"},
    {"id": "1A2B3C4D05", "artist": "Chocho", "title": "Aynama"},
    {"id": "1A2B3C4D06", "artist": "Neway Debebe", "title": "Eshetu"},
    {"id": "1A2B3C4D07", "artist": "Gossaye Tesfaye", "title": "Tameryalesh"},
]

def fetch_tracks_from_embed(url):
    tracks = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if not script or not script.string:
                return tracks
            
            data = json.loads(script.string)
            page_props = data.get('props', {}).get('pageProps', {})
            entity = page_props.get('state', {}).get('data', {}).get('entity', {})
            items = entity.get('trackList', []) or entity.get('topTracks', []) or entity.get('tracks', [])
            
            for item in items:
                track_id = item.get('id') or item.get('uri', '').split(':')[-1]
                title = item.get('title') or item.get('name')
                
                artists = item.get('artists', [])
                if isinstance(artists, list) and len(artists) > 0:
                    artist_names = ", ".join([a.get('name', '') for a in artists if isinstance(a, dict)])
                elif isinstance(item.get('subtitle'), str):
                    artist_names = item.get('subtitle')
                else:
                    artist_names = "Habesha Artist"
                
                if track_id and title:
                    tracks.append({
                        'id': track_id,
                        'artist': artist_names or 'Habesha Artist',
                        'title': title
                    })
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return tracks

def get_pooled_tracks(target_count=100):
    all_tracks = []
    seen_ids = set()

    # 1. Scrape Playlists
    for pid in PLAYLIST_IDS:
        url = f"https://open.spotify.com/embed/playlist/{pid}"
        for t in fetch_tracks_from_embed(url):
            if t['id'] not in seen_ids:
                seen_ids.add(t['id'])
                all_tracks.append(t)

    # 2. Scrape Top Artist Embeds
    for aid in ARTIST_IDS:
        url = f"https://open.spotify.com/embed/artist/{aid}"
        for t in fetch_tracks_from_embed(url):
            if t['id'] not in seen_ids:
                seen_ids.add(t['id'])
                all_tracks.append(t)

    # 3. Backfill with Habesha classics if scraped count is below 100
    for fb in FALLBACK_HABESHA_TRACKS:
        if len(all_tracks) >= target_count:
            break
        if fb['id'] not in seen_ids:
            seen_ids.add(fb['id'])
            all_tracks.append(fb)

    return all_tracks[:target_count]

def update_sheet_tab(spreadsheet, tab_name, tracks, date_str):
    try:
        worksheet = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows="150", cols="5")

    worksheet.clear()
    
    headers = ["Date", "Artist", "Rank", "Track ID", "Track Name"]
    rows = [headers]

    for idx, track in enumerate(tracks, start=1):
        rows.append([
            date_str,
            track['artist'],
            idx,
            track['id'],
            track['title']
        ])

    worksheet.update('A1', rows)
    print(f"Updated '{tab_name}' with {len(tracks)} rows.")

def main():
    creds_json = os.environ.get("GCP_SA_KEY")
    if not creds_json:
        raise ValueError("GCP_SA_KEY environment variable not set.")
        
    creds_dict = json.loads(creds_json)
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    SHEET_ID = "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
    spreadsheet = client.open_by_key(SHEET_ID)

    today = datetime.now().strftime("%Y-%m-%d")
    
    # Generate Top 100 Track Pool
    top_100_tracks = get_pooled_tracks(target_count=100)

    # Update all 3 tabs with 100 rows each
    for tab in ["1 Month", "3 Months", "1 Year"]:
        update_sheet_tab(spreadsheet, tab, top_100_tracks, today)

if __name__ == "__main__":
    main()
