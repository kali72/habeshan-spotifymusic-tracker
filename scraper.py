import json
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Modern Ethiopian & Habesha Search Queries
MODERN_QUERIES = [
    "ethio pop",
    "amharic pop",
    "habesha",
    "ethiopian hits",
    "ethiopian hip hop",
    "year:2025-2026",
]


def parse_release_date(date_str):
  """Converts Spotify release date formats into a datetime object."""
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


def fetch_all_modern_tracks(sp):
  """Collects modern Ethiopian tracks with release dates and popularity scores."""
  unique_tracks = {}

  for query in MODERN_QUERIES:
    try:
      results = sp.search(q=query, type="track", limit=50)
      for track in results.get("tracks", {}).get("items", []):
        t_id = track["id"]
        if t_id not in unique_tracks:
          rel_date = parse_release_date(track["album"]["release_date"])
          if rel_date:
            artist_names = ", ".join([a["name"] for a in track["artists"]])
            unique_tracks[t_id] = {
                "id": t_id,
                "artist": artist_names,
                "title": track["name"],
                "popularity": track.get("popularity", 0),
                "release_date": rel_date,
            }
    except Exception as e:
      print(f"Error searching query '{query}': {e}")

  return list(unique_tracks.values())


def filter_tracks_by_days(tracks, max_days):
  """Filters tracks by max release age in days and sorts by Spotify popularity."""
  now = datetime.now()
  filtered = []
  for t in tracks:
    days_old = (now - t["release_date"]).days
    if 0 <= days_old <= max_days:
      filtered.append(t)

  # Sort by popularity descending
  filtered.sort(key=lambda x: x["popularity"], reverse=True)
  return filtered


def update_sheet_tab(spreadsheet, tab_name, tracks, date_str):
  try:
    worksheet = spreadsheet.worksheet(tab_name)
  except gspread.exceptions.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title=tab_name, rows="150", cols="5")

  worksheet.clear()
  headers = ["Date", "Artist", "Rank", "Track ID", "Track Name"]
  rows = [headers]

  for idx, track in enumerate(tracks[:100], start=1):
    rows.append(
        [date_str, track["artist"], idx, track["id"], track["title"]]
    )

  worksheet.update("A1", rows)
  print(f"Updated '{tab_name}' with {len(rows[:100])} modern tracks.")


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
      "https://www.googleapis.com/auth/drive",
  ]
  creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
  client = gspread.authorize(creds)

  SHEET_ID = "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
  spreadsheet = client.open_by_key(SHEET_ID)
  today = datetime.now().strftime("%Y-%m-%d")

  # Fetch modern releases
  all_tracks = fetch_all_modern_tracks(sp)

  # Filter distinct sets by timeframe
  tracks_1_month = filter_tracks_by_days(all_tracks, max_days=30)
  tracks_3_months = filter_tracks_by_days(all_tracks, max_days=90)
  tracks_1_year = filter_tracks_by_days(all_tracks, max_days=365)

  # Write distinct outputs to Google Sheets
  update_sheet_tab(spreadsheet, "1 Month", tracks_1_month, today)
  update_sheet_tab(spreadsheet, "3 Months", tracks_3_months, today)
  update_sheet_tab(spreadsheet, "1 Year", tracks_1_year, today)


if __name__ == "__main__":
  main()
