import json
import os
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Curated Spotify Playlists for Authentic Habesha Music
HABESHA_PLAYLISTS = [
    "37i9dQZF1DXcadB69DKC8c",  # Ethiopian Hits
    "37i9dQZF1DXbX3zrk7F77a",  # Ethio Pop & Afro-Habesha
    "37i9dQZF1DX83P1650C1k8",  # Ethio Jazz Classics
]

# Top Habesha Artist IDs for complete coverage
TOP_HABESHA_ARTISTS = [
    "08oMhAUN23C91R1zltrR6p",  # Teddy Afro
    "3S9v12W801",  # Rophnan
    "4a0K2Y2001",  # Kassmasse
    "6oCxgUP6Vdx3YIJb59Ia0L",  # Aster Aweke
    "2j7Iv2k201",  # Mahmoud Ahmed
]


def get_spotify_client():
  client_id = os.environ.get("SPOTIPY_CLIENT_ID")
  client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
  if not client_id or not client_secret:
    raise ValueError("SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET is missing.")
  return spotipy.Spotify(
      auth_manager=SpotifyClientCredentials(
          client_id=client_id, client_secret=client_secret
      )
  )


def get_gspread_client():
  creds_json = os.environ.get("GCP_SA_KEY")
  if not creds_json:
    raise ValueError("Missing GCP_SA_KEY environment variable.")
  info = json.loads(creds_json)
  scopes = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  return gspread.authorize(
      Credentials.from_service_account_info(info, scopes=scopes)
  )


def fetch_authentic_tracks(sp):
  unique_tracks = {}

  # 1. Fetch tracks directly from Spotify Curated Playlists
  for pl_id in HABESHA_PLAYLISTS:
    try:
      results = sp.playlist_items(pl_id, limit=100)
      for item in results.get("items", []):
        track = item.get("track")
        if track and track.get("id") and track["id"] not in unique_tracks:
          unique_tracks[track["id"]] = track
    except Exception as e:
      print(f"Playlist {pl_id} fetch error: {e}")

  # 2. Fetch top tracks from key artists
  for artist_id in TOP_HABESHA_ARTISTS:
    try:
      top_tracks = sp.artist_top_tracks(artist_id).get("tracks", [])
      for track in top_tracks:
        if track and track.get("id") and track["id"] not in unique_tracks:
          unique_tracks[track["id"]] = track
    except Exception as e:
      print(f"Artist {artist_id} fetch error: {e}")

  return list(unique_tracks.values())


def parse_release_date(track):
  date_str = track.get("album", {}).get("release_date", "")
  if not date_str:
    return datetime(2020, 1, 1).date()
  try:
    parts = date_str.split("-")
    if len(parts) == 1:
      return datetime.strptime(date_str, "%Y").date()
    elif len(parts) == 2:
      return datetime.strptime(date_str, "%Y-%m").date()
    else:
      return datetime.strptime(date_str, "%Y-%m-%d").date()
  except ValueError:
    return datetime(2020, 1, 1).date()


def filter_by_days(tracks, max_days):
  today = datetime.now().date()
  cutoff = today - timedelta(days=max_days)

  filtered = [t for t in tracks if parse_release_date(t) >= cutoff]
  filtered.sort(key=lambda x: x.get("popularity", 0), reverse=True)

  # Backfill if timeframe has fewer than 100 tracks
  if len(filtered) < 100:
    seen_ids = {t["id"] for t in filtered}
    all_sorted = sorted(
        tracks, key=lambda x: x.get("popularity", 0), reverse=True
    )
    for t in all_sorted:
      if t["id"] not in seen_ids:
        filtered.append(t)
        seen_ids.add(t["id"])
      if len(filtered) >= 100:
        break

  return filtered[:100]


def prepare_rows(tracks):
  today_str = datetime.now().strftime("%Y-%m-%d")
  rows = [["Date", "Artist", "Rank", "Track ID", "Track Name"]]

  for rank, track in enumerate(tracks, start=1):
    artist_names = ", ".join([a["name"] for a in track.get("artists", [])])
    rows.append(
        [today_str, artist_names, rank, track.get("id", ""), track.get("name", "")]
    )
  return rows


def update_sheet_tab(sheet, tab_name, rows):
  try:
    try:
      worksheet = sheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
      worksheet = sheet.add_worksheet(title=tab_name, rows="150", cols="10")

    worksheet.clear()
    worksheet.update(values=rows, range_name="A1")
    print(f"Updated '{tab_name}' with {len(rows)-1} authentic tracks.")
  except Exception as e:
    print(f"Error updating '{tab_name}': {e}")


def main():
  sp = get_spotify_client()
  gc = get_gspread_client()

  sheet_id = os.environ.get(
      "SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
  )
  sheet = gc.open_by_key(sheet_id)

  all_tracks = fetch_authentic_tracks(sp)
  print(f"Fetched {len(all_tracks)} authentic Habesha tracks from Spotify.")

  timeframes = [("1 Month", 30), ("3 Months", 90), ("1 Year", 365)]

  for tab_name, max_days in timeframes:
    tracks = filter_by_days(all_tracks, max_days)
    rows = prepare_rows(tracks)
    update_sheet_tab(sheet, tab_name, rows)


if __name__ == "__main__":
  main()
