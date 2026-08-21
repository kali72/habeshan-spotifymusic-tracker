import json
import os
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ---------------------------------------------------------------------------
# Dynamic discovery configuration
# ---------------------------------------------------------------------------

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

SEED_ARTISTS = {
    "golden_era": ["Tilahun Gessesse", "Mahmoud Ahmed", "Alemayehu Eshete", "Mulatu Astatke"],
    "90s_2000s": ["Aster Aweke", "Neway Debebe", "Gigi", "Teddy Afro"],
    "modern": ["Rophnan", "Kassmasse", "Veronica Adane", "Jano Band"],
}

RELATED_ARTIST_DEPTH = 1
MAX_ARTIST_POOL_SIZE = 150
ARCHIVE_HEADERS = ["Date", "Track ID", "Artist", "Track Name", "Popularity"]


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
# Spotify Discovery Strategies
# ---------------------------------------------------------------------------

def discover_by_search_queries(sp, unique_tracks):
    for query in DISCOVERY_QUERIES:
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
            while offset < 200:
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


def fetch_spotify_tracks():
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Spotify credentials missing. Cannot discover tracks.")
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
# Historical Archive & Delta Tracking
# ---------------------------------------------------------------------------

def ensure_archive_tab(sheet):
    """Ensures the Archive tab exists and has the required schema."""
    try:
        ws = sheet.worksheet("Archive")
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title="Archive", rows="2000", cols="10")
        ws.append_row(ARCHIVE_HEADERS)
        print("Created new 'Archive' tab with headers.")
    return ws


def append_daily_snapshot(archive_ws, tracks):
    """Appends today's raw track popularity scores into the Archive tab."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    rows_to_append = []

    for t in tracks:
        artist_names = ", ".join([a["name"] for a in t.get("artists", [])])
        rows_to_append.append([
            today_str,
            t.get("id", ""),
            artist_names,
            t.get("name", ""),
            t.get("popularity", 0)
        ])

    if rows_to_append:
        archive_ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        print(f"Appended {len(rows_to_append)} daily snapshot rows to Archive.")


def calculate_timeframe_growth(archive_ws, current_tracks, days_back):
    """Computes popularity score growth between today and N days ago."""
    all_records = archive_ws.get_all_records()
    today = datetime.now().date()
    target_date = today - timedelta(days=days_back)

    # Find past popularity scores closest to the target_date
    past_scores = {}
    best_deltas = {}

    for row in all_records:
        try:
            row_date_str = str(row.get("Date", ""))
            row_date = datetime.strptime(row_date_str, "%Y-%m-%d").date()
            track_id = str(row.get("Track ID", ""))
            pop = int(row.get("Popularity", 0))

            days_diff = abs((row_date - target_date).days)
            max_allowed_diff = max(2, min(14, days_back // 2))

            if days_diff <= max_allowed_diff:
                if track_id not in past_scores or days_diff < best_deltas[track_id]:
                    past_scores[track_id] = pop
                    best_deltas[track_id] = days_diff
        except (ValueError, TypeError, KeyError):
            continue

    ranked_tracks = []
    for t in current_tracks:
        tid = t.get("id")
        curr_pop = t.get("popularity", 0)

        if tid in past_scores:
            growth = curr_pop - past_scores[tid]
        else:
            # Cold-start baseline if insufficient history exists
            growth = 0

        t_copy = dict(t)
        t_copy["growth"] = growth
        ranked_tracks.append(t_copy)

    # Sort primarily by score growth, secondarily by current overall popularity
    ranked_tracks.sort(key=lambda x: (x["growth"], x.get("popularity", 0)), reverse=True)
    return ranked_tracks


def get_track_image_url(track):
    """Extracts the smallest album cover image URL (approx 64x64 or 300x300)."""
    images = track.get("album", {}).get("images", [])
    if not images:
        return ""
    # images[-1] is usually smallest (64x64), perfect for table thumbnails
    return images[-1].get("url", "")

def prepare_leaderboard_rows(tracks, limit=100):
    """Formats ranked tracks into Google Sheets row arrays including Cover Image URL."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    rows = [["Rank", "Cover", "Artist", "Track Name", "Track ID", "Popularity", "Score Growth", "Date"]]

    for rank, track in enumerate(tracks[:limit], start=1):
        artist_names = ", ".join([a["name"] for a in track.get("artists", [])])
        growth = track.get("growth", 0)
        growth_str = f"+{growth}" if growth > 0 else str(growth)
        image_url = get_track_image_url(track)

        rows.append([
            rank,
            image_url,
            artist_names,
            track.get("name", ""),
            track.get("id", ""),
            track.get("popularity", 0),
            growth_str,
            today_str,
        ])
    return rows
    
def fetch_full_tracks_with_popularity(sp, raw_tracks):
    """Enriches a list of tracks with complete metadata (including popularity)."""
    track_ids = [t["id"] for t in raw_tracks if t.get("id")]
    full_tracks = []

    # Spotify allows fetching up to 50 tracks per API request
    for i in range(0, len(track_ids), 50):
        chunk = track_ids[i:i + 50]
        response = sp.tracks(chunk)
        full_tracks.extend(response["tracks"])

    return full_tracks
    
def update_sheet_tab(sheet, tab_name, rows):
    try:
        try:
            worksheet = sheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=tab_name, rows="150", cols="10")

        worksheet.clear()
        worksheet.update(values=rows, range_name="A1")
        print(f"Updated '{tab_name}' tab with {len(rows)-1} tracks.")
    except Exception as e:
        print(f"Error updating '{tab_name}': {e}")


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def main():
    tracks = fetch_spotify_tracks()

    # Safety safeguard: Abort before clearing sheets if discovery fails
    if not tracks:
        print("Spotify returned 0 tracks. Aborting script to protect Google Sheet data.")
        return

    gc = get_gspread_client()
    sheet_id = os.environ.get(
        "SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
    )
    sheet = gc.open_by_key(sheet_id)

    # 1. Fetch raw tracks (from playlist, search, or audio features)
    raw_tracks = get_spotify_tracks(...) 

    # 2. Upgrade raw tracks to full track objects (populates popularity 0-100)
    tracks = fetch_full_tracks_with_popularity(sp, raw_tracks)

    # 3. Format and update Google Sheets
    rows = prepare_leaderboard_rows(tracks)
    update_google_sheet(rows)

    # 1. Store snapshot in Archive tab
    archive_ws = ensure_archive_tab(sheet)
    append_daily_snapshot(archive_ws, tracks)

    # 2. Timeframes: (Tab Name, Days Back for Delta, Output Item Limit)
    timeframes = [
        ("1 Week", 7, 10),
        ("1 Month", 30, 100),
        ("3 Months", 90, 100),
        ("1 Year", 365, 100),
    ]

    # 3. Calculate consumption growth across timeframes & publish leaderboards
    for tab_name, days_back, limit in timeframes:
        ranked_tracks = calculate_timeframe_growth(archive_ws, tracks, days_back=days_back)
        rows = prepare_leaderboard_rows(ranked_tracks, limit=limit)
        update_sheet_tab(sheet, tab_name, rows)


if __name__ == "__main__":
    main()
