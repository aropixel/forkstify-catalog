#!/usr/bin/env python3
"""Consolide tous les signaux de learned/ en un classement d'artistes.

Score : titres aimés ×1, albums aimés ×3, suivi +8, titres de playlist ×1
(toute playlist : #fipway, road trip, et tout learned/artistes-*.json à venir).
Écrit learned/classement.json.
"""
import json
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "learned"
POIDS = {"titres_aimes": 1, "albums_aimes": 3, "titres_fipway": 1,
         "titres_playlist": 1, "artiste_favori": 5, "albums_favoris": 3}

rows = {}
suivis = set()
for f in sorted(p.glob("artistes-*.json")):
    for a in json.load(open(f)):
        sid = a["spotify"]
        e = rows.setdefault(sid, {"nom": a["nom"], "spotify": sid, "score": 0, "sources": 0})
        compte = False
        for champ, poids in POIDS.items():
            if a.get(champ):
                e[champ] = e.get(champ, 0) + a[champ]
                e["score"] += poids * a[champ]
                compte = True
        if f.name == "artistes-suivis.json":
            suivis.add(sid)
            e["suivi"] = True
            e["score"] += 8
            compte = True
        if compte:
            e["sources"] += 1

classement = sorted(rows.values(), key=lambda e: -e["score"])
(p / "classement.json").write_text(json.dumps(classement, ensure_ascii=False, indent=1))
multi = sum(1 for e in classement if e["sources"] >= 2)
print(f"{len(classement)} artistes, {multi} dans ≥2 sources, "
      f"{sum(1 for e in classement if e['score'] >= 10)} avec score ≥ 10")
for e in classement[:25]:
    print(f"  {e['score']:3d}  {e['nom']}")
