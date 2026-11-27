"""Gli appuntamenti in un file Excel, da tenere sul computer del salone.

Nasce dal 2026-11-27: senza internet in salone il gestionale era vuoto (i
dati erano al sicuro sul server, ma irraggiungibili) e nessuno sapeva chi
stava arrivando. Un file scaricato prima si apre anche offline.

Dentro c'è quello che serve a lavorare una giornata senza il gestionale:
chi, quando, con chi, cosa, e il telefono per richiamare. Gli appuntamenti
annullati o rifiutati restano fuori: in un'agenda di emergenza sono rumore.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models.appointment import AppointmentStatus
from app.utils.tempo import ora_salone

STATI = {
    AppointmentStatus.pending: "Da confermare",
    AppointmentStatus.confirmed: "Confermato",
    AppointmentStatus.rescheduled: "Proposto altro orario",
    AppointmentStatus.completed: "Fatto",
    AppointmentStatus.cancelled: "Annullato",
    AppointmentStatus.rejected: "Rifiutato",
}
ESCLUSI = (AppointmentStatus.cancelled, AppointmentStatus.rejected)
GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")

COLONNE = (
    ("Data", 12), ("Giorno", 7), ("Inizio", 8), ("Fine", 8),
    ("Collaboratore", 20), ("Cliente", 26), ("Telefono", 17),
    ("Servizi", 36), ("Stato", 20), ("Note", 40),
)


def foglio_appuntamenti(appuntamenti, dal: date, al: date) -> bytes:
    """`appuntamenti` già ordinati per inizio, con cliente, collaboratore e
    servizi caricati."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Appuntamenti"

    ws.append([nome for nome, _ in COLONNE])
    for i, (_, larghezza) in enumerate(COLONNE, start=1):
        cella = ws.cell(row=1, column=i)
        cella.font = Font(bold=True, color="FFFFFF")
        cella.fill = PatternFill("solid", fgColor="2B2622")
        ws.column_dimensions[get_column_letter(i)].width = larghezza

    for a in appuntamenti:
        inizio, fine = ora_salone(a.start_time), ora_salone(a.end_time)
        cliente = a.client
        collaboratore = a.collaborator
        ws.append([
            inizio.date(),
            GIORNI[inizio.weekday()],
            inizio.strftime("%H:%M"),
            fine.strftime("%H:%M"),
            f"{collaboratore.first_name} {collaboratore.last_name}".strip() if collaboratore else "",
            f"{cliente.first_name} {cliente.last_name}".strip() if cliente else "",
            (cliente.phone or "") if cliente else "",
            " + ".join(s.service.name for s in a.appointment_services if s.service is not None),
            STATI.get(a.status, str(a.status)),
            a.notes or "",
        ])
        ws.cell(row=ws.max_row, column=1).number_format = "DD/MM/YYYY"
        ws.cell(row=ws.max_row, column=10).alignment = Alignment(wrap_text=True, vertical="top")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    # Stampabile su A4 orizzontale, una pagina in larghezza.
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"
    ws.oddHeader.center.text = f"New Style Hair — appuntamenti dal {dal:%d/%m/%Y} al {al:%d/%m/%Y}"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
