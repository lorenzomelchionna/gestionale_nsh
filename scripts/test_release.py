"""Test di `release.py`: il salto di versione, il CHANGELOG, i controlli.

Girano con `python3 -m pytest scripts` (in CI nel job «Versione»). Toccano
solo cartelle temporanee: nessun git, nessun file del repository.
"""
import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

import release as r


def c(oggetto, corpo=""):
    return r.Commit.da_messaggio(oggetto, corpo)


class TestSalto:
    @pytest.mark.parametrize("versione, livello, attesa", [
        ("1.0.0", "patch", "1.0.1"),
        ("1.0.9", "minor", "1.1.0"),
        ("1.4.2", "major", "2.0.0"),
    ])
    def test_alza(self, versione, livello, attesa):
        assert r.alza(versione, livello) == attesa

    @pytest.mark.parametrize("sbagliata", ["1.0", "v1.0.0", "1.0.0-beta", "uno"])
    def test_solo_semver(self, sbagliata):
        with pytest.raises(r.ErroreRilascio):
            r.analizza(sbagliata)

    def test_solo_correzioni_e_manutenzione_patch(self):
        assert r.livello_da_commit([c("fix: x"), c("docs: y"), c("chore: z")]) == "patch"

    def test_una_funzionalita_minor(self):
        assert r.livello_da_commit([c("fix: x"), c("feat(chat): y")]) == "minor"

    def test_rottura_col_punto_esclamativo_major(self):
        assert r.livello_da_commit([c("feat!: y"), c("fix: x")]) == "major"

    def test_rottura_nel_corpo_major(self):
        assert r.livello_da_commit([c("refactor: y", "BREAKING CHANGE: api diversa")]) == "major"

    def test_fuori_forma_conta_come_correzione(self):
        assert r.livello_da_commit([c("Aggiornato il README")]) == "patch"

    def test_il_commit_di_rilascio_non_conta(self):
        assert r.livello_da_commit([c("chore(release): v1.1.0")]) is None
        assert r.livello_da_commit([]) is None


class TestLaVersioneSale:
    @pytest.mark.parametrize("prima, dopo", [("0.1.0", "1.0.0"), ("1.0.0", "1.0.1"), ("1.9.9", "2.0.0")])
    def test_sale(self, prima, dopo):
        r.controlla_salto(prima, dopo)

    @pytest.mark.parametrize("prima, dopo", [("1.0.0", "1.0.0"), ("1.1.0", "1.0.9"), ("2.0.0", "1.9.9")])
    def test_uguale_o_piu_bassa_non_passa(self, prima, dopo):
        with pytest.raises(r.ErroreRilascio, match="non sale"):
            r.controlla_salto(prima, dopo)

    def test_confronto_numerico_non_testuale(self):
        # «1.10.0» viene dopo «1.9.0»: da stringhe sarebbe il contrario.
        r.controlla_salto("1.9.0", "1.10.0")


class TestChangelog:
    def test_raggruppa_e_tralascia_la_manutenzione(self):
        sezione = r.sezione_changelog("1.1.0", dt.date(2026, 9, 30), [
            c("feat(calendar): colori dei servizi"),
            c("fix: intestazioni allineate"),
            c("docs: TODO aggiornato"),
            c("test: casi nuovi"),
        ])
        assert sezione.startswith("## [1.1.0] — 2026-09-30")
        assert "### Novità\n\n- calendar: colori dei servizi" in sezione
        assert "### Correzioni\n\n- intestazioni allineate" in sezione
        assert "TODO" not in sezione and "casi nuovi" not in sezione

    def test_solo_manutenzione_lo_dice(self):
        sezione = r.sezione_changelog("1.0.1", dt.date(2026, 9, 30), [c("docs: x")])
        assert "Solo manutenzione" in sezione

    def test_la_voce_nuova_va_sopra(self, tmp_path):
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nIntro.\n\n## [1.0.0] — 2026-09-29\n\nPrima.\n")
        r.aggiungi_al_changelog("## [1.1.0] — 2026-09-30\n\nSeconda.\n", radice=tmp_path)
        testo = (tmp_path / "CHANGELOG.md").read_text()
        assert testo.index("## [1.1.0]") < testo.index("## [1.0.0]")
        assert testo.index("Intro.") < testo.index("## [1.1.0]")
        assert r.note_versione("1.1.0", testo).strip() == "Seconda."
        assert r.note_versione("1.0.0", testo).strip() == "Prima."

    def test_versione_senza_voce(self):
        with pytest.raises(r.ErroreRilascio):
            r.note_versione("9.9.9", "# Changelog\n\n## [1.0.0] — x\n\nA\n")


class TestFile:
    @pytest.fixture
    def copia(self, tmp_path):
        """Una copia dei tre file di versione veri, da modificare in pace."""
        for p in (r.FRONT_PKG, r.FRONT_LOCK, r.BACK_VERSION):
            (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(r.ROOT / p, tmp_path / p)
        return tmp_path

    def test_il_repository_e_coerente(self):
        r.versione_unica(r.leggi_versioni())

    def test_scrive_tutti_e_tre(self, copia):
        r.scrivi_versione("7.8.9", radice=copia)
        assert r.versione_unica(r.leggi_versioni(radice=copia)) == "7.8.9"
        lock = json.loads((copia / r.FRONT_LOCK).read_text())
        assert lock["packages"][""]["version"] == "7.8.9"

    def test_file_disallineati_bloccano(self, copia):
        pkg = copia / r.FRONT_PKG
        dati = json.loads(pkg.read_text())
        # 0.0.1 e non una versione plausibile: le versioni salgono e basta,
        # quindi questa non sarà mai quella vera. Con "1.2.3" il test è
        # passato finché il repository non è arrivato proprio alla 1.2.3.
        dati["version"] = "0.0.1"
        pkg.write_text(json.dumps(dati))
        with pytest.raises(r.ErroreRilascio, match="non coincidono"):
            r.versione_unica(r.leggi_versioni(radice=copia))
