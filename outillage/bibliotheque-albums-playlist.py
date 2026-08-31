#!/usr/bin/env python3
"""Lit les albums aimés et la playlist #fipway via la session Omarchy-Spotify.

Même principe que bibliotheque-spotify.py : lecture seule, jeton relu dans le
trousseau GNOME et réécrit s'il tourne, rien d'affiché de sensible.
"""
import json, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CLIENT_ID = "d420a117a32841c2b3474932e49fb54b"
KEYRING = ["service", "quickshell-spotify", "kind", "refresh-token", "client-id", CLIENT_ID]
OUT = Path(__file__).resolve().parent.parent / "usage"
PLAYLIST_NAME = "#fipway"
MAX_PAGES = 200


def keyring_read():
    r = subprocess.run(["secret-tool", "lookup", *KEYRING], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit("Impossible de lire le jeton dans le trousseau.")
    return r.stdout.strip()


def keyring_write(token):
    subprocess.run(["secret-tool", "store", "--label=Omarchy Spotify refresh token", *KEYRING],
                   input=token, text=True, check=True)


def refresh(refresh_token):
    data = urllib.parse.urlencode({"grant_type": "refresh_token",
                                   "refresh_token": refresh_token,
                                   "client_id": CLIENT_ID}).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    new_rt = payload.get("refresh_token")
    if new_rt and new_rt != refresh_token:
        keyring_write(new_rt)
        print("(jeton de rafraîchissement tourné et réécrit dans le trousseau)")
    return payload["access_token"]


def get(token, url, ok404=False):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "2")) + 1)
                continue
            if e.code == 404 and ok404:
                return None
            sys.exit(f"API {e.code} sur {url.split('?')[0]} : {e.read()[:200]}")
    sys.exit("Trop de 429, abandon.")


def paginate(token, first_url):
    url = first_url
    for _ in range(MAX_PAGES):
        page = get(token, url)
        yield from page.get("items", [])
        url = page.get("next")
        if not url:
            return


def add(counts, artist, champ):
    e = counts.setdefault(artist["id"], {"nom": artist["name"], "spotify": artist["id"], champ: 0})
    e[champ] += 1


def main():
    OUT.mkdir(exist_ok=True)
    token = refresh(keyring_read())

    albums = {}
    n_albums = 0
    for it in paginate(token, "https://api.spotify.com/v1/me/albums?limit=50"):
        n_albums += 1
        for a in (it.get("album") or {}).get("artists", []):
            add(albums, a, "albums_aimes")
    ranked = sorted(albums.values(), key=lambda e: -e["albums_aimes"])
    (OUT / "artistes-des-albums-aimes.json").write_text(
        json.dumps(ranked, ensure_ascii=False, indent=1))
    print(f"Albums aimés : {n_albums} → {len(ranked)} artistes distincts")
    for e in ranked[:20]:
        print(f"  {e['albums_aimes']:3d}  {e['nom']}")

    target = None
    for pl in paginate(token, "https://api.spotify.com/v1/me/playlists?limit=50"):
        if (pl.get("name") or "").strip().lower() == PLAYLIST_NAME:
            target = pl
            break
    if not target:
        print(f"\nPlaylist « {PLAYLIST_NAME} » introuvable dans tes playlists.")
        return
    pid = target["id"]
    fip = {}
    n_titres = 0
    base = f"https://api.spotify.com/v1/playlists/{pid}"
    first = get(token, f"{base}/items?limit=50", ok404=True)
    path = "items" if first is not None else "tracks"
    for it in paginate(token, f"{base}/{path}?limit=50"):
        track = it.get("track") or it.get("item") or {}
        if not track.get("artists"):
            continue
        n_titres += 1
        for a in track["artists"]:
            add(fip, a, "titres_fipway")
    ranked = sorted(fip.values(), key=lambda e: -e["titres_fipway"])
    (OUT / "artistes-fipway.json").write_text(json.dumps(ranked, ensure_ascii=False, indent=1))
    print(f"\n#fipway : {n_titres} titres → {len(ranked)} artistes distincts")
    for e in ranked[:20]:
        print(f"  {e['titres_fipway']:3d}  {e['nom']}")
    print(f"\nDétail écrit dans {OUT}/")


if __name__ == "__main__":
    main()
