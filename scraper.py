import json
import os
import urllib.request
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


def get_gspread_client():
  creds_json = os.environ.get("GCP_SA_KEY")
  if not creds_json:
    raise ValueError("Missing GCP_SA_KEY environment variable.")
  info = json.loads(creds_json)
  scopes = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  credentials = Credentials.from_service_account_info(info, scopes=scopes)
  return gspread.authorize(credentials)


def fetch_spotify_tracks():
  client_id = os.environ.get("SPOTIPY_CLIENT_ID")
  client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
  if not client_id or not client_secret:
    print("Spotify credentials missing. Switching to public fallback...")
    return []

  try:
    auth_mgr = SpotifyClientCredentials(
        client_id=client_id, client_secret=client_secret
    )
    sp = spotipy.Spotify(auth_manager=auth_mgr)
    tracks = []
    seen = set()
    for q in ["Ethiopian", "Amharic", "Habesha"]:
      res = sp.search(q=q, type="track", limit=50)
      for item in res.get("tracks", {}).get("items", []):
        if item.get("id") and item["id"] not in seen:
          seen.add(item["id"])
          artists = ", ".join([a["name"] for a in item.get("artists", [])])
          tracks.append({
              "id": item["id"],
              "artist": artists,
              "title": item.get("name", ""),
          })
    return tracks
  except Exception as e:
    print(f"Spotify API error ({e}). Switching to public fallback...")
    return []


def fetch_fallback_tracks():
  """Fetches modern Ethiopian/Habesha tracks via public chart endpoints."""
  tracks = []
  queries = ["ethiopian", "amharic", "habesha"]
  seen = set()

  for q in queries:
    url = f"https://itunes.apple.com/search?term={q}&entity=song&limit=50"
    try:
      req = urllib.request.Request(
          url, headers={"User-Agent": "Mozilla/5.0"}
      )
      with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        for item in data.get("results", []):
          track_id = str(item.get("trackId"))
          if track_id and track_id not in seen:
            seen.add(track_id)
            tracks.append({
                "id": track_id,
                "artist": item.get("artistName", "Unknown"),
                "title": item.get("trackName", "Unknown"),
            })
    except Exception as e:
      print(f"Fallback query error for '{q}': {e}")

  return tracks


def prepare_rows(tracks):
  today_str = datetime.now().strftime("%Y-%m-%d")
  rows = [["Date", "Artist", "Rank", "Track ID", "Track Name"]]
  for rank, track in enumerate(tracks[:100], start=1):
    rows.append([today_str, track["artist"], rank, track["id"], track["title"]])
  return rows


def update_sheet_tab(sheet, tab_name, rows):
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

  tracks = fetch_spotify_tracks()
  if not tracks:
    print("Fetching tracks via public fallback...")
    tracks = fetch_fallback_tracks()

  if not tracks:
    raise RuntimeError("Failed to retrieve track data from all sources.")

  rows = prepare_rows(tracks)
  for tab_name in ["1 Month", "3 Months", "1 Year"]:
    update_sheet_tab(sheet, tab_name, rows)


if __name__ == "__main__":
  main()
