import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ---------------------------------------------------------------------------
# Dynamic discovery configuration
# (replaces the old static HABESHA_ARTISTS array)
# ---------------------------------------------------------------------------

# Keyword / genre search queries spanning every era. These are search leads,
# not a whitelist -- the track pool is built from whatever they surface.
DISCOVERY_QUERIES = [
    # Golden Era / Classics (1960s-1980s)
    'genre:"ethio-jazz"',
    "ethiopian oldies",
    "ethiopian classics",
    "amharic oldies",
    "tilahun gessesse",
    "mahmoud ahmed",
    "alemayehu eshete",
    "mulatu astatke",
    "ethiopiques",
    # 1990s & 2000s
    "ethiopian pop",
    "amharic music",
    "habesha music",
    "aster aweke",
    "neway debebe",
    "gigi ethiopian singer",
    # Modern Era & Contemporary (2010s-present)
    "ethiopian hip hop",
    "habesha hits",
    "tigrigna music",
    "oromo music",
    "eritrean music",
    "amharic hip hop",
    "rophnan",
    "kassmasse",
    "veronica adane",
    "ethiopian afrobeat",
]

# Curated playlist searches (Ethio-Jazz, Ethiopian Gold, Modern Habesha Hits,
# Eritrean Classics, etc.) -- tracks are pulled from whatever public/official
# playlists these terms surface.
PLAYLIST_SEARCH_TERMS = [
    "Ethio Jazz",
    "Ethiopian Gold",
    "Habesha Hits",
    "Eritrean Classics",
    "Amharic Hits",
    "Tigrigna Music",
    "Oromo Music",
    "Ethiopian Music",
]

# A handful of well-known artists per era, used ONLY to bootstrap
# sp.artist_related_artists() expansion (and as a term list for the iTunes
# fallback below). This is not a filter -- the pool grows organically from
# here via the related-artist graph.
SEED_ARTISTS = {
    "golden_era": ["Tilahun Gessesse", "Mahmoud Ahmed", "Alemayehu Eshete", "Mulatu Astatke"],
    "90s_2000s": ["Aster Aweke", "Neway Debebe", "Gigi", "Teddy Afro"],
    "modern": ["Rophnan", "Kassmasse", "Veronica Adane", "Jano Band"],
}

RELATED_ARTIST_DEPTH = 1     # hops outward from seed artists
MAX_ARTIST_POOL_SIZE = 150   # safety cap so related-artist expansion can't explode


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


# ---------------------------------------------------------------------------
# Discovery strategy 1: keyword / genre search queries
# ---------------------------------------------------------------------------

def discover_by_search_queries(sp, unique_tracks):
  for query in DISCOVERY_QUERIES:
    # limit=10 per request, paginated via offset -- keeps every call within
    # Spotify's search API limits and avoids HTTP 400s.
    for offset in range(0, 30, 10):
      try:
        results = sp.search(q=query, type="track", limit=10, offset=offset)
        items = results.get("tracks", {}).get("items", [])
        if not items:
          break
        for track in items:
          if track and track.get("id") and track["id"] not in unique_tracks:
            unique_tracks[track["id"]] = track
      except Exception as e:
        print(f"Spotify search warning for query '{query}' at offset {offset}: {e}")
        break


# ---------------------------------------------------------------------------
# Discovery strategy 2: curated playlists (era-specific)
# ---------------------------------------------------------------------------

def discover_by_playlists(sp, unique_tracks):
  seen_playlists = set()
  for term in PLAYLIST_SEARCH_TERMS:
    try:
      results = sp.search(q=term, type="playlist", limit=10)
      playlists = (results.get("playlists", {}) or {}).get("items", []) or []
    except Exception as e:
      print(f"Playlist search warning for '{term}': {e}")
      continue

    for playlist in playlists:
      if not playlist:
        continue
      pid = playlist.get("id")
      if not pid or pid in seen_playlists:
        continue
      seen_playlists.add(pid)

      offset = 0
      while offset < 200:  # cap per playlist so one huge playlist can't dominate a run
        try:
          resp = sp.playlist_items(
              pid,
              limit=100,
              offset=offset,
              fields="items.track(id,name,type,artists,album,popularity)",
          )
          items = resp.get("items", [])
          if not items:
            break
          for item in items:
            track = item.get("track") if item else None
            if track and track.get("type") == "track" and track.get("id"):
              if track["id"] not in unique_tracks:
                unique_tracks[track["id"]] = track
          if len(items) < 100:
            break
          offset += 100
        except Exception as e:
          print(f"Playlist track fetch warning for '{pid}' at offset {offset}: {e}")
          break


# ---------------------------------------------------------------------------
# Discovery strategy 3: related-artist graph expansion
# ---------------------------------------------------------------------------

def resolve_artist_id(sp, name):
  try:
    results = sp.search(q=f'artist:"{name}"', type="artist", limit=1)
    items = results.get("artists", {}).get("items", [])
    return items[0]["id"] if items else None
  except Exception as e:
    print(f"Artist lookup warning for '{name}': {e}")
    return None


def expand_related_artists(sp, seed_ids, depth=RELATED_ARTIST_DEPTH, max_pool=MAX_ARTIST_POOL_SIZE):
  pool = set(seed_ids)
  frontier = set(seed_ids)

  for _ in range(depth):
    if len(pool) >= max_pool:
      break
    next_frontier = set()
    for artist_id in frontier:
      if len(pool) >= max_pool:
        break
      try:
        related = sp.artist_related_artists(artist_id)
        for artist in related.get("artists", []):
          aid = artist.get("id")
          if aid and aid not in pool:
            pool.add(aid)
            next_frontier.add(aid)
            if len(pool) >= max_pool:
              break
      except Exception as e:
        print(f"Related-artist lookup warning for '{artist_id}': {e}")
        continue
    frontier = next_frontier

  return pool


def discover_by_related_artists(sp, unique_tracks):
  seed_ids = set()
  for era, names in SEED_ARTISTS.items():
    for name in names:
      artist_id = resolve_artist_id(sp, name)
      if artist_id:
        seed_ids.add(artist_id)

  artist_pool = expand_related_artists(sp, seed_ids)

  for artist_id in artist_pool:
    try:
      top = sp.artist_top_tracks(artist_id, country="US")
      for track in top.get("tracks", []):
        if track and track.get("id") and track["id"] not in unique_tracks:
          unique_tracks[track["id"]] = track
    except Exception as e:
      print(f"Top-tracks warning for artist '{artist_id}': {e}")
      continue


# ---------------------------------------------------------------------------
# Spotify fetch orchestration
# ---------------------------------------------------------------------------

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

    print("Discovering tracks via keyword/genre search...")
    discover_by_search_queries(sp, unique_tracks)

    print("Discovering tracks via curated playlists...")
    discover_by_playlists(sp, unique_tracks)

    print("Discovering tracks via related-artist graph...")
    discover_by_related_artists(sp, unique_tracks)

    print(f"Discovered {len(unique_tracks)} unique candidate tracks.")
    return list(unique_tracks.values())
  except Exception as e:
    print(f"Spotify authentication error: {e}")
    return []


# ---------------------------------------------------------------------------
# Fallback (iTunes) -- now driven by the dynamic seed/keyword lists instead
# of the removed HABESHA_ARTISTS array
# ---------------------------------------------------------------------------

FALLBACK_SEARCH_TERMS = sorted(
    {name for names in SEED_ARTISTS.values() for name in names}
) + ["Ethiopian Music", "Habesha Music", "Eritrean Music", "Ethio Jazz"]


def fetch_fallback_tracks():
  unique_tracks = {}
  for term in FALLBACK_SEARCH_TERMS:
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(term)}&entity=song&limit=10"
    try:
      req = urllib.request.Request(
          url, headers={"User-Agent": "Mozilla/5.0"}
      )
      with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        for item in data.get("results", []):
          t_id = str(item.get("trackId"))
          artist_name = item.get("artistName", "")
          if t_id and t_id not in unique_tracks and artist_name:
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
      print(f"Fallback search warning for '{term}': {e}")

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
