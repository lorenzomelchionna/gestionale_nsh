"""Cosa i log devono contenere, e soprattutto cosa non devono contenere mai.

Un registro degli accessi è di per sé un archivio di dati personali: se è
scritto male raddoppia il problema invece di risolverlo. Metà di questo file
serve a impedire che qualcuno, un giorno, aggiunga la riga comoda che scrive
la password o il token accanto all'indirizzo a cui appartengono.

L'altra metà pinna la sola cosa per cui i log esistono davvero: dopo un furto
di credenziali bisogna poter dire **chi** ha aperto **cosa**. Se la riga del
registro non porta l'attore, non risponde a quella domanda, e allora è un
elenco di URL.
"""
import json
import logging

import pytest

from app.audit import RegistroAccessi
from app.logging_config import (
    FiltroSegreti, FormatoJson, SOSTITUTO, maschera_email, maschera_telefono,
)
from tests.conftest import ADMIN_PASSWORD, auth

pytestmark = pytest.mark.asyncio


def righe(caplog) -> list[logging.LogRecord]:
    return list(caplog.records)


def per_evento(caplog, nome: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "evento", None) == nome]


def accessi(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "nsh.accessi"]


def come_json(record: logging.LogRecord) -> dict:
    """Passa il record per la stessa catena della produzione: prima il filtro
    che toglie i segreti, poi il formatter JSON. Controllare il record grezzo
    proverebbe qualcosa su un oggetto che in produzione non esiste."""
    FiltroSegreti().filter(record)
    return json.loads(FormatoJson().format(record))


class TestQuelloCheNonDeveUscire:
    async def test_la_password_non_finisce_nei_log(
        self, client, caplog, client_account
    ):
        """Il test che vale tutto il file. Una password in chiaro nei log è
        una violazione in sé, e i log sono il posto dove finisce copiata per
        sbaglio più spesso che altrove."""
        with caplog.at_level(logging.DEBUG):
            await client.post(
                "/api/auth/login",
                json={"email": client_account.email, "password": "SbagliataDavvero123"},
            )

        tutto = " ".join(come_json(r).__str__() for r in righe(caplog))
        assert "SbagliataDavvero123" not in tutto

    async def test_il_token_non_finisce_nei_log(self, client, caplog, admin_tokens):
        with caplog.at_level(logging.DEBUG):
            await client.get("/api/admin/clients", headers=auth(admin_tokens))

        tutto = " ".join(str(come_json(r)) for r in righe(caplog))
        assert admin_tokens["access_token"] not in tutto

    async def test_un_token_scritto_a_mano_viene_tolto_lo_stesso(self, caplog):
        """La rete di sicurezza: anche se qualcuno mette un JWT dentro il testo
        del messaggio invece che in un campo, il filtro lo toglie."""
        finto = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0."
                 "abcdefghijklmnopqrstuvwxyz0123456789")
        with caplog.at_level(logging.DEBUG):
            logging.getLogger("nsh.test").info("token=%s", finto)

        prodotto = come_json(caplog.records[-1])
        assert finto not in str(prodotto)
        assert SOSTITUTO in str(prodotto)

    async def test_un_header_authorization_viene_tolto(self, caplog):
        with caplog.at_level(logging.DEBUG):
            logging.getLogger("nsh.test").info("chiamata con Bearer abc123DEF456ghi")

        assert "abc123DEF456ghi" not in str(come_json(caplog.records[-1]))

    @pytest.mark.parametrize(
        "campo", ["password", "new_password", "reset_token", "password_hash",
                  "api_key", "authorization", "code", "codice_verifica"],
    )
    async def test_i_campi_che_sanno_di_segreto_sono_oscurati(self, caplog, campo):
        """Per nome, non per valore: è l'unica regola che regge anche quando
        chi scrive la chiamata non ha letto `logging_config.py`."""
        with caplog.at_level(logging.DEBUG):
            logging.getLogger("nsh.test").info("prova", extra={campo: "valore-vero"})

        prodotto = come_json(caplog.records[-1])
        assert prodotto[campo] == SOSTITUTO
        assert "valore-vero" not in str(prodotto)

    async def test_la_query_string_non_entra_nel_registro(self, client, caplog):
        """Il token di reset viaggia in query string sul frontend, e le
        ricerche dell'agenda ci passano i nomi delle clienti."""
        with caplog.at_level(logging.INFO):
            await client.get("/api/public/services?cerca=Rossi&token=abc")

        for record in accessi(caplog):
            assert "?" not in record.percorso
            assert "Rossi" not in record.percorso


class TestMascherature:
    @pytest.mark.parametrize(
        "indirizzo,atteso",
        [
            ("mario.rossi@gmail.com", "m***i@gmail.com"),
            ("ab@x.it", "a***@x.it"),
            ("a@x.it", "a***@x.it"),
        ],
    )
    async def test_email(self, indirizzo, atteso):
        assert maschera_email(indirizzo) == atteso

    async def test_email_senza_chiocciola_non_esce_affatto(self):
        assert maschera_email("non-un-indirizzo") == SOSTITUTO
        assert maschera_email(None) == SOSTITUTO

    async def test_il_dominio_resta_leggibile(self):
        """Serve: distinguere una raffica da `@gmail.com` da una che arriva
        tutta da un dominio mai visto è metà della diagnosi."""
        assert maschera_email("chiunque@dominio-strano.ru").endswith("@dominio-strano.ru")

    async def test_telefono(self):
        assert maschera_telefono("+393331234567") == "+39***4567"
        assert maschera_telefono("333") == SOSTITUTO
        assert maschera_telefono(None) == SOSTITUTO


class TestIlRegistroDegliAccessi:
    async def test_ogni_richiesta_lascia_una_riga(self, client, caplog, admin_tokens):
        with caplog.at_level(logging.INFO):
            await client.get("/api/admin/clients", headers=auth(admin_tokens))

        riga = next(r for r in accessi(caplog) if r.percorso == "/api/admin/clients")
        assert riga.metodo == "GET"
        assert riga.stato == 200
        assert isinstance(riga.durata_ms, float)

    async def test_la_riga_dice_chi_era(self, client, caplog, admin_tokens, admin_user):
        """Il cuore di tutto.

        Senza questo campo il registro dice che qualcuno ha aperto l'elenco
        clienti, non *chi*: cioè non risponde alla domanda che si fa dopo un
        furto di credenziali, che è l'unica ragione per cui il registro esiste.

        È anche il test che ha imposto di scrivere `RegistroAccessi` come
        middleware ASGI: con `BaseHTTPMiddleware` l'applicazione gira in un
        altro task, la `ContextVar` impostata dalle dipendenze non torna
        indietro, e questo campo resta `anonimo` per sempre.
        """
        with caplog.at_level(logging.INFO):
            await client.get("/api/admin/clients", headers=auth(admin_tokens))

        riga = next(r for r in accessi(caplog) if r.percorso == "/api/admin/clients")
        assert riga.attore == f"admin:{admin_user.id}", (
            "la riga non sa chi ha fatto la richiesta"
        )

    async def test_un_cliente_del_portale_e_riconoscibile(
        self, client, caplog, client_tokens, client_account
    ):
        with caplog.at_level(logging.INFO):
            await client.get("/api/public/appointments",
                             headers=auth(client_tokens))

        righe_portale = [r for r in accessi(caplog)
                         if r.percorso == "/api/public/appointments"]
        assert righe_portale
        assert righe_portale[-1].attore == f"client:{client_account.id}"

    async def test_senza_token_l_attore_e_anonimo(self, client, caplog):
        with caplog.at_level(logging.INFO):
            await client.get("/api/public/services")

        assert accessi(caplog)[-1].attore == "anonimo"

    async def test_l_attore_non_resta_appiccicato_alla_richiesta_dopo(
        self, client, caplog, admin_tokens
    ):
        """Le `ContextVar` vanno riportate indietro: se non lo si fa, la
        richiesta successiva servita dallo stesso worker eredita l'attore
        della precedente — e il registro attribuisce a una persona quello che
        ha fatto un'altra, che è peggio di non avere il registro."""
        await client.get("/api/admin/clients", headers=auth(admin_tokens))

        with caplog.at_level(logging.INFO):
            await client.get("/api/public/services")

        assert accessi(caplog)[-1].attore == "anonimo"

    async def test_ogni_richiesta_ha_un_identificativo_diverso(
        self, client, caplog, admin_tokens
    ):
        with caplog.at_level(logging.INFO):
            for _ in range(3):
                await client.get("/api/admin/clients", headers=auth(admin_tokens))

        visti = {r.richiesta for r in accessi(caplog)}
        assert len(visti) == 3
        assert "-" not in visti

    async def test_l_identificativo_torna_al_chiamante(self, client, admin_tokens):
        """Serve per il supporto: se una cliente segnala un problema, l'unico
        modo di ritrovare *quella* richiesta nei log è un identificativo che
        lei possa leggere."""
        resp = await client.get("/api/admin/clients", headers=auth(admin_tokens))
        assert resp.headers.get("x-request-id")

    async def test_un_identificativo_malevolo_non_spezza_la_risposta(self, client):
        """L'id arriva da un header, e viene rimandato indietro in un header:
        senza ripulirlo, un `\\r\\n` in mezzo permetterebbe di iniettare
        intestazioni arbitrarie nella risposta."""
        resp = await client.get(
            "/api/public/services",
            headers={"X-Request-ID": "abc\r\nX-Iniettato: si"},
        )
        assert "x-iniettato" not in {k.lower() for k in resp.headers}
        assert "\r" not in resp.headers.get("x-request-id", "")
        assert "\n" not in resp.headers.get("x-request-id", "")

    async def test_il_controllo_di_salute_non_riempie_il_registro(self, client, caplog):
        """`/health` arriva ogni pochi secondi per sempre: un registro fatto
        per il 99% di quello non è più leggibile, cioè non serve più."""
        with caplog.at_level(logging.INFO):
            await client.get("/health")

        assert accessi(caplog) == []


class TestGliEventiDiSicurezza:
    async def test_un_login_riuscito_e_scritto(self, client, caplog, admin_user):
        with caplog.at_level(logging.INFO):
            await client.post(
                "/api/auth/login",
                json={"email": admin_user.email, "password": ADMIN_PASSWORD},
            )

        eventi = per_evento(caplog, "login_riuscito")
        assert eventi
        assert eventi[-1].id_account == admin_user.id
        assert eventi[-1].email == maschera_email(admin_user.email)

    async def test_un_login_fallito_e_scritto_come_warning(
        self, client, caplog, admin_user
    ):
        """`WARNING` e non `INFO`: uno non dice niente, trenta di fila sono
        l'unico segnale che il salone ha di essere sotto attacco — e a `INFO`
        starebbero in mezzo a tutto il traffico normale."""
        with caplog.at_level(logging.INFO):
            await client.post(
                "/api/auth/login",
                json={"email": admin_user.email, "password": "non-e-questa"},
            )

        eventi = per_evento(caplog, "login_fallito")
        assert eventi
        assert eventi[-1].levelno == logging.WARNING
        assert eventi[-1].motivo == "password_errata"

    async def test_il_log_distingue_password_errata_da_account_inesistente(
        self, client, caplog
    ):
        """Distinzione che l'API non fa di proposito — e che il log deve fare.

        «Cento tentativi su un indirizzo che esiste» è qualcuno che sta
        forzando un account preciso; «cento indirizzi che non esistono» è
        qualcuno che sta provando una lista comprata. Sono due fatti diversi
        e chiedono due risposte diverse.
        """
        with caplog.at_level(logging.INFO):
            resp = await client.post(
                "/api/auth/login",
                json={"email": "nessuno@da-nessuna-parte.it", "password": "qualunque"},
            )

        assert resp.status_code == 401
        assert per_evento(caplog, "login_fallito")[-1].motivo == "account_inesistente"

    async def test_la_risposta_pero_resta_indistinguibile(self, client, admin_user):
        """Il contrario del test sopra: la distinzione sta nei log e **non**
        deve uscire dall'API, o diventa un modo per scoprire chi ha un
        account."""
        sconosciuto = await client.post(
            "/api/auth/login",
            json={"email": "nessuno@da-nessuna-parte.it", "password": "x"},
        )
        noto = await client.post(
            "/api/auth/login", json={"email": admin_user.email, "password": "x"},
        )
        assert sconosciuto.status_code == noto.status_code == 401
        assert sconosciuto.json() == noto.json()

    async def test_un_token_cliente_su_una_rotta_staff_e_un_warning(
        self, client, caplog, client_tokens
    ):
        """La forma esatta della escalation cliente→admin già trovata in
        questo codice. Se ricompare nei log, non è rumore."""
        with caplog.at_level(logging.INFO):
            await client.get("/api/admin/clients", headers=auth(client_tokens))

        eventi = per_evento(caplog, "token_rifiutato")
        assert eventi
        assert eventi[-1].motivo == "token_cliente_su_rotta_staff"
        assert eventi[-1].levelno == logging.WARNING

    async def test_un_collaboratore_su_una_rotta_admin_e_scritto(
        self, client, caplog, collab_tokens
    ):
        with caplog.at_level(logging.INFO):
            await client.post(
                "/api/admin/clients",
                headers=auth(collab_tokens),
                json={"first_name": "X", "last_name": "Y", "phone": "3330000000"},
            )

        eventi = per_evento(caplog, "permesso_negato")
        assert eventi
        assert eventi[-1].motivo == "serve_admin"
        assert eventi[-1].percorso == "/api/admin/clients"

    async def test_il_codice_di_verifica_non_finisce_nel_log_del_fallimento(
        self, client, caplog, db
    ):
        """Il codice tentato è una credenziale: scritto accanto all'indirizzo
        a cui appartiene, il log diventa il posto da cui rubarlo."""
        with caplog.at_level(logging.DEBUG):
            await client.post(
                "/api/public/auth/verify-email",
                json={"email": "qualcuno@example.com", "code": "424242"},
            )

        assert "424242" not in " ".join(str(come_json(r)) for r in righe(caplog))


class TestGliErrori:
    async def test_un_500_lascia_una_traccia(
        self, client, caplog, monkeypatch, booking_config, collaborator, service
    ):
        """Prima non ne lasciava nessuna: il gestore globale in `main.py`
        inghiottiva l'eccezione e rispondeva 500 senza scrivere niente. Con
        `SENTRY_DSN` non configurato — che è il caso oggi — un guasto in
        produzione spariva del tutto, e restava solo una cliente che dice «non
        funziona» e nessun modo di sapere cosa fosse."""
        from datetime import date, timedelta

        from app.api.public import booking

        def esplode(*a, **kw):
            raise RuntimeError("guasto finto per il test")

        monkeypatch.setattr(booking, "get_available_slots", esplode)

        with caplog.at_level(logging.INFO):
            try:
                await client.get(
                    "/api/public/availability",
                    params={
                        "service_id": service.id,
                        "collaborator_id": collaborator.id,
                        "target_date": (date.today() + timedelta(days=2)).isoformat(),
                    },
                )
            except RuntimeError:
                # Il transport di test rilancia l'eccezione invece di
                # trasformarla in 500; a noi interessa che la riga sia stata
                # scritta comunque, cioè prima che la richiesta morisse.
                pass

        esplosi = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert esplosi, "un errore non gestito non ha lasciato niente nei log"
        assert any(r.exc_info for r in esplosi), "manca lo stack: resta «non funziona»"
        assert any("guasto finto" in str(r.exc_info[1]) for r in esplosi if r.exc_info)


class TestIlFormato:
    async def test_una_riga_e_un_json_valido(self, caplog):
        with caplog.at_level(logging.INFO):
            logging.getLogger("nsh.test").info(
                "prova", extra={"id_cliente": 7, "percorso": "/x"}
            )

        prodotto = come_json(caplog.records[-1])
        assert prodotto["message"] == "prova"
        assert prodotto["level"] == "info"
        assert prodotto["id_cliente"] == 7
        assert "ts" in prodotto and "richiesta" in prodotto and "attore" in prodotto

    @pytest.mark.parametrize(
        "livello,atteso",
        [
            (logging.DEBUG, "debug"),
            (logging.INFO, "info"),
            (logging.WARNING, "warn"),
            (logging.ERROR, "error"),
            (logging.CRITICAL, "error"),
        ],
    )
    async def test_il_livello_sta_nella_chiave_che_railway_legge(
        self, caplog, livello, atteso
    ):
        """`level` e `message` sono le due chiavi che Railway *interpreta*;
        tutte le altre le indicizza soltanto.

        Trovato in produzione, non a tavolino: con `livello` al posto di
        `level` ogni riga risultava `info` — è il default per stdout — e
        `@level:warn` non trovava niente. I login falliti erano `WARNING` nel
        codice e indistinguibili dal traffico normale nel posto in cui quei
        log si leggono, il che annulla l'unico motivo per cui sono `WARNING`.
        """
        with caplog.at_level(logging.DEBUG):
            logging.getLogger("nsh.test").log(livello, "prova")

        prodotto = come_json(caplog.records[-1])
        assert prodotto["level"] == atteso
        assert prodotto["level"] in ("debug", "info", "warn", "error"), (
            "Railway riconosce solo questi quattro"
        )
        assert "livello" not in prodotto

    async def test_un_valore_non_serializzabile_non_fa_esplodere_il_log(self, caplog):
        """Un `Decimal` o una `date` finiti in un campo capitano, e un log che
        solleva è peggio di un log impreciso: farebbe fallire la richiesta che
        stava solo descrivendo."""
        from datetime import date
        from decimal import Decimal

        with caplog.at_level(logging.INFO):
            logging.getLogger("nsh.test").info(
                "prova", extra={"importo": Decimal("12.50"), "giorno": date(2026, 8, 5)}
            )

        prodotto = come_json(caplog.records[-1])
        assert prodotto["importo"] == "12.50"
        assert prodotto["giorno"] == "2026-08-05"

    async def test_il_middleware_non_e_quello_che_perde_il_contesto(self):
        """Guardia esplicita contro la regressione più probabile di questo
        file: qualcuno riscrive `RegistroAccessi` con `BaseHTTPMiddleware`
        perché è più corto, e l'attore torna `anonimo` senza che nessun altro
        test lo noti subito."""
        from starlette.middleware.base import BaseHTTPMiddleware

        assert not issubclass(RegistroAccessi, BaseHTTPMiddleware)
