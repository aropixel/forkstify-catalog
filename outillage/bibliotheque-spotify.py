#!/usr/bin/env python3
"""Lit la bibliothèque Spotify de Joel via la session Omarchy-Spotify.

Lecture seule sur l'API. Le jeton de rafraîchissement est relu dans le
trousseau GNOME et le nouveau (rotation) y est réécrit aussitôt, comme le
fait le plugin, pour ne pas déconnecter Omarchy-Spotify. Aucun jeton n'est
affiché ni écrit sur disque.
"""
import json, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CLIENT_ID = "d420a117a32841c2b3474932e49fb54b"  # identité publique ncspot, celle du plugin
KEYRING = ["service", "quickshell-spotify", "kind", "refresh-token", "client-id", CLIENT_ID]
OUT = Path(__file__).resolve().parent.parent / "usage"
MAX_TRACKS = 5000


def keyring_read():
    r = subprocess.run(["secret-tool", "lookup", *KEYRING], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit("Impossible de lire le jeton dans le trousseau (session verrouillée ?).")
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


def get(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for _attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "2")) + 1)
                continue
            sys.exit(f"API {e.code} sur {url.split('?')[0]} : {e.read()[:200]}")
    sys.exit("Trop de 429, abandon.")


def followed_artists(token):
    artists, after = [], None
    while True:
        url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
        if after:
            url += f"&after={after}"
        block = get(token, url).get("artists", {})
        for a in block.get("items", []):
            artists.append({"nom": a["name"], "spotify": a["id"],
                            "genres": a.get("genres", []), "popularite": a.get("popularity")})
        after = (block.get("cursors") or {}).get("after")
        if not after:
            break
    return artists


def liked_track_artists(token):
    counts, offset, total = {}, 0, None
    while offset < MAX_TRACKS:
        page = get(token, f"https://api.spotify.com/v1/me/tracks?limit=50&offset={offset}")
        total = page.get("total", total)
        items = page.get("items", [])
        if not items:
            break
        for it in items:
            for a in (it.get("track") or {}).get("artists", []):
                key = a["id"]
                entry = counts.setdefault(key, {"nom": a["name"], "spotify": key,
                                                "titres_aimes": 0})
                entry["titres_aimes"] += 1
        offset += len(items)
        if page.get("next") is None:
            break
    ranked = sorted(counts.values(), key=lambda e: -e["titres_aimes"])
    return ranked, total, offset


def main():
    OUT.mkdir(exist_ok=True)
    token = refresh(keyring_read())
    suivis = followed_artists(token)
    aimes, total, lus = liked_track_artists(token)
    (OUT / "artistes-suivis.json").write_text(json.dumps(suivis, ensure_ascii=False, indent=1))
    (OUT / "artistes-des-titres-aimes.json").write_text(
        json.dumps(aimes, ensure_ascii=False, indent=1))
    print(f"Artistes suivis : {len(suivis)}")
    print(f"Titres aimés : {total} (lus : {lus}) → {len(aimes)} artistes distincts")
    print("Top des artistes par titres aimés :")
    for e in aimes[:30]:
        print(f"  {e['titres_aimes']:3d}  {e['nom']}")
    print(f"\nDétail écrit dans {OUT}/")


if __name__ == "__main__":
    main()
