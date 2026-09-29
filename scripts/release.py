#!/usr/bin/env python3
"""
Le versioni del gestionale: calcolarle, scriverle, controllarle.

Una versione sola, `MAGGIORE.MINORE.CORREZIONE` (SemVer), scritta in due
file perché frontend e backend si costruiscono su Railway ognuno dalla sua
cartella e non vedono la radice del repository:

    frontend/package.json        (e package-lock.json)   → piè di pagina
    backend/app/version.py                                → /health, OpenAPI

Il salto lo decidono i commit dall'ultimo tag, che seguono già la forma
`tipo(ambito): descrizione`:

    un `!` dopo il tipo, o «BREAKING CHANGE» nel corpo   → MAGGIORE  (2.0.0)
    almeno un `feat`                                      → MINORE    (1.1.0)
    tutto il resto (fix, docs, chore, test…)              → CORREZIONE (1.0.1)

Sottocomandi:

    prepare [--bump major|minor|patch] [--dry-run] [--no-pr]
        Su `develop`: calcola la versione nuova, aggiorna i file e il
        CHANGELOG, fa il commit `chore(release): vX.Y.Z`, lo pubblica e apre
        la PR di rilascio verso `main`. Il merge resta una scelta umana.
    check [--base REF]
        Le versioni nei file coincidono e il CHANGELOG ha la voce. Con
        `--base` (la PR verso main) la versione deve anche essere più alta
        di quella in REF: un rilascio che non la alza non passa.
    version
        Stampa la versione corrente.
    notes VERSIONE
        Stampa le note di quella versione dal CHANGELOG (per la Release).

Solo libreria standard: gira uguale in locale e nella CI, senza installare
niente.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT_PKG = "frontend/package.json"
FRONT_LOCK = "frontend/package-lock.json"
BACK_VERSION = "backend/app/version.py"
CHANGELOG = "CHANGELOG.md"

LIVELLI = ("patch", "minor", "major")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
COMMIT = re.compile(r"^(?P<tipo>[a-z]+)(?:\((?P<ambito>[^)]*)\))?(?P<rottura>!)?:\s*(?P<descr>.+)$")
VERSIONE_PY = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.M)


class ErroreRilascio(Exception):
    """Qualcosa impedisce di procedere, con il perché da mostrare."""


# ── Versioni ──────────────────────────────────────────────────────

def analizza(versione: str) -> tuple[int, int, int]:
    m = SEMVER.match(versione.strip())
    if not m:
        raise ErroreRilascio(f"Versione non valida: {versione!r} (serve MAGGIORE.MINORE.CORREZIONE)")
    return int(m[1]), int(m[2]), int(m[3])


def alza(versione: str, livello: str) -> str:
    maggiore, minore, correzione = analizza(versione)
    if livello == "major":
        return f"{maggiore + 1}.0.0"
    if livello == "minor":
        return f"{maggiore}.{minore + 1}.0"
    if livello == "patch":
        return f"{maggiore}.{minore}.{correzione + 1}"
    raise ErroreRilascio(f"Livello sconosciuto: {livello}")


def leggi_versioni(radice: Path = ROOT, leggi=None) -> dict[str, str]:
    """Le versioni scritte nei file. `leggi(percorso)` permette di leggerle da
    un altro commit (`git show REF:percorso`) invece che dal disco."""
    leggi = leggi or (lambda p: (radice / p).read_text(encoding="utf-8"))
    pkg = json.loads(leggi(FRONT_PKG))
    lock = json.loads(leggi(FRONT_LOCK))
    m = VERSIONE_PY.search(leggi(BACK_VERSION))
    return {
        FRONT_PKG: pkg.get("version", ""),
        FRONT_LOCK: lock.get("version", ""),
        f"{FRONT_LOCK} (packages[\"\"])": lock.get("packages", {}).get("", {}).get("version", ""),
        BACK_VERSION: m[1] if m else "",
    }


def versione_unica(versioni: dict[str, str]) -> str:
    valori = set(versioni.values())
    if len(valori) != 1 or "" in valori:
        dettaglio = "\n".join(f"  {k}: {v or '(mancante)'}" for k, v in versioni.items())
        raise ErroreRilascio(f"Le versioni nei file non coincidono:\n{dettaglio}")
    return valori.pop()


def scrivi_versione(nuova: str, radice: Path = ROOT) -> None:
    analizza(nuova)
    for percorso in (FRONT_PKG, FRONT_LOCK):
        file = radice / percorso
        dati = json.loads(file.read_text(encoding="utf-8"))
        dati["version"] = nuova
        if percorso == FRONT_LOCK and "" in dati.get("packages", {}):
            dati["packages"][""]["version"] = nuova
        file.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    file = radice / BACK_VERSION
    testo = file.read_text(encoding="utf-8")
    nuovo_testo, n = VERSIONE_PY.subn(f'__version__ = "{nuova}"', testo)
    if n != 1:
        raise ErroreRilascio(f"{BACK_VERSION}: riga __version__ non trovata")
    file.write_text(nuovo_testo, encoding="utf-8")


# ── Commit ────────────────────────────────────────────────────────

@dataclass
class Commit:
    tipo: str
    ambito: str | None
    descrizione: str
    rottura: bool

    @classmethod
    def da_messaggio(cls, oggetto: str, corpo: str = "") -> "Commit":
        m = COMMIT.match(oggetto.strip())
        rottura_corpo = "BREAKING CHANGE" in corpo or "BREAKING-CHANGE" in corpo
        if not m:
            # Un commit fuori forma conta come correzione: meglio una versione
            # un po' più alta che una modifica passata sotto silenzio.
            return cls("altro", None, oggetto.strip(), rottura_corpo)
        return cls(m["tipo"], m["ambito"], m["descr"].strip(), bool(m["rottura"]) or rottura_corpo)


def livello_da_commit(commits: list[Commit]) -> str | None:
    """Il salto che i commit richiedono; `None` se non ce n'è nessuno."""
    utili = [c for c in commits if not (c.tipo == "chore" and c.ambito == "release")]
    if not utili:
        return None
    if any(c.rottura for c in utili):
        return "major"
    if any(c.tipo == "feat" for c in utili):
        return "minor"
    return "patch"


def sezione_changelog(versione: str, data: dt.date, commits: list[Commit]) -> str:
    """La voce del CHANGELOG. Documentazione, test e manutenzione non ci
    finiscono: contano per il numero, non per chi legge cosa è cambiato."""
    def riga(c: Commit) -> str:
        return f"- {c.ambito + ': ' if c.ambito else ''}{c.descrizione}"

    gruppi = [
        ("Cambiamenti incompatibili", [c for c in commits if c.rottura]),
        ("Novità", [c for c in commits if c.tipo == "feat" and not c.rottura]),
        ("Correzioni", [c for c in commits if c.tipo in ("fix", "perf") and not c.rottura]),
    ]
    parti = [f"## [{versione}] — {data.isoformat()}"]
    for titolo, voci in gruppi:
        if voci:
            parti.append(f"### {titolo}\n\n" + "\n".join(riga(c) for c in voci))
    if len(parti) == 1:
        parti.append("Solo manutenzione: documentazione, test, configurazione.")
    return "\n\n".join(parti) + "\n"


def aggiungi_al_changelog(sezione: str, radice: Path = ROOT) -> None:
    file = radice / CHANGELOG
    testo = file.read_text(encoding="utf-8") if file.exists() else "# Changelog\n"
    # La voce nuova va sotto il titolo e sopra la più recente.
    m = re.search(r"^## \[", testo, re.M)
    if m:
        testo = testo[:m.start()] + sezione + "\n" + testo[m.start():]
    else:
        testo = testo.rstrip("\n") + "\n\n" + sezione
    file.write_text(testo, encoding="utf-8")


def note_versione(versione: str, testo_changelog: str) -> str:
    m = re.search(rf"^## \[{re.escape(versione)}\][^\n]*\n(.*?)(?=^## \[|\Z)", testo_changelog, re.M | re.S)
    if not m:
        raise ErroreRilascio(f"{CHANGELOG}: nessuna voce per la versione {versione}")
    return m[1].strip() + "\n"


# ── Git ───────────────────────────────────────────────────────────

def git(*argomenti: str, radice: Path = ROOT) -> str:
    r = subprocess.run(["git", *argomenti], cwd=radice, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroreRilascio(f"git {' '.join(argomenti)}: {r.stderr.strip()}")
    return r.stdout


def commit_dal_tag(tag: str) -> list[Commit]:
    # Separatori che nei messaggi non compaiono mai.
    uscita = git("log", f"{tag}..HEAD", "--no-merges", "--format=%s%x1f%b%x1e")
    commits = []
    for blocco in uscita.split("\x1e"):
        if not blocco.strip():
            continue
        oggetto, _, corpo = blocco.strip("\n").partition("\x1f")
        commits.append(Commit.da_messaggio(oggetto, corpo))
    return commits


# ── Sottocomandi ──────────────────────────────────────────────────

def cmd_version(_args) -> int:
    print(versione_unica(leggi_versioni()))
    return 0


def cmd_notes(args) -> int:
    print(note_versione(args.versione, (ROOT / CHANGELOG).read_text(encoding="utf-8")), end="")
    return 0


def versione_in(ref: str) -> str:
    """La versione in un altro commit. Prima dell'introduzione delle versioni
    (1.0.0) il backend non aveva il suo file: allora vale quella del
    `package.json`, e se manca anche quella si parte da zero."""
    try:
        return versione_unica(leggi_versioni(leggi=lambda p: git("show", f"{ref}:{p}")))
    except ErroreRilascio:
        try:
            return json.loads(git("show", f"{ref}:{FRONT_PKG}")).get("version") or "0.0.0"
        except ErroreRilascio:
            return "0.0.0"


def controlla_salto(prima: str, corrente: str, dove: str = "main") -> None:
    """Un rilascio deve alzare la versione: uguale o più bassa non passa."""
    if analizza(corrente) <= analizza(prima):
        raise ErroreRilascio(
            f"La versione non sale: {prima} in {dove}, {corrente} qui. "
            "Un rilascio verso main si prepara con `python3 scripts/release.py prepare`."
        )


def cmd_check(args) -> int:
    corrente = versione_unica(leggi_versioni())
    note_versione(corrente, (ROOT / CHANGELOG).read_text(encoding="utf-8"))
    if args.base:
        prima = versione_in(args.base)
        controlla_salto(prima, corrente, args.base)
        print(f"Versione {prima} → {corrente}: ok")
    else:
        print(f"Versione {corrente}: file coerenti, voce nel CHANGELOG presente")
    return 0


def cmd_prepare(args) -> int:
    ramo = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if ramo != "develop":
        raise ErroreRilascio(f"Il rilascio si prepara da develop, non da {ramo}")
    if git("status", "--porcelain").strip():
        raise ErroreRilascio("Ci sono modifiche non committate: prima un commit o uno stash")
    git("fetch", "--quiet", "--tags", "origin")
    if git("rev-parse", "HEAD").strip() != git("rev-parse", "origin/develop").strip():
        raise ErroreRilascio("develop locale non coincide con origin/develop: prima pull o push")

    corrente = versione_unica(leggi_versioni())
    try:
        tag = git("describe", "--tags", "--abbrev=0", "--match", "v*").strip()
    except ErroreRilascio:
        raise ErroreRilascio(
            f"Nessun tag di versione raggiungibile. Il primo (v{corrente}) lo crea la CI "
            "al merge su main; se manca, crearlo su main prima di proseguire."
        )
    if tag != f"v{corrente}":
        raise ErroreRilascio(f"L'ultimo tag è {tag} ma i file dicono {corrente}: allineare prima")

    commits = commit_dal_tag(tag)
    livello = args.bump or livello_da_commit(commits)
    if livello is None:
        raise ErroreRilascio(f"Nessun commit da {tag}: non c'è niente da rilasciare")
    nuova = alza(corrente, livello)
    sezione = sezione_changelog(nuova, dt.date.today(), commits)

    motivo = "scelto a mano" if args.bump else "dai commit"
    print(f"{corrente} → {nuova} ({livello}, {motivo}; {len(commits)} commit da {tag})\n")
    print(sezione)
    if args.dry_run:
        print("Prova a vuoto: nessun file toccato.")
        return 0

    scrivi_versione(nuova)
    aggiungi_al_changelog(sezione)
    git("add", FRONT_PKG, FRONT_LOCK, BACK_VERSION, CHANGELOG)
    git("commit", "-m", f"chore(release): v{nuova}")
    git("push", "--quiet", "origin", "develop")
    print(f"Commit di rilascio v{nuova} pubblicato su develop.")

    if args.no_pr:
        return 0
    corpo = (
        f"Rilascio **v{nuova}** ({livello}, {motivo}).\n\n{sezione}\n"
        "Al merge la CI crea il tag e la Release su GitHub. Dopo il merge:\n\n"
        "```bash\ngit checkout develop && git merge --ff-only origin/main && git push\n```\n"
    )
    r = subprocess.run(
        ["gh", "pr", "create", "--base", "main", "--head", "develop",
         "--title", f"Release v{nuova}", "--body", corpo],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise ErroreRilascio(f"PR non aperta: {r.stderr.strip()}")
    print(r.stdout.strip())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Versioni del gestionale New Style Hair")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("prepare", help="prepara il rilascio da develop")
    p.add_argument("--bump", choices=LIVELLI, help="forza il salto invece di calcolarlo")
    p.add_argument("--dry-run", action="store_true", help="mostra e basta")
    p.add_argument("--no-pr", action="store_true", help="non aprire la PR verso main")
    p.set_defaults(fn=cmd_prepare)

    c = sub.add_parser("check", help="controlla coerenza (e salto rispetto a --base)")
    c.add_argument("--base", help="commit o ramo di confronto, es. origin/main")
    c.set_defaults(fn=cmd_check)

    sub.add_parser("version", help="stampa la versione").set_defaults(fn=cmd_version)

    n = sub.add_parser("notes", help="note di una versione dal CHANGELOG")
    n.add_argument("versione")
    n.set_defaults(fn=cmd_notes)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except ErroreRilascio as e:
        print(f"Errore: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
