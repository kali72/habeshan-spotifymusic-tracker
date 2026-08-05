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
        raise ValueError("Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET")
    
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    return spotipy.Spotify(auth_manager=auth_manager)

def get_gspread_client():
    creds_json = os.environ.get("GCP_SA_KEY")
    if not creds_json:
        raise ValueError("Missing GCP_SA_KEY environment variable")
    
    info = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials)

def fetch_habesha_tracks(sp):
    queries = ["Ethiopian", "Habesha", "Ethio", "Amharic"]
    all_tracks = []
    seen_ids = set()

    # Search individual tracks
    for q in queries:
        try:
            results = sp.search(q=q, type="track", limit=50)
            items = results.get("tracks", {}).get("items", [])
            for item in items:
                track_id = item.get("id")
                if track_id and track_id not in seen_ids:
                    seen_ids.add(track_id)
                    all_tracks.append(item)
        except Exception as e:
            print(f"Error searching query '{q}': {e}")

    # Fetch from popular playlists
    for q in ["Ethiopian Hits", "Habesha Music", "Best Ethiopian Songs"]:
        try:
            playlists = sp.search(q=q, type="playlist", limit=3).get("playlists", {}).get("items", [])
            for pl in playlists:
                if not pl:
                    continue
                pl_items = sp.playlist_items(pl["id"], limit=50).get("items", [])
                for item in pl_items:
                    track = item.get("track")
                    if track and track.get("id") and track["id"] not in seen_ids:
                        seen_ids.add(track["id"])
                        all_tracks.append(track)
        except Exception as e:
            print(f"Error fetching playlist for '{q}': {e}")

    return all_tracks

def filter_by_timeframe(tracks, max_days):
    today = datetime.now().date()
    cutoff = today - timedelta(days=max_days)
    filtered = []

    for track in tracks:
        album = track.get("album", {})
        release_date_str = album.get("release_date", "")
        if not release_date_str:
            continue

        try:
            parts = release_date_str.split("-")
            if len(parts) == 1:
                rel_date = datetime.strptime(release_date_str, "%Y").date()
            elif len(parts) == 2:
                rel_date = datetime.strptime(release_date_str, "%Y-%m").date()
            else:
                rel_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()

            if rel_date >= cutoff:
                filtered.append((rel_date, track))
        except ValueError:
            continue

    filtered.sort(key=lambda x: x[0], reverse=True)
    return filtered

def prepare_rows(filtered_tracks):
    rows = [["Date", "Artist", "Rank", "Track ID", "Track Name"]]
    for rank, (rel_date, track) in enumerate(filtered_tracks, start=1):
        artists = ", ".join([artist["name"] for artist in track.get("artists", [])])
        rows.append([
            rel_date.strftime("%Y-%m-%d"),
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
            worksheet = sheet.add_worksheet(title=tab_name, rows="100", cols="10")

        worksheet.clear()
        # Explicit keyword arguments prevent gspread v6 signature errors
        worksheet.update(values=rows, range_name="A1")
        print(f"Successfully updated '{tab_name}' with {len(rows)-1} tracks.")
    except Exception as e:
        print(f"Error updating tab '{tab_name}': {e}")

def main():
    sp = get_spotify_client()
    gc = get_gspread_client()

    sheet_id = os.environ.get("SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU")
    sheet = gc.open_by_key(sheet_id)

    all_tracks = fetch_habesha_tracks(sp)
    print(f"Fetched {len(all_tracks)} unique tracks from Spotify.")

    timeframes = [
        ("1 Month", 30),
        ("3 Months", 90),
        ("1 Year", 365)
    ]

    for tab_name, max_days in timeframes:
        filtered = filter_by_timeframe(all_tracks, max_days)
        rows = prepare_rows(filtered)
        update_sheet_tab(sheet, tab_name, rows)

if __name__ == "__main__":
    main()
