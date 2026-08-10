import json
import os
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Key Habesha artists to query directly
HABESHA_ARTISTS = [
    "Teddy Afro",
    "Rophnan",
    "Aster Aweke",
    "Kassmasse",
    "Veronica Adane",
    "Mulatu Astatke",
    "Mahmoud Ahmed",
    "Gigi",
    "Hailu Mergia",
    "Ephrem Amare",
    "Lij Michael",
    "Neway Debebe",
    "Gossaye Tesfaye",
    "Betty G",
]


def get_spotify_client():
  client_id = os.environ.get("SPOTIPY_CLIENT_ID")
  client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
  if not client_id or not client_secret:
    raise ValueError(
        "Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET environment"
        " variables."
    )
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

  # 1. Search top tracks by artist name directly
  for artist in HABESHA_ARTISTS:
    try:
      results = sp.search(q=f'artist:"{artist}"', type="track", limit=20)
      for track in results.get("tracks", {}).get("items", []):
        if track and track.get("id") and track["id"] not in unique_tracks:
          unique_tracks[track["id"]] = track
    except Exception as e:
      print(f"Error searching artist '{artist}': {e}")

  # 2. Search general Ethiopian music genres
  for q in ["ethiopian", "habesha", "amharic pop", "ethio jazz"]:
    try:
      results = sp.search(q=q, type="track", limit=50)
      for track in results.get("tracks", {}).get("items", []):
        if track and track.get("id") and track["id"] not in unique_tracks:
          unique_tracks[track["id"]] = track
    except Exception as e:
      print(f"Error searching query '{q}': {e}")

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

  # Backfill to 100 tracks using overall popularity
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
  if len(rows) <= 1:
    print(f"Skipping update for '{tab_name}' — no rows to write.")
    return

  try:
    try:
      worksheet = sheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
      worksheet = sheet.add_worksheet(title=tab_name, rows="150", cols="10")

    worksheet.clear()
    worksheet.update(values=rows, range_name="A1")
    print(f"Successfully updated '{tab_name}' with {len(rows)-1} tracks.")
  except Exception as e:
    print(f"Error updating tab '{tab_name}': {e}")


def main():
  gc = get_gspread_client()
  sheet_id = os.environ.get(
      "SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
  )
  sheet = gc.open_by_key(sheet_id)

  sp = get_spotify_client()
  raw_tracks = fetch_authentic_tracks(sp)

  if not raw_tracks:
    raise RuntimeError(
        "Spotify API returned 0 tracks. Check SPOTIPY_CLIENT_ID and"
        " SPOTIPY_CLIENT_SECRET secrets in GitHub."
    )

  print(f"Fetched {len(raw_tracks)} tracks from Spotify.")

  timeframes = [("1 Month", 30), ("3 Months", 90), ("1 Year", 365)]

  for tab_name, max_days in timeframes:
    tracks = filter_by_days(raw_tracks, max_days)
    rows = prepare_rows(tracks)
    update_sheet_tab(sheet, tab_name, rows)


if __name__ == "__main__":
  main()
