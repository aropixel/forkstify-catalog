#!/usr/bin/env python3
"""Compose le texte de chaque fiche depuis sa structure et calcule les vecteurs.

Le texte n'est jamais demandé aux humains : il est composé depuis les champs
structurés (tags, dates, origine, liens et voisins), la description ajoute de
la nuance quand elle existe (docs/conception/catalogue.md du dépôt forkstify).

Nécessite fastembed — à lancer dans un conteneur :

  docker run --rm -v "$PWD":/catalogue -w /catalogue \
    -e FASTEMBED_CACHE_PATH=/catalogue/outillage/cache/fastembed \
    python:3.12-slim \
    bash -c "pip install -q fastembed && python outillage/vectoriser.py \
             && chown -R $(id -u):$(id -g) vecteurs outillage/cache/fastembed"

Écrit vecteurs/vecteurs.jsonl (une ligne par artiste, triée par slug) et
vecteurs/meta.toml (modèle, dimensions, date). Avec --textes, affiche les
textes composés sans vectoriser (aucune dépendance, utile pour relire).
"""

import datetime
import json
import pathlib
import sys
import tomllib

RACINE = pathlib.Path(__file__).resolve().parent.parent
FICHES = RACINE / "fiches"
VECTEURS = RACINE / "vecteurs"

# Multilingue (nos textes mêlent français et anglais), 384 dimensions,
# ~220 Mo, supporté par fastembed en Python comme en Rust.
MODELE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSIONS = 384
PREFIXE = ""

PAYS = {
    "fr": "France", "uk": "Royaume-Uni", "us": "États-Unis", "be": "Belgique",
    "de": "Allemagne", "it": "Italie", "es": "Espagne", "ca": "Canada",
    "au": "Australie", "se": "Suède", "no": "Norvège", "ie": "Irlande",
    "jp": "Japon", "ml": "Mali", "et": "Éthiopie", "in": "Inde",
    "cz": "Tchéquie", "nl": "Pays-Bas", "ch": "Suisse", "pt": "Portugal",
}

# Phrase par type de lien, dans le sens de la fiche puis en sens inverse
# (les liens sont portés par une seule des deux fiches, la relation vaut
# dans les deux sens ; seul influence est orienté).
PHRASES = {
    "member": ("membres en commun avec {}", "membres en commun avec {}"),
    "collab": ("a collaboré avec {}", "a collaboré avec {}"),
    "similar": ("proche de {}", "proche de {}"),
    "family": ("lié familialement à {}", "lié familialement à {}"),
    "scene": ("même scène que {}", "même scène que {}"),
    "influence": ("influencé par {}", "a influencé {}"),
}


def charger_fiches():
    fiches = {}
    for p in sorted(FICHES.glob("*.toml")):
        fiches[p.stem] = tomllib.loads(p.read_text())
    return fiches


def trier_tags(tags):
    """Sépare genres, pays et décennies."""
    genres, pays, decennies = [], [], []
    for t in tags:
        if t in PAYS:
            pays.append(PAYS[t])
        elif len(t) == 2 and t.isalpha():
            pays.append(t.upper())
        elif t.endswith("s") and t[:-1].isdigit():
            decennies.append("années " + (t[:-1] if len(t) > 3 else "19" + t[:-1]))
        else:
            genres.append(t.replace("-", " "))
    return genres, pays, decennies


def composer(slug, fiches):
    f = fiches[slug]
    phrases = [f["name"]]

    genres, pays, decennies = trier_tags(f.get("tags", []))
    if genres:
        phrases.append("Genres : " + ", ".join(genres))
    if pays:
        phrases.append("Pays : " + ", ".join(pays))
    if decennies:
        phrases.append("Époque : " + ", ".join(decennies))

    debut, fin = f.get("begin"), f.get("end")
    if debut and fin:
        phrases.append(f"Actif de {debut[:4]} à {fin[:4]}")
    elif debut:
        phrases.append(f"Actif depuis {debut[:4]}")
    if f.get("origin"):
        phrases.append("Origine : " + f["origin"])

    # liens sortants, puis entrants (la relation vaut dans les deux sens)
    liens = []
    for l in f.get("links", []):
        cible = fiches.get(l["to"])
        if cible:
            liens.append(PHRASES[l["type"]][0].format(cible["name"]))
    for autre_slug, autre in fiches.items():
        for l in autre.get("links", []):
            if l["to"] == slug:
                liens.append(PHRASES[l["type"]][1].format(autre["name"]))
    if liens:
        phrases.append(" ; ".join(dict.fromkeys(liens)))

    if f.get("description"):
        phrases.append(f["description"].strip())

    return ". ".join(phrases) + "."


def main():
    fiches = charger_fiches()
    textes = {slug: composer(slug, fiches) for slug in fiches}

    if "--textes" in sys.argv:
        cibles = [a for a in sys.argv[1:] if not a.startswith("-")] or textes
        for slug in cibles:
            print(f"--- {slug}\n{textes[slug]}\n")
        return

    from fastembed import TextEmbedding

    modele = TextEmbedding(model_name=MODELE)
    slugs = sorted(textes)
    vecteurs = modele.embed([PREFIXE + textes[s] for s in slugs])

    VECTEURS.mkdir(exist_ok=True)
    with open(VECTEURS / "vecteurs.jsonl", "w") as sortie:
        for slug, v in zip(slugs, vecteurs):
            ligne = {"slug": slug, "v": [round(float(x), 6) for x in v]}
            sortie.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    (VECTEURS / "meta.toml").write_text(
        f'modele = "{MODELE}"\n'
        f"dimensions = {DIMENSIONS}\n"
        f'pooling = "mean"  # fastembed >= 0.6 ; à reproduire côté Rust\n'
        f'prefixe = "{PREFIXE}"\n'
        f'date = "{datetime.date.today().isoformat()}"\n'
        f"fiches = {len(slugs)}\n"
    )
    print(f"{len(slugs)} vecteurs écrits dans vecteurs/vecteurs.jsonl")


if __name__ == "__main__":
    main()
