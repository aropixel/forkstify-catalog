# Contributing to the reference catalog

forkstify's reference catalog is one TOML card per artist, forked by
every listener. What you write in your fork — a card generated when you
arrived at an artist, a top you fixed, a link you drew — is yours; some of
it is worth sharing. This page says how it comes back here, and how it is
read.

## How a proposal is made

From forkstify, on your fork: `Cp` (or `:catalog propose`). It compares
your cards to the reference, puts their **state** on a branch `proposal`
— never your learned data, never the vectors — pushes it, and opens the
pull request (through `gh` after your `y`, or as a comparison page in the
browser). One proposal is open at a time: proposing again rewrites the
same branch and updates the same pull request.

The pull request's body is written for the reviewer, in two lists:

- **New cards** — pipeline output (MusicBrainz, then Deezer), one line
  each. Nothing to read: things to check, and the action checks them.
- **Edited cards** — what you changed on an existing card, with the
  sections touched and, for a link, the note that says where it came from.

## What the action checks

On every pull request, `forkstify validate` runs on the whole catalog:

- only `cards/` may change — `learned/`, `vectors/`, tooling stay out;
- every card reads as TOML, carries `format = 1`, a `name`, an `mbid`;
- the `mbid` is **unique across the catalog** — the same artist under two
  files is refused, whatever the names;
- the file name is a slug (lower case, digits, hyphens); a name that no
  longer matches it is a warning, not an error — the file is the key;
- every link's target is a slug (a target without a card is a proposal,
  not a mistake), and its type is one of `member`, `collab`, `similar`,
  `family`, `scene`, `influence`, or a type `catalog.toml` declares.

After a merge, the action regenerates `vectors/` and commits it. Never
include the index in a proposal.

## How a proposal is read

- **Generated cards only** (every new card has `generated = true`, no
  existing card touched): a glance at the names and the mbids — the one
  thing the action cannot see is a homonym resolved to the wrong artist —
  then merged as soon as the action is green.
- **Edited cards**: read.
  - Facts — `member`, `collab`, `family` links, a corrected `mbid` or
    Spotify id, a date, an origin — are taken.
  - A `similar` link is taken when it carries its note of provenance
    ("linked while listening, 2026-09-06"). It is a matter of taste,
    written down as such.
  - A change of `tops` is taken when it **fixes an error** — a wrong
    title, a live version, a track that is not the artist's — not when it
    expresses a taste. The reference's tops are only the doors a fresh
    fork enters by; yours live in your fork, and forkstify learns from
    what you play.
  - A description is welcome when it says something the tags do not.

## Language

Cards are read by people: descriptions and notes may be in any language.
Field names, slugs and link types are the format's and stay in English.
