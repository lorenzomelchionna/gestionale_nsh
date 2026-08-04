"""
Fuori da sviluppo, l'applicazione si rifiuta di partire su segreti pubblicati.

Questo repository è pubblico. `SECRET_KEY = "changeme"` non è una chiave debole:
è una chiave che conoscono tutti, e firma i token di admin, collaboratori e
clienti. Chi la conosce si emette da solo un token amministratore.

Il modo in cui si arriva lì non è un attacco, è una distrazione: una variabile
persa ricreando un servizio, un ambiente nuovo, un rename sbagliato. Il deploy
è automatico e l'healthcheck passerebbe lo stesso, quindi nessuno se ne
accorgerebbe. L'unica difesa che funziona in quel momento è non avviarsi.
"""
import pytest
from pydantic import ValidationError

from app.config import MIN_SECRET_KEY_LENGTH, Settings

CHIAVE_VERA = "a" * MIN_SECRET_KEY_LENGTH


def _settings(**kw):
    """Costruisce Settings ignorando .env e ambiente, così il test misura le
    regole e non la macchina su cui gira."""
    base = {
        "_env_file": None,
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "SECRET_KEY": CHIAVE_VERA,
        "APP_ENV": "production",
    }
    base.update(kw)
    return Settings(**base)


class TestInProduzione:
    @pytest.mark.parametrize("pubblicata", ["changeme", "change_me_in_production", "secret", "test"])
    def test_una_chiave_pubblicata_impedisce_l_avvio(self, pubblicata):
        with pytest.raises(ValidationError) as e:
            _settings(SECRET_KEY=pubblicata)
        assert "SECRET_KEY" in str(e.value)

    def test_una_chiave_troppo_corta_impedisce_l_avvio(self):
        with pytest.raises(ValidationError) as e:
            _settings(SECRET_KEY="x" * (MIN_SECRET_KEY_LENGTH - 1))
        assert "minimo" in str(e.value)

    def test_una_chiave_vera_avvia(self):
        assert _settings().SECRET_KEY == CHIAVE_VERA

    def test_vale_per_qualunque_ambiente_che_non_sia_development(self):
        """Uno staging con la chiave di default è esposto quanto la produzione."""
        with pytest.raises(ValidationError):
            _settings(APP_ENV="staging", SECRET_KEY="changeme")


class TestInSviluppo:
    def test_la_chiave_di_default_resta_usabile_in_locale(self):
        """`python seed.py` su un portatile senza .env deve continuare a girare:
        il guardrail protegge la produzione, non intralcia lo sviluppo."""
        s = _settings(APP_ENV="development", SECRET_KEY="changeme")
        assert s.SECRET_KEY == "changeme"
