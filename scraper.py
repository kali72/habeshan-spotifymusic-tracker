import json
import os
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ---------------------------------------------------------------------------
# Discovery Configuration
# ---------------------------------------------------------------------------

DISCOVERY_QUERIES = [
    'genre:"ethio-jazz"',
    "ethiopian oldies",
    "ethiopian classics",
    "amharic oldies",
    "tilahun gessesse",
    "mahmoud ahmed",
    "alemayehu eshete",
    "mulatu astatke",
    "ethiopiques",
    "ethiopian pop",
    "amharic music",
    "habesha music",
    "aster aweke",
    "neway debebe",
    "gigi ethiopian singer",
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
    return gspread.authorize(Credentials.from_service_account_info(info, scopes=scopes))


# ---------------------------------------------------------------------------
# Spotify Discovery
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
                print(f"Spotify search warning for '{query}': {e}")
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
                    print(f"Playlist track warning for '{pid}': {e}")
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
                print(f"Related artist error for '{artist_id}': {e}")
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
            print(f"Top-tracks warning for '{artist_id}': {e}")
            continue


def fetch_spotify_tracks():
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Spotify credentials missing.")
        return [], None

    try:
        auth_mgr = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(auth_manager=auth_mgr)
        unique_tracks = {}

        print("Discovering tracks...")
        discover_by_search_queries(sp, unique_tracks)
        discover_by_playlists(sp, unique_tracks)
        discover_by_related_artists(sp, unique_tracks)

        print(f"Discovered {len(unique_tracks)} unique tracks.")
        return list(unique_tracks.values()), sp
    except Exception as e:
        print(f"Spotify authentication error: {e}")
        return [], None


# ---------------------------------------------------------------------------
# Data Aggregations & Helpers
# ---------------------------------------------------------------------------

def ensure_archive_tab(sheet):
    try:
        ws = sheet.worksheet("Archive")
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title="Archive", rows="2000", cols="10")
        ws.append_row(ARCHIVE_HEADERS)
    return ws


def append_daily_snapshot(archive_ws, tracks):
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


def get_track_image_url(track):
    images = track.get("album", {}).get("images", [])
    return images[0].get("url", "") if images else ""


def parse_release_date(date_str):
    if not date_str:
        return datetime(2000, 1, 1)
    try:
        if len(date_str) == 4:
            return datetime.strptime(date_str, "%Y")
        elif len(date_str) == 7:
            return datetime.strptime(date_str, "%Y-%m")
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return datetime(2000, 1, 1)


def prepare_artist_leaderboard_rows(sp, tracks, limit=15):
    """Fetches real artist profile pictures and generates short bios."""
    artist_counts = {}
    artist_objs = {}

    for track in tracks:
        pop = track.get("popularity", 0)
        for artist in track.get("artists", []):
            aid = artist.get("id")
            name = artist.get("name")
            if not aid or not name:
                continue
            if aid not in artist_counts:
                artist_counts[aid] = {"name": name, "total_pop": 0, "count": 0}
                artist_objs[aid] = artist
            artist_counts[aid]["total_pop"] += pop
            artist_counts[aid]["count"] += 1

    sorted_artists = sorted(
        artist_counts.items(),
        key=lambda x: (x[1]["total_pop"], x[1]["count"]),
        reverse=True
    )[:limit]

    # Batch fetch Spotify artist profile data for real pictures and genres
    artist_ids = [aid for aid, _ in sorted_artists]
    spotify_artist_details = {}

    if sp and artist_ids:
        for i in range(0, len(artist_ids), 50):
            chunk = artist_ids[i:i + 50]
            try:
                resp = sp.artists(chunk)
                for a in resp.get("artists", []):
                    if a:
                        spotify_artist_details[a["id"]] = a
            except Exception as e:
                print(f"Error fetching artist batch: {e}")

    rows = [["Rank", "Cover", "Artist", "Bio"]]

    for rank, (aid, data) in enumerate(sorted_artists, start=1):
        sp_details = spotify_artist_details.get(aid, {})
        images = sp_details.get("images", [])
        profile_img = images[0]["url"] if images else ""

        genres = sp_details.get("genres", [])
        genre_str = ", ".join([g.title() for g in genres[:2]]) if genres else "Habesha Artist"
        followers = sp_details.get("followers", {}).get("total", 0)
        follower_str = f"{followers:,} Spotify followers" if followers else f"{data['count']} tracked songs"

        bio = f"{genre_str} • {follower_str}"
        rows.append([rank, profile_img, data["name"], bio])

    return rows


def prepare_all_time_track_rows(tracks, limit=100):
    sorted_tracks = sorted(tracks, key=lambda x: x.get("popularity", 0), reverse=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    rows = [["Rank", "Cover", "Artist", "Track Name", "Track ID", "Popularity", "Score Growth", "Date"]]

    for rank, track in enumerate(sorted_tracks[:limit], start=1):
        artist_names = ", ".join([a["name"] for a in track.get("artists", [])])
        rows.append([
            rank,
            get_track_image_url(track),
            artist_names,
            track.get("name", ""),
            track.get("id", ""),
            track.get("popularity", 0),
            "+0",
            today_str,
        ])
    return rows


def calculate_timeframe_growth(archive_ws, current_tracks, days_back):
    all_records = archive_ws.get_all_records()
    today = datetime.now().date()
    target_date = today - timedelta(days=days_back)

    past_scores = {}
    best_deltas = {}

    for row in all_records:
        try:
            row_date = datetime.strptime(str(row.get("Date", "")), "%Y-%m-%d").date()
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

    has_archive_data = len(past_scores) > 0

    ranked_tracks = []
    now = datetime.now()

    for t in current_tracks:
        tid = t.get("id")
        curr_pop = t.get("popularity", 0)
        t_copy = dict(t)

        if has_archive_data and tid in past_scores:
            # Historical Delta
            growth = curr_pop - past_scores[tid]
            t_copy["score"] = (growth, curr_pop)
            t_copy["growth_str"] = f"+{growth}" if growth > 0 else str(growth)
        else:
            # Cold-Start Criteria (Option B)
            rel_date = parse_release_date(t.get("album", {}).get("release_date"))
            days_old = (now - rel_date).days

            if days_back == 7:  # Weekly: Heavy emphasis on recent hits
                recency_weight = max(0, 100 - (days_old / 30))
                score = curr_pop * 1.5 + recency_weight
            elif days_back == 30:  # Monthly: Recent releases + medium popularity
                recency_weight = max(0, 50 - (days_old / 90))
                score = curr_pop + recency_weight
            elif days_back == 90:  # 3-Month: Mid-term trends & high stability
                recency_weight = max(0, 25 - (days_old / 180))
                score = curr_pop * 1.1 + recency_weight
            else:  # Yearly: Established classics & high overall streaming power
                catalog_weight = min(30, days_old / 365)
                score = curr_pop + catalog_weight

            t_copy["score"] = score
            t_copy["growth_str"] = "+0"

        ranked_tracks.append(t_copy)

    ranked_tracks.sort(key=lambda x: x["score"], reverse=True)
    return ranked_tracks


def prepare_leaderboard_rows(tracks, limit=100):
    today_str = datetime.now().strftime("%Y-%m-%d")
    rows = [["Rank", "Cover", "Artist", "Track Name", "Track ID", "Popularity", "Score Growth", "Date"]]

    for rank, track in enumerate(tracks[:limit], start=1):
        artist_names = ", ".join([a["name"] for a in track.get("artists", [])])
        growth_str = track.get("growth_str", "+0")

        rows.append([
            rank,
            get_track_image_url(track),
            artist_names,
            track.get("name", ""),
            track.get("id", ""),
            track.get("popularity", 0),
            growth_str,
            today_str,
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
        print(f"Updated '{tab_name}' tab with {len(rows)-1} items.")
    except Exception as e:
        print(f"Error updating '{tab_name}': {e}")


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def main():
    tracks, sp = fetch_spotify_tracks()
    if not tracks:
        print("Spotify returned 0 tracks. Aborting script to protect Google Sheet data.")
        return

    gc = get_gspread_client()
    sheet_id = os.environ.get(
        "SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
    )
    sheet = gc.open_by_key(sheet_id)

    archive_ws = ensure_archive_tab(sheet)
    append_daily_snapshot(archive_ws, tracks)

    # 1. Top 15 Artists Tab (Rank | Cover | Artist | Bio)
    artist_rows = prepare_artist_leaderboard_rows(sp, tracks, limit=15)
    update_sheet_tab(sheet, "Top 15 Artists", artist_rows)

    # 2. All-Time Tracks Tab
    all_time_rows = prepare_all_time_track_rows(tracks, limit=100)
    update_sheet_tab(sheet, "All-Time Tracks", all_time_rows)

    # 3. Timeframe Growth Leaderboards
    timeframes = [
        ("Weekly Top 10", 7, 10),
        ("Monthly Top 100", 30, 100),
        ("3-Month Top 100", 90, 100),
        ("Yearly Top 100", 365, 100),
    ]

    for tab_name, days_back, limit in timeframes:
        ranked_tracks = calculate_timeframe_growth(archive_ws, tracks, days_back=days_back)
        rows = prepare_leaderboard_rows(ranked_tracks, limit=limit)
        update_sheet_tab(sheet, tab_name, rows)


if __name__ == "__main__":
    main()
