#!/usr/bin/env python3
"""Récupère les artistes des playlists PUBLIQUES d'un utilisateur Spotify.

Usage : amis-spotify.py <id_utilisateur> <label>
        (l'id est dans l'URL du profil, ex. open.spotify.com/user/xxxx)

Utilise la session Omarchy-Spotify de Joel (jeton relu dans le trousseau,
réécrit s'il tourne) : seules les playlists publiques de la cible sont
visibles — jamais ses titres ou artistes aimés. Résultat dans
learned/amis/<label>-spotify.json.

Réserve : depuis 2026, Spotify peut refuser le contenu de certaines
playlists d'autrui ; les playlists illisibles sont signalées et ignorées.
"""
import json, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CLIENT_ID = "d420a117a32841c2b3474932e49fb54b"
KEYRING = ["service", "quickshell-spotify", "kind", "refresh-token", "client-id", CLIENT_ID]
OUT = Path(__file__).resolve().parent.parent / "learned" / "amis"


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


def get(token, url, tolere=(403, 404)):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "2")) + 1)
                continue
            if e.code in tolere:
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
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    uid, label = sys.argv[1], sys.argv[2]
    token = refresh(keyring_read())
    counts, n_titres, illisibles = {}, 0, []
    playlists = list(paginate(token,
        f"https://api.spotify.com/v1/users/{urllib.parse.quote(uid)}/playlists?limit=50"))
    if not playlists:
        sys.exit("Aucune playlist publique visible pour cet utilisateur.")
    for pl in playlists:
        if (pl.get("owner") or {}).get("id") != uid:
            continue  # playlists suivies mais pas créées par la cible
        base = f"https://api.spotify.com/v1/playlists/{pl['id']}"
        first = get(token, f"{base}/items?limit=50")
        path = "items" if first is not None else "tracks"
        items = list(paginate(token, f"{base}/{path}?limit=50"))
        if not items:
            illisibles.append(pl.get("name", pl["id"]))
            continue
        for it in items:
            track = it.get("track") or {}
            for a in track.get("artists", []):
                e = counts.setdefault(a["id"], {"nom": a["name"], "spotify": a["id"],
                                                "titres_playlists": 0})
                e["titres_playlists"] += 1
                n_titres += 1
    ranked = sorted(counts.values(), key=lambda e: -e["titres_playlists"])
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{label}-spotify.json"
    out.write_text(json.dumps(ranked, ensure_ascii=False, indent=1))
    print(f"{label} : {len(playlists)} playlists publiques, {n_titres} titres lus "
          f"→ {len(ranked)} artistes distincts")
    if illisibles:
        print(f"Playlists au contenu refusé par l'API : {', '.join(illisibles)}")
    for e in ranked[:20]:
        print(f"  {e['titres_playlists']:3d}  {e['nom']}")
    print(f"Écrit dans {out}")


if __name__ == "__main__":
    main()
