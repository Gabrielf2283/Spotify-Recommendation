import os
import sys
import time
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ─────────────────────────────────────────────
#   CONFIGURATION — fill in your credentials
# ─────────────────────────────────────────────

SPOTIFY_CLIENT_ID     = "56914569c6f34fca949971f55ee3720f"
SPOTIFY_CLIENT_SECRET = "da06d5b9dbb240de922fc697fd532eae"
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8888/callback"   # must match your Spotify app settings
LASTFM_API_KEY        = "77a9bf8f4b0d3f47553e83b74fd41fa6"

# ─────────────────────────────────────────────
#   TERMINAL STYLE HELPERS
# ─────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
RED    = "\033[91m"
WHITE  = "\033[97m"
PURPLE = "\033[95m"
BLUE   = "\033[94m"

def clr(text, *codes):
    return "".join(codes) + str(text) + RESET

def banner():
    os.system("cls" if os.name == "nt" else "clear")
    print(clr("╔══════════════════════════════════════════════════════╗", CYAN, BOLD))
    print(clr("║", CYAN, BOLD) + clr("          🎵  MUSIC RECOMMENDATION ENGINE  🎵         ", WHITE, BOLD) + clr("║", CYAN, BOLD))
    print(clr("║", CYAN, BOLD) + clr("          Spotify  ✦  Last.fm  ✦  Smart Merge          ", DIM) + clr("║", CYAN, BOLD))
    print(clr("╚══════════════════════════════════════════════════════╝", CYAN, BOLD))
    print()

def divider(char="─", width=56):
    print(clr(char * width, DIM))

def spinner(label, duration=1.2):
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    end = time.time() + duration
    i = 0
    while time.time() < end:
        print(f"\r  {clr(frames[i % len(frames)], CYAN)} {label} ", end="", flush=True)
        time.sleep(0.08)
        i += 1
    print("\r" + " " * 60 + "\r", end="", flush=True)

def tag(label, color):
    return color + BOLD + f"[{label}]" + RESET

def print_track(index, name, artist, badge=""):
    num   = clr(f"{index:>2}.", DIM)
    track = clr(name, WHITE, BOLD)
    art   = clr(f"by {artist}", DIM)
    print(f"  {num}  {track}  {art}  {badge}")

# ─────────────────────────────────────────────
#   SPOTIFY SETUP
# ─────────────────────────────────────────────

def init_spotify():
    try:
        auth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="user-read-private",
            cache_path=".spotify_cache",
            open_browser=True,
        )
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        sp = spotipy.Spotify(auth_manager=auth, requests_session=session)
        sp.prefix = "https://api.spotify.com/v1/"
        return sp
    except Exception as e:
        print(clr(f"\n  ✖ Spotify init failed: {e}", RED))
        return None

# ─────────────────────────────────────────────
#   SPOTIFY RECOMMENDATIONS
#   (fallback method — /recommendations deprecated)
# ─────────────────────────────────────────────

def get_spotify_recs(sp, song_query, limit=10):
    
    #Returns list of dicts: {name, artist, id, url}
    #Strategy:
    #1. Search for the song, grab track + artist IDs
    # 2. Try sp.recommendations() — works only for pre-Nov-2024 apps
    # 3. Fallback: artist top tracks + search by artist name
    results = []

    search = sp.search(q=song_query, type="track", limit=1)
    items  = search.get("tracks", {}).get("items", [])
    if not items:
        return None, None, results

    track      = items[0]
    track_id   = track["id"]
    track_name = track["name"]
    artist_name = track["artists"][0]["name"]
    artist_id   = track["artists"][0]["id"]

    # ── Try the official recommendations endpoint first ──
    try:
        recs = sp.recommendations(
            seed_tracks=[track_id],
            seed_artists=[artist_id],
            limit=limit,
            market="US",
        )
        for t in recs.get("tracks", []):
            results.append({
                "name":   t["name"],
                "artist": t["artists"][0]["name"],
                "id":     t["id"],
                "url":    t["external_urls"].get("spotify", ""),
                "source": "spotify",
            })
        if results:
            return track_name, artist_name, results
    except Exception:
        pass  # endpoint deprecated — fall through

    # ── Fallback: artist top tracks + keyword search ──
    seen_ids = {track_id}

    try:
        top = sp.artist_top_tracks(artist_id, market="US").get("tracks", [])
        for t in top:
            if t["id"] not in seen_ids:
                seen_ids.add(t["id"])
                results.append({
                    "name":   t["name"],
                    "artist": t["artists"][0]["name"],
                    "id":     t["id"],
                    "url":    t["external_urls"].get("spotify", ""),
                    "source": "spotify",
                })
    except Exception:
        pass

    try:
        more = sp.search(q=f'artist:"{artist_name}"', type="track", limit=10)
        for t in more.get("tracks", {}).get("items", []):
            if t["id"] not in seen_ids:
                seen_ids.add(t["id"])
                results.append({
                    "name":   t["name"],
                    "artist": t["artists"][0]["name"],
                    "id":     t["id"],
                    "url":    t["external_urls"].get("spotify", ""),
                    "source": "spotify",
                })
    except Exception:
        pass

    return track_name, artist_name, results[:limit]

# ─────────────────────────────────────────────
#   LAST.FM RECOMMENDATIONS
# ─────────────────────────────────────────────

def get_lastfm_recs(track_name, artist_name, limit=10):
    """Returns list of dicts: {name, artist, url}"""
    try:
        resp = requests.get(
            "http://ws.audioscrobbler.com/2.0/",
            params={
                "method":  "track.getSimilar",
                "track":   track_name,
                "artist":  artist_name,
                "api_key": LASTFM_API_KEY,
                "format":  "json",
                "limit":   limit,
            },
            timeout=10,
        )
        data    = resp.json()
        similar = data.get("similartracks", {}).get("track", [])
        return [
            {
                "name":   t["name"],
                "artist": t["artist"]["name"],
                "url":    t.get("url", ""),
                "source": "lastfm",
            }
            for t in similar
        ]
    except Exception as e:
        print(clr(f"\n  ✖ Last.fm error: {e}", RED))
        return []

# ─────────────────────────────────────────────
#   SMART MERGE LOGIC
#   - If overlap exists  → include overlap + fill to 10 total
#   - No overlap         → 2 from Spotify, 3 from Last.fm (5 total)
# ─────────────────────────────────────────────

def normalize(s):
    return s.lower().strip()

def smart_merge(spotify_recs, lastfm_recs):
    """
    Returns (merged_list, overlap_list)
    merged_list items have a 'badge' field indicating source/overlap.
    """
    sp_lookup = {
        (normalize(r["name"]), normalize(r["artist"])): r
        for r in spotify_recs
    }
    lfm_lookup = {
        (normalize(r["name"]), normalize(r["artist"])): r
        for r in lastfm_recs
    }

    overlap_keys = set(sp_lookup.keys()) & set(lfm_lookup.keys())
    overlap      = [sp_lookup[k] for k in overlap_keys]

    if overlap:
        # Start with overlapping tracks (up to 5), then fill from each source
        merged   = []
        used_keys = set()

        for k in list(overlap_keys)[:5]:
            rec = dict(sp_lookup[k])
            rec["badge"] = "overlap"
            merged.append(rec)
            used_keys.add(k)

        # Fill remaining from Spotify then Last.fm alternately
        sp_extra  = [r for k, r in sp_lookup.items()  if k not in used_keys]
        lfm_extra = [r for k, r in lfm_lookup.items() if k not in used_keys]
        for r in sp_extra:
            if len(merged) >= 10:
                break
            rec = dict(r); rec["badge"] = "spotify"
            merged.append(rec); used_keys.add((normalize(r["name"]), normalize(r["artist"])))
        for r in lfm_extra:
            if len(merged) >= 10:
                break
            rec = dict(r); rec["badge"] = "lastfm"
            merged.append(rec); used_keys.add((normalize(r["name"]), normalize(r["artist"])))

        return merged, overlap

    else:
        # No overlap — 2 from Spotify, 3 from Last.fm
        merged = []
        for r in spotify_recs[:2]:
            rec = dict(r); rec["badge"] = "spotify"
            merged.append(rec)
        for r in lastfm_recs[:3]:
            rec = dict(r); rec["badge"] = "lastfm"
            merged.append(rec)
        return merged, []

# ─────────────────────────────────────────────
#   DISPLAY RESULTS
# ─────────────────────────────────────────────

BADGE_LABELS = {
    "overlap": clr("✦ BOTH",    YELLOW, BOLD),
    "spotify": clr("● Spotify", GREEN),
    "lastfm":  clr("◆ Last.fm", PURPLE),
}

def display_source_list(title, color, recs, limit=10):
    divider()
    print(f"  {color}{BOLD}{title}{RESET}")
    divider()
    if not recs:
        print(clr("  No results found.", RED))
        return
    for i, r in enumerate(recs[:limit], 1):
        print_track(i, r["name"], r["artist"])
    print()

def display_merged(merged, overlap):
    divider("═")
    print(f"  {clr('🎯  SMART MERGE', CYAN, BOLD)}", end="")
    if overlap:
        print(f"  {clr(f'({len(overlap)} overlap found — showing up to 10)', YELLOW)}")
    else:
        print(f"  {clr('(no overlap — 2 Spotify + 3 Last.fm)', DIM)}")
    divider("═")

    for i, r in enumerate(merged, 1):
        badge = BADGE_LABELS.get(r.get("badge", ""), "")
        print_track(i, r["name"], r["artist"], badge)
    print()

# ─────────────────────────────────────────────
#   SAVE TO FILE
# ─────────────────────────────────────────────

def save_results(song_query, track_name, artist_name, sp_recs, lfm_recs, merged, overlap):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recommendations.txt")
    with open(path, "a", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(f"Query   : {song_query}\n")
        f.write(f"Matched : {track_name} by {artist_name}\n")
        f.write("=" * 60 + "\n\n")

        f.write("── Spotify ──\n")
        for i, r in enumerate(sp_recs[:10], 1):
            f.write(f"  {i:>2}. {r['name']} - {r['artist']}\n")

        f.write("\n── Last.fm ──\n")
        for i, r in enumerate(lfm_recs[:10], 1):
            f.write(f"  {i:>2}. {r['name']} - {r['artist']}\n")

        f.write("\n── Smart Merge ──\n")
        if overlap:
            f.write(f"  ({len(overlap)} tracks appeared in both sources)\n")
        for i, r in enumerate(merged, 1):
            badge = {"overlap": "[BOTH]", "spotify": "[Spotify]", "lastfm": "[Last.fm]"}.get(r.get("badge", ""), "")
            f.write(f"  {i:>2}. {r['name']} - {r['artist']}  {badge}\n")

        f.write("\n")
    return path

# ─────────────────────────────────────────────
#   MAIN LOOP
# ─────────────────────────────────────────────

def main():
    banner()

    # Init Spotify
    print(clr("  Initializing Spotify...", DIM))
    sp = init_spotify()
    if not sp:
        print(clr("  ✖ Could not connect to Spotify. Check your credentials.", RED))
        sys.exit(1)
    print(clr("  ✔ Spotify connected", GREEN))
    print(clr("  ✔ Last.fm ready", GREEN))
    print()
    divider()
    print(clr("  Type a song name to get recommendations.", WHITE))
    print(clr("  Type 'exit' or press Ctrl+C to quit.", DIM))
    divider()

    while True:
        try:
            print()
            query = input(clr("  🎵 Song: ", CYAN, BOLD)).strip()
        except (KeyboardInterrupt, EOFError):
            print(clr("\n\n  Goodbye! 🎶\n", CYAN))
            break

        if not query:
            continue
        if query.lower() in ("exit", "quit", "q"):
            print(clr("\n  Goodbye! 🎶\n", CYAN))
            break

        print()

        # ── Spotify ──
        spinner(f"Fetching Spotify recommendations for  \"{query}\"...")
        track_name, artist_name, sp_recs = get_spotify_recs(sp, query, limit=10)

        if track_name is None:
            print(clr(f"  ✖ Could not find \"{query}\" on Spotify.", RED))
            continue

        print(clr(f"  ✔ Found: ", GREEN) + clr(track_name, WHITE, BOLD) + clr(f" by {artist_name}", DIM))

        # ── Last.fm ──
        spinner(f"Fetching Last.fm similar tracks...")
        lfm_recs = get_lastfm_recs(track_name, artist_name, limit=10)

        if not lfm_recs:
            print(clr("  ⚠ Last.fm returned no results.", YELLOW))

        print()

        # ── Display each source ──
        display_source_list("SPOTIFY  RECOMMENDATIONS", GREEN,  sp_recs,  limit=10)
        display_source_list("LAST.FM  RECOMMENDATIONS", PURPLE, lfm_recs, limit=10)

        # ── Merge ──
        merged, overlap = smart_merge(sp_recs, lfm_recs)
        display_merged(merged, overlap)

        # ── Save ──
        path = save_results(query, track_name, artist_name, sp_recs, lfm_recs, merged, overlap)
        print(clr(f"  💾 Saved to: {path}", DIM))

if __name__ == "__main__":
    main()