import os
import json
from datetime import datetime, timedelta
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import gspread
from google.oauth2.service_account import Credentials

def get_spotify_client():
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("Missing Spotify API credentials.")
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))

def get_gspread_client():
    creds_json = os.environ.get("GCP_SA_KEY")
    if not creds_json:
        raise ValueError("Missing GCP_SA_KEY environment variable.")
    info = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials)

def fetch_habesha_tracks(sp):
    unique_tracks = {}
    
    # Keyword Searches
    queries = ["Ethiopian", "Habesha", "Ethio Pop", "Amharic", "Ethiopia Hits"]
    for q in queries:
        try:
            results = sp.search(q=q, type="track", limit=50)
            for track in results.get("tracks", {}).get("items", []):
                if track and track.get("id"):
                    unique_tracks[track["id"]] = track
        except Exception as e:
            print(f"Search error for '{q}': {e}")

    # Playlist Searches
    playlists_q = ["Ethiopian Hits", "Habesha Music", "Best Ethiopian Songs", "Ethio Pop"]
    for q in playlists_q:
        try:
            playlists = sp.search(q=q, type="playlist", limit=3).get("playlists", {}).get("items", [])
            for pl in playlists:
                if not pl:
                    continue
                items = sp.playlist_items(pl["id"], limit=50).get("items", [])
                for item in items:
                    track = item.get("track")
                    if track and track.get("id"):
                        unique_tracks[track["id"]] = track
        except Exception as e:
            print(f"Playlist error for '{q}': {e}")

    return list(unique_tracks.values())

def parse_track_date(track):
    album = track.get("album", {})
    date_str = album.get("release_date", "")
    if not date_str:
        return datetime(2000, 1, 1).date()
    try:
        parts = date_str.split("-")
        if len(parts) == 1:
            return datetime.strptime(date_str, "%Y").date()
        elif len(parts) == 2:
            return datetime.strptime(date_str, "%Y-%m").date()
        else:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return datetime(2000, 1, 1).date()

def get_tracks_for_timeframe(all_tracks, max_days):
    today = datetime.now().date()
    cutoff = today - timedelta(days=max_days)

    processed = []
    for t in all_tracks:
        rel_date = parse_track_date(t)
        processed.append({"date": rel_date, "track": t})

    # Filter tracks inside cutoff window
    within_timeframe = [p for p in processed if p["date"] >= cutoff]
    within_timeframe.sort(key=lambda x: (x["date"], x["track"].get("popularity", 0)), reverse=True)

    selected = [p["track"] for p in within_timeframe]

    # Backfill with top popular tracks if strict date filter returns < 100 items
    if len(selected) < 100:
        seen_ids = {t["id"] for t in selected}
        remaining = [p["track"] for p in processed if p["track"]["id"] not in seen_ids]
        remaining.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        selected.extend(remaining[:100 - len(selected)])

    return selected[:100]

def prepare_rows(tracks):
    rows = [["Date", "Artist", "Rank", "Track ID", "Track Name"]]
    today_str = datetime.now().strftime("%Y-%m-%d")

    for rank, track in enumerate(tracks, start=1):
        artists = ", ".join([a["name"] for a in track.get("artists", [])])
        rows.append([
            today_str,
            artists,
            rank,
            track.get("id", ""),
            track.get("name", "")
        ])
    return rows

def update_sheet_tab(sheet, tab_name, rows):
    try:
        try:
            worksheet = sheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=tab_name, rows="150", cols="10")

        worksheet.clear()
        worksheet.update(values=rows, range_name="A1")
        print(f"Updated '{tab_name}' with {len(rows)-1} tracks.")
    except Exception as e:
        print(f"Error updating '{tab_name}': {e}")

def main():
    sp = get_spotify_client()
    gc = get_gspread_client()

    sheet_id = os.environ.get("SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU")
    sheet = gc.open_by_key(sheet_id)

    all_tracks = fetch_habesha_tracks(sp)

    timeframes = [
        ("1 Month", 30),
        ("3 Months", 90),
        ("1 Year", 365)
    ]

    for tab_name, max_days in timeframes:
        tracks = get_tracks_for_timeframe(all_tracks, max_days)
        rows = prepare_rows(tracks)
        update_sheet_tab(sheet, tab_name, rows)

if __name__ == "__main__":
    main()
