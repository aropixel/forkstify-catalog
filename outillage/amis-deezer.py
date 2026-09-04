#!/usr/bin/env python3
"""Récupère les artistes du profil Deezer public d'un ami consentant.

Usage : amis-deezer.py <id_utilisateur> <label>
        (l'id numérique est dans l'URL du profil, ex. deezer.com/fr/profile/12345)

Aucune authentification : seules les données publiques du profil sont lues
(artistes favoris, albums favoris, playlists publiques). Résultat dans
learned/amis/<label>-deezer.json.
"""
import json, sys, time, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "learned" / "amis"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "forkstify-bootstrap/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def paginate(url):
    while url:
        page = get(url)
        if "error" in page:
            sys.exit(f"Deezer : {page['error'].get('message', page['error'])} — profil privé ou id invalide ?")
        yield from page.get("data", [])
        url = page.get("next")
        time.sleep(0.3)


def add(counts, artist, champ):
    if not artist or not artist.get("id"):
        return
    e = counts.setdefault(str(artist["id"]),
                          {"nom": artist.get("name", "?"), "deezer": str(artist["id"])})
    e[champ] = e.get(champ, 0) + 1


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    uid, label = sys.argv[1], sys.argv[2]
    base = f"https://api.deezer.com/user/{uid}"
    counts = {}

    favoris = list(paginate(f"{base}/artists?limit=100"))
    for a in favoris:
        add(counts, a, "artiste_favori")
    albums = list(paginate(f"{base}/albums?limit=100"))
    for al in albums:
        add(counts, al.get("artist"), "albums_favoris")
    playlists = list(paginate(f"{base}/playlists?limit=100"))
    n_titres = 0
    for pl in playlists:
        if not pl.get("public", True):
            continue
        for t in paginate(f"https://api.deezer.com/playlist/{pl['id']}/tracks?limit=100"):
            add(counts, t.get("artist"), "titres_playlists")
            n_titres += 1

    ranked = sorted(counts.values(),
                    key=lambda e: -(e.get("artiste_favori", 0) * 5
                                    + e.get("albums_favoris", 0) * 3
                                    + e.get("titres_playlists", 0)))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{label}-deezer.json"
    out.write_text(json.dumps(ranked, ensure_ascii=False, indent=1))
    print(f"{label} : {len(favoris)} artistes favoris, {len(albums)} albums favoris, "
          f"{n_titres} titres de playlists publiques → {len(ranked)} artistes distincts")
    for e in ranked[:20]:
        print(f"  fav={e.get('artiste_favori', 0)} alb={e.get('albums_favoris', 0)} "
              f"pl={e.get('titres_playlists', 0)}  {e['nom']}")
    print(f"Écrit dans {out}")


if __name__ == "__main__":
    main()
