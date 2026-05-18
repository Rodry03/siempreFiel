import io
import os
from datetime import date

import fitz  # PyMuPDF

_MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "contrato_adopcion.pdf")


def _white(page, x0, y0, x1, y1):
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(1, 1, 1), fill=(1, 1, 1), width=0)


def _txt(page, x, y, text, fontsize=8.5):
    if not text:
        return
    page.insert_text((x, y), text, fontname="helv", fontsize=fontsize, color=(0, 0, 0))


def _txt_fit(page, x0, y, x1, text, max_fontsize=8.5):
    """Inserta texto entre x0 y x1, reduciendo el tamaño de fuente si es necesario."""
    if not text:
        return
    available = x1 - x0
    fs = max_fontsize
    length = fitz.get_text_length(text, fontname="helv", fontsize=fs)
    if length > available:
        fs = fs * available / length
    page.insert_text((x0, y), text, fontname="helv", fontsize=fs, color=(0, 0, 0))


def generar_contrato_adopcion(familia, perro) -> bytes:
    doc = fitz.open(os.path.abspath(_TEMPLATE_PATH))
    p1 = doc[0]
    p4 = doc[3]

    # ── Tabla persona (página 1) ──────────────────────────────────────────
    _txt(p1, 194, 338, f"{familia.nombre} {familia.apellidos}")
    _txt(p1, 97,  357, familia.dni or "")
    _txt(p1, 400, 357, familia.email or "")
    _txt(p1, 137, 375, familia.direccion or "")
    _txt(p1, 140, 396, familia.municipio or "")
    _txt(p1, 337, 396, familia.provincia or "")
    _txt(p1, 95,  415, familia.codigo_postal or "")
    _txt(p1, 335, 415, familia.telefono or "")

    # ── Tabla perro (página 1) ────────────────────────────────────────────
    _txt(p1, 121, 657, perro.nombre)
    _txt(p1, 132, 680, perro.num_chip or "")
    _txt(p1, 435, 680, perro.num_pasaporte or "")
    _txt(p1, 106, 704, perro.raza.nombre if perro.raza else "")
    _txt(p1, 250, 703, perro.sexo.value.upper() if perro.sexo else "")
    if perro.fecha_nacimiento:
        _txt(p1, 436, 704, perro.fecha_nacimiento.strftime("%d/%m/%Y"))
    _txt(p1, 105, 727, perro.color or "")
    _txt(p1, 265, 727, perro.tamano or "")

    # Esterilizado: la plantilla ya trae "PEND. ADOP"; si está esterilizado lo tapamos
    if perro.esterilizado:
        _white(p1, 436, 717, 493, 730)
        _txt(p1, 437, 727, "SÍ")

    # ── Tasa adopción — cláusula 21 (página 4) ───────────────────────────
    # Línea original: "...la cantidad de € para costear parte"
    # Tapamos desde "de" hasta el final de la línea y reescribimos todo con font dinámico
    tasa_str = f"{perro.tasa:.2f}" if perro.tasa is not None else "0.00"
    texto_clausula = f"de {tasa_str} € para costear parte"
    _white(p4, 408, 259, 526, 276)
    _txt_fit(p4, 410, 272, 524, texto_clausula)

    # ── Fecha (página 4) ─────────────────────────────────────────────────
    hoy = date.today()
    fecha_str = f"{hoy.day} de {_MESES_ES[hoy.month]} de {hoy.year}"
    # Tapamos "29  de Abril de 2026." y escribimos la fecha actual
    _white(p4, 428, 666, 524, 682)
    _txt(p4, 429, 679, fecha_str, fontsize=9)

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()
