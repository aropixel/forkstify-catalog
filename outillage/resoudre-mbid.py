#!/usr/bin/env python3
"""Résout les MBID MusicBrainz des artistes via leur URL Spotify (1 req/s)."""
import json, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "usage"
OUT = SRC / "mbid.json"
UA = "forkstify-bootstrap/0.1 (joel.gomez@aropixel.com)"

artists = {}
for f in sorted(SRC.glob("artistes-*.json")):
    for a in json.load(open(f)):
        artists.setdefault(a["spotify"], a["nom"])

done = json.load(open(OUT)) if OUT.exists() else {}


def mb(url):
    """GET MusicBrainz avec respect du 1 req/s et réessai sur 429/503."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        time.sleep(1.1)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(3 * (attempt + 1))
                continue
            if e.code == 404:
                return None
            raise
    return None


restants = [(sid, nom) for sid, nom in sorted(artists.items(), key=lambda kv: kv[1])
            if not (done.get(sid) or {}).get("mbid")]
print(f"{len(restants)} artistes à résoudre ({len(done)} déjà en cache, "
      f"{sum(1 for e in done.values() if e.get('mbid'))} avec MBID)")

for i, (sid, nom) in enumerate(restants):
    entry = {"nom": nom, "mbid": None, "methode": None}
    try:  # 1) par URL Spotify (précis, pas d'homonyme)
        res = urllib.parse.quote(f"https://open.spotify.com/artist/{sid}", safe="")
        data = mb(f"https://musicbrainz.org/ws/2/url?resource={res}&inc=artist-rels&fmt=json")
        rels = [r for r in (data or {}).get("relations", []) if r.get("artist")]
        if rels:
            entry.update(mbid=rels[0]["artist"]["id"], methode="url-spotify")
    except Exception as e:
        print(f"  ! {nom} (url) : {e}")
    if not entry["mbid"]:
        try:  # 2) par nom, en repli (à relire)
            q = urllib.parse.quote(f'artist:"{nom}"')
            data = mb(f"https://musicbrainz.org/ws/2/artist?query={q}&limit=1&fmt=json")
            hits = (data or {}).get("artists", [])
            if hits and int(hits[0].get("score", 0)) >= 95:
                entry.update(mbid=hits[0]["id"], methode="nom")
        except Exception as e:
            print(f"  ! {nom} (nom) : {e}")
    done[sid] = entry
    if i % 20 == 0:
        OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1))

OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1))
par_url = sum(1 for e in done.values() if e["methode"] == "url-spotify")
par_nom = sum(1 for e in done.values() if e["methode"] == "nom")
sans = sorted(e["nom"] for e in done.values() if not e["mbid"])
print(f"{len(done)} artistes : {par_url} par URL Spotify, {par_nom} par nom (à relire), "
      f"{len(sans)} sans MBID")
if sans:
    print("Sans MBID :", ", ".join(sans))
