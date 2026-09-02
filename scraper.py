import json
import os
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ---------------------------------------------------------------------------
# Discovery & Filtering Configuration
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

HABESHA_KEYWORDS = [
    "ethio", "ethiopian", "eritrean", "habesha", "amharic", 
    "tigrigna", "oromo", "gurage", "ethio-jazz", "ethiopiques"
]

SEED_ARTISTS = [
    "Tilahun Gessesse", "Mahmoud Ahmed", "Alemayehu Eshete", "Mulatu Astatke",
    "Aster Aweke", "Neway Debebe", "Gigi", "Teddy Afro", "Rophnan", 
    "Kassmasse", "Veronica Adane", "Jano Band", "Betty G", "Sami Dan"
]

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
# Strict Habesha Filtering
# ---------------------------------------------------------------------------

def build_habesha_artist_cache(sp):
    """Pre-builds a verified set of Habesha artist IDs from seeds & related artists."""
    verified_ids = set()
    verified_names = {s.lower() for s in SEED_ARTISTS}

    for name in SEED_ARTISTS:
        try:
            results = sp.search(q=f'artist:"{name}"', type="artist", limit=1)
            items = results.get("artists", {}).get("items", [])
            if items:
                aid = items[0]["id"]
                verified_ids.add(aid)
                # Fetch related artists and filter by genre
                related = sp.artist_related_artists(aid)
                for rel in related.get("artists", []):
                    genres = " ".join(rel.get("genres", [])).lower()
                    rel_name = rel.get("name", "").lower()
                    if any(kw in genres for kw in HABESHA_KEYWORDS) or any(kw in rel_name for kw in HABESHA_KEYWORDS):
                        verified_ids.add(rel["id"])
                        verified_names.add(rel_name)
        except Exception as e:
            print(f"Error seeding artist '{name}': {e}")

    return verified_ids, verified_names


def is_habesha_track(track, verified_ids, verified_names):
    """Filters out non-Habesha artists and tracks."""
    artists = track.get("artists", [])
    if not artists:
        return False

    for artist in artists:
        aid = artist.get("id")
        aname = artist.get("name", "").lower()

        if aid in verified_ids or aname in verified_names:
            return True

        if any(kw in aname for kw in HABESHA_KEYWORDS):
            return True

    return False


# ---------------------------------------------------------------------------
# Spotify Discovery
# ---------------------------------------------------------------------------

def fetch_spotify_tracks():
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Spotify credentials missing.")
        return [], None

    try:
        auth_mgr = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(auth_manager=auth_mgr)

        print("Building Habesha artist cache...")
        verified_ids, verified_names = build_habesha_artist_cache(sp)

        unique_tracks = {}

        print("Discovering Habesha tracks...")
        for query in DISCOVERY_QUERIES:
            try:
                results = sp.search(q=query, type="track", limit=20)
                for track in results.get("tracks", {}).get("items", []):
                    if track and track.get("id") and is_habesha_track(track, verified_ids, verified_names):
                        unique_tracks[track["id"]] = track
            except Exception as e:
                print(f"Search error for '{query}': {e}")

        for term in PLAYLIST_SEARCH_TERMS:
            try:
                results = sp.search(q=term, type="playlist", limit=5)
                for playlist in results.get("playlists", {}).get("items", []) or []:
                    if not playlist:
                        continue
                    resp = sp.playlist_items(playlist["id"], limit=50)
                    for item in resp.get("items", []):
                        track = item.get("track") if item else None
                        if track and track.get("id") and is_habesha_track(track, verified_ids, verified_names):
                            unique_tracks[track["id"]] = track
            except Exception as e:
                print(f"Playlist search error for '{term}': {e}")

        print(f"Filtered to {len(unique_tracks)} verified Habesha tracks.")
        return list(unique_tracks.values()), sp
    except Exception as e:
        print(f"Spotify authentication error: {e}")
        return [], None


# ---------------------------------------------------------------------------
# Data Aggregations & Top 15 Artists
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
    """Aggregates Habesha artists and fetches profile pictures directly from Spotify."""
    artist_counts = {}

    for track in tracks:
        pop = track.get("popularity", 0)
        for artist in track.get("artists", []):
            aid = artist.get("id")
            name = artist.get("name")
            if not aid or not name:
                continue
            if aid not in artist_counts:
                artist_counts[aid] = {"name": name, "total_pop": 0, "count": 0}
            artist_counts[aid]["total_pop"] += pop
            artist_counts[aid]["count"] += 1

    sorted_artists = sorted(
        artist_counts.items(),
        key=lambda x: (x[1]["total_pop"], x[1]["count"]),
        reverse=True
    )[:limit]

    artist_ids = [aid for aid, _ in sorted_artists]
    spotify_artist_details = {}

    if sp and artist_ids:
        try:
            resp = sp.artists(artist_ids)
            for a in resp.get("artists", []):
                if a:
                    spotify_artist_details[a["id"]] = a
        except Exception as e:
            print(f"Error fetching artist profile batch: {e}")

    rows = [["Rank", "Cover", "Artist", "Bio"]]

    for rank, (aid, data) in enumerate(sorted_artists, start=1):
        sp_details = spotify_artist_details.get(aid, {})
        images = sp_details.get("images", [])
        
        # High-res profile image URL fallback
        profile_img = images[0]["url"] if images else ""

        genres = sp_details.get("genres", [])
        genre_str = ", ".join([g.title() for g in genres[:2]]) if genres else "Habesha Icon"
        followers = sp_details.get("followers", {}).get("total", 0)
        follower_str = f"{followers:,} followers" if followers else f"{data['count']} tracks"

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
            growth = curr_pop - past_scores[tid]
            t_copy["score"] = (float(growth), float(curr_pop))
            t_copy["growth_str"] = f"+{growth}" if growth > 0 else str(growth)
        else:
            rel_date = parse_release_date(t.get("album", {}).get("release_date"))
            days_old = (now - rel_date).days

            if days_back == 7:
                recency_weight = max(0.0, 100.0 - (days_old / 30.0))
                calc_score = curr_pop * 1.5 + recency_weight
            elif days_back == 30:
                recency_weight = max(0.0, 50.0 - (days_old / 90.0))
                calc_score = curr_pop + recency_weight
            elif days_back == 90:
                recency_weight = max(0.0, 25.0 - (days_old / 180.0))
                calc_score = curr_pop * 1.1 + recency_weight
            else:
                catalog_weight = min(30.0, days_old / 365.0)
                calc_score = curr_pop + catalog_weight

            t_copy["score"] = (float(calc_score), float(curr_pop))
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
# Main Execution
# ---------------------------------------------------------------------------

def main():
    tracks, sp = fetch_spotify_tracks()
    if not tracks:
        print("Spotify returned 0 tracks. Aborting script.")
        return

    gc = get_gspread_client()
    sheet_id = os.environ.get(
        "SPREADSHEET_ID", "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU"
    )
    sheet = gc.open_by_key(sheet_id)

    archive_ws = ensure_archive_tab(sheet)
    append_daily_snapshot(archive_ws, tracks)

    # 1. Top 15 Artists
    artist_rows = prepare_artist_leaderboard_rows(sp, tracks, limit=15)
    update_sheet_tab(sheet, "Top 15 Artists", artist_rows)

    # 2. All-Time Most Heard
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
