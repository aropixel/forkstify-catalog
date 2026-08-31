#!/usr/bin/env python3
"""Récupère les artistes d'une playlist du compte Spotify de Joel.

Usage : playlist-spotify.py "<nom exact de la playlist>"

Même principe que les autres scripts : lecture seule, jeton relu dans le
trousseau GNOME et réécrit s'il tourne. Résultat dans
usage/artistes-<slug-du-nom>.json (pris en compte par resoudre-mbid.py).
"""
import json, re, subprocess, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CLIENT_ID = "d420a117a32841c2b3474932e49fb54b"
KEYRING = ["service", "quickshell-spotify", "kind", "refresh-token", "client-id", CLIENT_ID]
OUT = Path(__file__).resolve().parent.parent / "usage"


def slugifier(nom):
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "playlist"


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


def paginate(token, url):
    while url:
        page = get(token, url)
        if page is None:
            return
        yield from page.get("items", [])
        url = page.get("next")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    voulu = sys.argv[1].strip()
    token = refresh(keyring_read())

    cible = None
    for pl in paginate(token, "https://api.spotify.com/v1/me/playlists?limit=50"):
        if (pl.get("name") or "").strip().lower() == voulu.lower():
            cible = pl
            break
    if not cible:
        sys.exit(f"Playlist « {voulu} » introuvable dans tes playlists.")

    base = f"https://api.spotify.com/v1/playlists/{cible['id']}"
    first = get(token, f"{base}/items?limit=50", ok404=True)
    path = "items" if first is not None else "tracks"
    counts, n_titres = {}, 0
    for it in paginate(token, f"{base}/{path}?limit=50"):
        track = it.get("track") or {}
        if not track.get("artists"):
            continue
        n_titres += 1
        for a in track["artists"]:
            e = counts.setdefault(a["id"], {"nom": a["name"], "spotify": a["id"],
                                            "titres_playlist": 0})
            e["titres_playlist"] += 1

    ranked = sorted(counts.values(), key=lambda e: -e["titres_playlist"])
    slug = slugifier(cible["name"])
    out = OUT / f"artistes-{slug}.json"
    out.write_text(json.dumps(ranked, ensure_ascii=False, indent=1))
    print(f"« {cible['name']} » : {n_titres} titres → {len(ranked)} artistes distincts")
    for e in ranked[:20]:
        print(f"  {e['titres_playlist']:3d}  {e['nom']}")
    print(f"Écrit dans {out}")


if __name__ == "__main__":
    main()
