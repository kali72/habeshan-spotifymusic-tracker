import json
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

PLAYLIST_IDS = [
    "37i9dQZF1DXcadB69DKC8c",  # Ethiopian Hits
    "37i9dQZF1DXbX3zrk7F77a",  # Ethio Pop & Afro-Habesha
]

SEARCH_QUERIES = [
    "ethiopia",
    "amharic",
    "habesha",
    "ethio pop"
]

def parse_release_date(date_str):
    if not date_str:
        return None
    parts = date_str.split("-")
    try:
        if len(parts) == 3:
            return datetime.strptime(date_str, "%Y-%m-%d")
        elif len(parts) == 2:
            return datetime.strptime(date_str, "%Y-%m")
        elif len(parts) == 1:
            return datetime.strptime(date_str, "%Y")
    except ValueError:
        return None
    return None

def fetch_all_tracks(sp):
    unique_tracks = {}

    # 1. Fetch from modern Ethiopian Spotify Playlists
    for pid in PLAYLIST_IDS:
        try:
            results = sp.playlist_items(pid, limit=100)
            for item in results.get("items", []):
                track = item.get("track")
                if track and track.get("id") and track["id"] not in unique_tracks:
                    rel_date = parse_release_date(track["album"]["release_date"])
                    artist_names = ", ".join([a["name"] for a in track["artists"]])
                    unique_tracks[track["id"]] = {
                        "id": track["id"],
                        "artist": artist_names,
                        "title": track["name"],
                        "popularity": track.get("popularity", 0),
                        "release_date": rel_date or datetime(2020, 1, 1)
                    }
        except Exception as e:
            print(f"Error reading playlist {pid}: {e}")

    # 2. Search Spotify API for Ethiopian queries
    for query in SEARCH_QUERIES:
        try:
            results = sp.search(q=query, type="track", limit=50)
            for track in results.get("tracks", {}).get("items", []):
                t_id = track.get("id")
                if t_id and t_id not in unique_tracks:
                    rel_date = parse_release_date(track["album"]["release_date"])
                    artist_names = ", ".join([a["name"] for a in track["artists"]])
                    unique_tracks[t_id] = {
                        "id": t_id,
                        "artist": artist_names,
                        "title": track["name"],
                        "popularity": track.get("popularity", 0),
                        "release_date": rel_date or datetime(2020, 1, 1)
                    }
        except Exception as e:
            print(f"Error with query '{query}': {e}")

    return list(unique_tracks.values())

def get_tracks_for_timeframe(all_tracks, max_days):
    now = datetime.now()
    filtered = []
    for t in all_tracks:
        days_old = (now - t["release_date"]).days
        if 0 <= days_old <= max_days:
            filtered.append(t)
    
    filtered.sort(key=lambda x: x["popularity"], reverse=True)

    # Fallback: Fill remaining slots up to 100 with top popular tracks if date filter yields < 100
    if len(filtered) < 100:
        all_sorted = sorted(all_tracks, key=lambda x: x["popularity"], reverse=True)
        seen_ids = {t["id"] for t in filtered}
        for t in all_sorted:
            if t["id"] not in seen_ids:
                filtered.append(t)
                seen_ids.add(t["id"])
            if len(filtered) >= 100:
                break

    return filtered[:100]

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
            track["artist"],
            idx,
            track["id"],
            track["title"]
        ])

    worksheet.update("A1", rows)
    print(f"Updated '{tab_name}' with {len(rows) - 1} tracks.")

def main():
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    gcp_key = os.environ.get("GCP_SA_KEY")

    if not client_id or not client_secret or not gcp_key:
        raise ValueError("Missing environment variables.")

    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )
    )

    creds_dict = json.loads(gcp_key)
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    SHEET_ID = "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
    spreadsheet = client.open_by_key(SHEET_ID)
    today = datetime.now().strftime("%Y-%m-%d")

    all_tracks = fetch_all_tracks(sp)

    tracks_1_month = get_tracks_for_timeframe(all_tracks, max_days=30)
    tracks_3_months = get_tracks_for_timeframe(all_tracks, max_days=90)
    tracks_1_year = get_tracks_for_timeframe(all_tracks, max_days=365)

    update_sheet_tab(spreadsheet, "1 Month", tracks_1_month, today)
    update_sheet_tab(spreadsheet, "3 Months", tracks_3_months, today)
    update_sheet_tab(spreadsheet, "1 Year", tracks_1_year, today)

if __name__ == "__main__":
    main()
