#!/usr/bin/env python3
"""Les voisins d'un artiste dans l'espace des vecteurs — prototype de
`forkstify check` : on ne juge pas son texte, on juge ses effets.

  python3 tools/voisins.py the-cure [n]

Sans argument, affiche les voisins de quelques fiches témoins.
Bibliothèque standard uniquement (lit vectors/vectors.jsonl).
"""

import json
import math
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
TEMOINS = ["the-cure", "experience", "nina-simone", "iam", "les-thugs",
           "yann-tiersen", "idles"]


def charger():
    vecteurs = {}
    for ligne in open(RACINE / "vectors" / "vectors.jsonl"):
        d = json.loads(ligne)
        vecteurs[d["slug"]] = d["v"]
    return vecteurs


def cosinus(a, b):
    scalaire = sum(x * y for x, y in zip(a, b))
    normes = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return scalaire / normes


def voisins(slug, vecteurs, n):
    ref = vecteurs[slug]
    scores = [(cosinus(ref, v), s) for s, v in vecteurs.items() if s != slug]
    return sorted(scores, reverse=True)[:n]


def main():
    vecteurs = charger()
    args = [a for a in sys.argv[1:] if not a.isdigit()]
    n = next((int(a) for a in sys.argv[1:] if a.isdigit()), 10)
    for slug in args or [t for t in TEMOINS if t in vecteurs]:
        if slug not in vecteurs:
            print(f"{slug} : pas de vecteur")
            continue
        print(f"\n{slug} est proche de :")
        for score, s in voisins(slug, vecteurs, n):
            print(f"  {score:.3f}  {s}")


if __name__ == "__main__":
    main()
