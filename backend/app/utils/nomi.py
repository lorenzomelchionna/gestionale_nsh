"""Quando due schede portano lo stesso nome.

Serve dove un numero di telefono, già dimostrato, non basta da solo a dire
che due schede sono la stessa persona: madre e figlia possono condividere il
fisso di casa. Il nome fa da secondo controllo — ma scritto da persone
diverse in momenti diversi, quindi va confrontato per quello che dice, non
per come è battuto: «D'Angelo», «d angelo» e «DANGELO» sono la stessa
persona, «Nicolò» e «Nicolo» pure.

Non prova a indovinare oltre: «Maria» e «Maria Rosaria» restano diversi. Un
collegamento mancato lo sistema il salone con «Unisci»; uno sbagliato
consegnerebbe a qualcuno gli appuntamenti di un'altra persona.
"""
import unicodedata


def _pulisci(testo: str) -> str:
    scomposto = unicodedata.normalize("NFKD", testo or "")
    senza_accenti = "".join(c for c in scomposto if not unicodedata.combining(c))
    return "".join(c for c in senza_accenti.casefold() if c.isalnum())


def chiave_nome(nome: str, cognome: str) -> str:
    """Nome e cognome ridotti a ciò che conta per dire «è lei»."""
    return f"{_pulisci(nome)}|{_pulisci(cognome)}"
