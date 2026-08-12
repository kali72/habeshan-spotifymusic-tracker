import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Curated list of verified Habesha / Ethiopian artists
HABESHA_ARTISTS = [
    "Teddy Afro",
    "Rophnan",
    "Aster Aweke",
    "Kassmasse",
    "Veronica Adane",
    "Gigi",
    "Mahmoud Ahmed",
    "Mulatu Astatke",
    "Ephrem Amare",
    "Lij Michael",
    "Yared Negu",
    "Betty G",
    "Gossaye Tesfaye",
    "Neway Debebe",
    "Alemayehu Eshete",
    "Hailu Mergia",
    "Tilahun Gessesse",
    "Kiros Alemayehu",
    "Bizunesh Bekele",
    "Teddy Yo",
    "Sami Dan",
    "Sancho Gebre",
    "Abinet Agonafer",
    "Dawit Nega",
    "Assegid Abate",
    "Jah Lude",
    "Getish Mamo",
    "Dawit Tsige",
]


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


def fetch_spotify_tracks():
  client_id = os.environ.get("SPOTIPY_CLIENT_ID")
  client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
  if not client_id or not client_secret:
    print("Spotify credentials missing. Using fallback API...")
    return []

  try:
    auth_mgr = SpotifyClientCredentials(
        client_id=client_id, client_secret=client_secret
    )
    sp = spotipy.Spotify(auth_manager=auth_mgr)
    unique_tracks = {}

    for artist in HABESHA_ARTISTS:
      query = f'artist:"{artist}"'
      for offset in range(0, 30, 10):
        try:
          results = sp.search(q=query, type="track", limit=10, offset=offset)
          items = results.get("tracks", {}).get("items", [])
          if not items:
            break
          for track in items:
            if track and track.get("id") and track["id"] not in unique_tracks:
              # Ensure target artist is explicitly on the track
              track_artists = [
                  a["name"].lower() for a in track.get("artists", [])
              ]
              if any(artist.lower() in ta for ta in track_artists):
                unique_tracks[track["id"]] = track
        except Exception as e:
          print(
              f"Spotify search warning for '{artist}' at offset {offset}: {e}"
          )
          break

    return list(unique_tracks.values())
  except Exception as e:
    print(f"Spotify authentication error: {e}")
    return []


def fetch_fallback_tracks():
  unique_tracks = {}
  for artist in HABESHA_ARTISTS:
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(artist)}&entity=song&limit=10"
    try:
      req = urllib.request.Request(
          url, headers={"User-Agent": "Mozilla/5.0"}
      )
      with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        for item in data.get("results", []):
          t_id = str(item.get("trackId"))
          artist_name = item.get("artistName", "")
          if t_id and t_id not in unique_tracks:
            if artist.lower() in artist_name.lower():
              unique_tracks[t_id] = {
                  "id": t_id,
                  "name": item.get("trackName", ""),
                  "artists": [{"name": artist_name}],
                  "album": {
                      "release_date": item.get("releaseDate", "2020-01-01")[:10]
                  },
                  "popularity": 50,
              }
    except Exception as e:
      print(f"Fallback search warning for '{artist}': {e}")

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


def filter_by_days(tracks, max_days, limit=100):
  today = datetime.now().date()
  cutoff = today - timedelta(days=max_days)

  filtered = [t for t in tracks if parse_release_date(t) >= cutoff]
  filtered.sort(key=lambda x: x.get("popularity", 0), reverse=True)

  # Backfill up to `limit` tracks using overall popularity if timeframe yields fewer
  if len(filtered) < limit:
    seen_ids = {t["id"] for t in filtered}
    all_sorted = sorted(
        tracks, key=lambda x: x.get("popularity", 0), reverse=True
    )
    for t in all_sorted:
      if t["id"] not in seen_ids:
        filtered.append(t)
        seen_ids.add(t["id"])
      if len(filtered) >= limit:
        break

  return filtered[:limit]


def prepare_rows(tracks):
  today_str = datetime.now().strftime("%Y-%m-%d")
  rows = [["Date", "Artist", "Rank", "Track ID", "Track Name"]]

  for rank, track in enumerate(tracks, start=1):
    artist_names = ", ".join([a["name"] for a in track.get("artists", [])])
    rows.append([
        today_str,
        artist_names,
        rank,
        track.get("id", ""),
        track.get("name", ""),
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
  gc = get_gspread_client()
  sheet_id = os.environ.get(
      "SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
  )
  sheet = gc.open_by_key(sheet_id)

  tracks = fetch_spotify_tracks()
  if not tracks:
    print("Spotify returned 0 tracks. Running fallback fetcher...")
    tracks = fetch_fallback_tracks()

  # List of tabs to generate: (Tab Name, Days Cutoff, Item Limit)
  timeframes = [
      ("1 Week", 7, 10),
      ("1 Month", 30, 100),
      ("3 Months", 90, 100),
      ("1 Year", 365, 100),
  ]

  for tab_name, max_days, limit in timeframes:
    filtered = filter_by_days(tracks, max_days, limit=limit)
    rows = prepare_rows(filtered)
    update_sheet_tab(sheet, tab_name, rows)


if __name__ == "__main__":
  main()
