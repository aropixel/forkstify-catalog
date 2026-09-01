#!/usr/bin/env python3
"""Génère des fiches TOML (marquées `generated`) depuis MusicBrainz et Deezer.

Usage : generer-fiches.py [slug ...]
Sans argument : tous les slugs appelés par les links des fiches existantes
et qui n'ont pas encore de fiche (le « lot suivant »).

Sources (pipeline du démarrage à froid, docs/conception/catalogue.md) :
- identité, dates, origine, genres, relations : MusicBrainz (1 req/s) ;
- tops et similaires : Deezer, sans clé ;
- description et notes : absentes — tout est optionnel, la relecture enrichit.
"""
import json, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from pathlib import Path

try:
    import tomllib
except ImportError:
    sys.exit("Python ≥ 3.11 requis (tomllib)")

RACINE = Path(__file__).resolve().parent.parent
FICHES = RACINE / "fiches"
USAGE = RACINE / "usage"
CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)
UA = "forkstify-bootstrap/0.1 (joel.gomez@aropixel.com)"

# --- HTTP avec cache disque -------------------------------------------------

def http(url, pause):
    """GET JSON, mis en cache dans outillage/cache/, réessai sur 429/503."""
    clef = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[-150:]
    fichier = CACHE / f"{clef}.json"
    if fichier.exists():
        return json.load(open(fichier))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for essai in range(4):
        time.sleep(pause)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            json.dump(data, open(fichier, "w"))
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(3 * (essai + 1))
                continue
            if e.code == 404:
                return None
            raise
    return None

def mb(chemin):
    return http(f"https://musicbrainz.org/ws/2/{chemin}", pause=1.1)

def deezer(chemin):
    return http(f"https://api.deezer.com/{chemin}", pause=0.5)

# --- Slugs ------------------------------------------------------------------

def slugifier(nom):
    nom = nom.replace("&", " and ")
    nom = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    nom = re.sub(r"[''']", "", nom)
    return "-".join(re.findall(r"[a-z0-9]+", nom.lower()))

def clef_de_correspondance(slug):
    """Slug normalisé pour comparer : ignore les mots vides and/et."""
    return "-".join(m for m in slug.split("-") if m not in ("and", "et"))

# --- Univers connu : fiches + bibliothèque résolue --------------------------

def charger_univers():
    """clef de correspondance -> {slug, nom, mbid, spotify}."""
    univers = {}
    for entree in json.load(open(USAGE / "mbid.json")).items():
        spotify, e = entree
        if not e.get("mbid"):
            continue
        univers.setdefault(clef_de_correspondance(slugifier(e["nom"])), {
            "slug": slugifier(e["nom"]), "nom": e["nom"],
            "mbid": e["mbid"], "spotify": spotify, "methode": e["methode"],
        })
    for p in FICHES.glob("*.toml"):  # les fiches priment sur la bibliothèque
        f = tomllib.load(open(p, "rb"))
        univers[clef_de_correspondance(p.stem)] = {
            "slug": p.stem, "nom": f["name"], "mbid": f.get("mbid"),
            "spotify": f.get("spotify"), "methode": "fiche",
        }
    return univers

def slugs_appeles_sans_fiche():
    existants = {p.stem for p in FICHES.glob("*.toml")}
    appeles = set()
    for p in FICHES.glob("*.toml"):
        for l in tomllib.load(open(p, "rb")).get("links", []):
            appeles.add(l["to"])
    return sorted(appeles - existants)

# --- MusicBrainz ------------------------------------------------------------

TYPES_RELATION = {  # relation MusicBrainz -> type de link du format 1
    "member of band": "member", "founder": "member",
    "collaboration": "collab", "supporting musician": "collab",
    "instrumental supporting musician": "collab", "vocal supporting musician": "collab",
    "sibling": "family", "parent": "family", "married": "family",
}

def chercher_mbid(nom):
    """Recherche par nom ; on compare les slugs, pas le score seul —
    « destinys child » doit trouver « Destiny's Child »."""
    data = mb(f"artist?query={urllib.parse.quote(nom)}&limit=5&fmt=json")
    voulu = clef_de_correspondance(slugifier(nom))
    for hit in (data or {}).get("artists", []):
        if int(hit.get("score", 0)) < 90:
            break
        if clef_de_correspondance(slugifier(hit["name"])) == voulu:
            return hit["id"]
    return None

def faits_musicbrainz(mbid):
    a = mb(f"artist/{mbid}?inc=genres+artist-rels+url-rels&fmt=json")
    if not a:
        return None
    vie = a.get("life-span") or {}
    genres = [g["name"] for g in sorted(a.get("genres", []),
                                        key=lambda g: -g.get("count", 0))]
    relations, spotify, deezer_id = [], None, None
    for rel in a.get("relations", []):
        url = (rel.get("url") or {}).get("resource", "")
        if (m := re.search(r"open\.spotify\.com/artist/(\w+)", url)):
            spotify = m.group(1)
        if (m := re.search(r"deezer\.com/(?:\w+/)?artist/(\d+)", url)):
            deezer_id = m.group(1)
        cible = rel.get("artist")
        if cible and (t := TYPES_RELATION.get(rel.get("type"))):
            relations.append({"type": t, "nom": cible["name"], "mbid": cible["id"],
                              "debut": rel.get("begin"), "fin": rel.get("end")})
    return {
        "nom": a["name"], "pays": a.get("country"),
        "zone": (a.get("begin-area") or {}).get("name"),
        "debut": vie.get("begin"), "fin": vie.get("ended") and vie.get("end"),
        "genres": genres, "relations": relations,
        "spotify": spotify, "deezer": deezer_id,
    }

# --- Deezer -----------------------------------------------------------------

def deezer_id_par_nom(nom):
    data = deezer(f"search/artist?q={urllib.parse.quote(nom)}&limit=5")
    voulu = clef_de_correspondance(slugifier(nom))
    for hit in (data or {}).get("data", []):
        if clef_de_correspondance(slugifier(hit["name"])) == voulu:
            return str(hit["id"])
    return None

def nettoyer_titre(titre):
    return re.sub(r"\s*[(\[-][^()\[\]]*(?:remaster|\bmaster\b)[^()\[\]]*[)\]]?\s*$",
                  "", titre, flags=re.I).strip(" -")

def tops_et_similaires(deezer_id):
    top = deezer(f"artist/{deezer_id}/top?limit=10") or {}
    tops, vus = [], set()
    for t in top.get("data", []):
        titre = nettoyer_titre(t["title"])
        if titre.lower() not in vus:
            vus.add(titre.lower())
            tops.append(titre)
        if len(tops) == 5:
            break
    related = deezer(f"artist/{deezer_id}/related?limit=20") or {}
    similaires = [a["name"] for a in related.get("data", [])]
    return tops, similaires

# --- Tags -------------------------------------------------------------------

PAYS = {"GB": "uk"}  # sinon : code ISO en minuscules (FR -> fr, US -> us)

def tag_decennie(debut):
    annee = int(debut[:4]) if debut and debut[:4].isdigit() else None
    if not annee:
        return None
    return f"{annee % 100 // 10 * 10}s" if annee < 2000 else f"{annee // 10 * 10}s"

def composer_tags(faits):
    tags = [slugifier(g) for g in faits["genres"][:4]]
    if faits["pays"]:
        tags.append(PAYS.get(faits["pays"], faits["pays"].lower()))
    if (d := tag_decennie(faits["debut"])):
        tags.append(d)
    return tags

# --- Écriture de la fiche ---------------------------------------------------

def toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

def ecrire_fiche(slug, fiche):
    lignes = ["format = 1", "generated = true",
              f"name = {toml_str(fiche['name'])}", f"mbid = \"{fiche['mbid']}\""]
    for champ in ("spotify", "begin", "end", "origin"):
        if fiche.get(champ):
            lignes.append(f"{champ} = {toml_str(str(fiche[champ]))}")
    lignes += ["", "tags = [" + ", ".join(toml_str(t) for t in fiche["tags"]) + "]"]
    if fiche["tops"]:
        lignes += ["", "tops = ["] + [f"  {toml_str(t)}," for t in fiche["tops"]] + ["]"]
    if fiche["links"]:
        lignes += ["", "links = ["]
        for l in fiche["links"]:
            morceaux = [f"to = \"{l['to']}\"", f"type = \"{l['type']}\""]
            if l.get("note"):
                morceaux.append(f"note = {toml_str(l['note'])}")
            lignes.append("  { " + ", ".join(morceaux) + " },")
        lignes.append("]")
    (FICHES / f"{slug}.toml").write_text("\n".join(lignes) + "\n")

# --- Liens scene par recoupement --------------------------------------------

def liens_scene(fiche, toutes, deja_lies):
    """Même pays, activité qui se chevauche (±10 ans), ≥ 2 tags communs."""
    resultat = []
    mes_tags = set(fiche["tags"])
    mon_pays = next((t for t in fiche["tags"] if len(t) == 2), None)
    ma_decennie = fiche.get("begin") and fiche["begin"][:4]
    for autre_slug, autre in toutes.items():
        if autre_slug == fiche["slug"] or autre_slug in deja_lies:
            continue
        tags = set(autre.get("tags", []))
        pays = next((t for t in autre.get("tags", []) if len(t) == 2), None)
        genres_communs = sorted((mes_tags & tags) - {mon_pays} -
                                {t for t in mes_tags | tags if t.endswith("s") and t[:-1].isdigit()})
        sa_decennie = autre.get("begin") and str(autre["begin"])[:4]
        proches = (ma_decennie and sa_decennie and ma_decennie.isdigit()
                   and sa_decennie.isdigit() and abs(int(ma_decennie) - int(sa_decennie)) <= 10)
        if pays and pays == mon_pays and proches and len(genres_communs) >= 2:
            resultat.append({"to": autre_slug, "type": "scene",
                             "note": "même époque et pays, genres proches : "
                                     + ", ".join(genres_communs[:3])})
        if len(resultat) == 2:
            break
    return resultat

# --- Génération -------------------------------------------------------------

def generer(slugs):
    univers = charger_univers()
    lot = set(slugs) | {p.stem for p in FICHES.glob("*.toml")}
    rapport = {"ecrites": [], "a_relire": [], "sans_deezer": [], "echecs": []}
    fiches_ecrites = {}

    for i, slug in enumerate(slugs, 1):
        if (FICHES / f"{slug}.toml").exists():
            print(f"[{i}/{len(slugs)}] {slug} : fiche existante, on ne touche pas")
            continue
        print(f"[{i}/{len(slugs)}] {slug}", flush=True)
        connu = univers.get(clef_de_correspondance(slug), {})
        nom = connu.get("nom") or slug.replace("-", " ")
        mbid = connu.get("mbid") or chercher_mbid(nom)
        if not mbid:
            rapport["echecs"].append((slug, "MBID introuvable"))
            continue
        if connu.get("methode") == "nom" or not connu:
            rapport["a_relire"].append(slug)

        faits = faits_musicbrainz(mbid)
        if not faits:
            rapport["echecs"].append((slug, "artiste MusicBrainz introuvable"))
            continue

        deezer_id = faits["deezer"] or deezer_id_par_nom(faits["nom"])
        tops, similaires = tops_et_similaires(deezer_id) if deezer_id else ([], [])
        if not deezer_id:
            rapport["sans_deezer"].append(slug)

        links, lies = [], set()
        for rel in faits["relations"]:  # relations MusicBrainz, factuelles
            cible = univers.get(clef_de_correspondance(slugifier(rel["nom"])))
            if not cible or cible["slug"] in lies or cible["slug"] == slug:
                continue  # cible hors de l'univers connu : lien abandonné
            note = None
            if rel["type"] == "member" and rel["debut"]:
                note = f"membre ({rel['debut'][:4]}–{rel['fin'][:4] if rel['fin'] else '…'})"
            links.append({"to": cible["slug"], "type": rel["type"], "note": note})
            lies.add(cible["slug"])
        for nom_similaire in similaires:  # similaires Deezer, dans l'univers connu
            cible = univers.get(clef_de_correspondance(slugifier(nom_similaire)))
            if cible and cible["slug"] not in lies and cible["slug"] != slug:
                links.append({"to": cible["slug"], "type": "similar", "note": None})
                lies.add(cible["slug"])
            if sum(1 for l in links if l["type"] == "similar") == 4:
                break

        fiche = {"slug": slug, "name": faits["nom"], "mbid": mbid,
                 "spotify": faits["spotify"] or connu.get("spotify"),
                 "begin": faits["debut"] and faits["debut"][:4],
                 "end": faits["fin"] and str(faits["fin"])[:4],
                 "origin": faits["zone"], "tags": composer_tags(faits),
                 "tops": tops, "links": links}
        fiches_ecrites[slug] = fiche
        univers[clef_de_correspondance(slug)] = {"slug": slug, "nom": faits["nom"],
                                                 "mbid": mbid, "spotify": fiche["spotify"],
                                                 "methode": "fiche"}

    # les liens scene se calculent à la fin, quand tout le lot est connu
    toutes = {}
    for p in FICHES.glob("*.toml"):
        f = tomllib.load(open(p, "rb"))
        toutes[p.stem] = {"slug": p.stem, "tags": f.get("tags", []), "begin": f.get("begin")}
    toutes.update({s: f for s, f in fiches_ecrites.items()})
    for slug, fiche in fiches_ecrites.items():
        if len(fiche["links"]) < 2:
            fiche["links"] += liens_scene(fiche, toutes, {l["to"] for l in fiche["links"]})
        ecrire_fiche(slug, fiche)
        rapport["ecrites"].append(slug)

    print(f"\n{len(rapport['ecrites'])} fiches écrites.")
    for titre, clef in (("À relire (MBID incertain)", "a_relire"),
                        ("Sans Deezer (pas de tops)", "sans_deezer")):
        if rapport[clef]:
            print(f"{titre} : {', '.join(rapport[clef])}")
    for slug, raison in rapport["echecs"]:
        print(f"Échec : {slug} — {raison}")

if __name__ == "__main__":
    cibles = sys.argv[1:] or slugs_appeles_sans_fiche()
    print(f"{len(cibles)} fiches à générer")
    generer(cibles)
