import io
import logging
import os
import tempfile
from datetime import date

from docx import Document

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "contracts", "contrato_adopcion.docx")
_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


_DATA_FONT = "Times New Roman"


def _apply_font(run):
    run.font.name = _DATA_FONT
    run.font.bold = True


def _set_run(para, run_idx: int, value: str):
    value = value.upper()
    runs = para.runs
    if run_idx < len(runs):
        runs[run_idx].text = value
        _apply_font(runs[run_idx])
    else:
        r = para.add_run(value)
        _apply_font(r)


def _append_run(para, value: str):
    r = para.add_run(value.upper())
    _apply_font(r)


def _fill_tasa(doc, tasa):
    tasa_str = f"{tasa:.2f}" if tasa is not None else "0.00"
    for p in doc.paragraphs:
        if "cantidad de" in p.text:
            for r in p.runs:
                if "cantidad de" in r.text:
                    r.text = r.text.replace("la cantidad de  €", f"la cantidad de {tasa_str} €")
                    _apply_font(r)
            break


def _fill_fecha(doc):
    hoy = date.today()
    nueva = f"  En Salamanca, a {hoy.day} de {_MESES[hoy.month - 1]} de {hoy.year}.          "
    for p in doc.paragraphs:
        if "En Salamanca" in p.text:
            for r in p.runs:
                if "En Salamanca" in r.text:
                    r.text = nueva
                    _apply_font(r)
            break


def _generar_docx(familia, perro) -> bytes:
    doc = Document(os.path.abspath(_TEMPLATE_PATH))
    t0 = doc.tables[0]  # datos familia
    t1 = doc.tables[1]  # datos perro

    # ── Tabla 0: datos de la familia ────────────────────────────────────────
    # Fila 0 (celda fusionada): NOMBRE Y APELLIDOS — run[1] es el valor
    _set_run(t0.rows[0].cells[0].paragraphs[0], 1, f"{familia.nombre} {familia.apellidos}")

    # Fila 1: DNI (1 run) | CORREO ELECTRÓNICO (run[1] es valor)
    _append_run(t0.rows[1].cells[0].paragraphs[0], familia.dni or "")
    _set_run(t0.rows[1].cells[1].paragraphs[0], 1, familia.email or "")

    # Fila 2 (celda fusionada): DIRECCIÓN — 1 run, añadir valor
    _append_run(t0.rows[2].cells[0].paragraphs[0], familia.direccion or "")

    # Fila 3: LOCALIDAD (run[1] es valor) | PROVINCIA (1 run)
    _set_run(t0.rows[3].cells[0].paragraphs[0], 1, familia.municipio or "")
    _append_run(t0.rows[3].cells[1].paragraphs[0], familia.provincia or "")

    # Fila 4: C.P (1 run) | TELÉFONO (1 run)
    _append_run(t0.rows[4].cells[0].paragraphs[0], familia.codigo_postal or "")
    _append_run(t0.rows[4].cells[1].paragraphs[0], familia.telefono or "")

    # ── Tabla 1: datos del perro ─────────────────────────────────────────────
    # Fila 0 (cols 0-1 fusionadas): NOMBRE — run[1] limpiar espacio, run[2] valor
    _set_run(t1.rows[0].cells[0].paragraphs[0], 1, "")
    _set_run(t1.rows[0].cells[0].paragraphs[0], 2, perro.nombre)

    # Fila 1 (cols 0-1 fusionadas): MICROCHIP — run[1] limpiar, run[2] valor
    _set_run(t1.rows[1].cells[0].paragraphs[0], 1, "")
    _set_run(t1.rows[1].cells[0].paragraphs[0], 2, perro.num_chip or "")

    # Fila 1 (cols 2-3 fusionadas): Nº PASAPORTE — run[2] limpiar espacio, run[3] valor
    _set_run(t1.rows[1].cells[2].paragraphs[0], 2, "")
    _set_run(t1.rows[1].cells[2].paragraphs[0], 3, perro.num_pasaporte or "")

    # Fila 2 col 0: RAZA — run[2] es valor (bold)
    _set_run(t1.rows[2].cells[0].paragraphs[0], 2, perro.raza.nombre if perro.raza else "")

    # Fila 2 col 1: SEXO — run[1] es valor
    _set_run(t1.rows[2].cells[1].paragraphs[0], 1, perro.sexo.value.upper() if perro.sexo else "")

    # Fila 2 (cols 2-3 fusionadas): F.NACIMIENTO — run[1] limpiar espacios, run[2] valor
    _set_run(t1.rows[2].cells[2].paragraphs[0], 1, "")
    fecha_str = perro.fecha_nacimiento.strftime("%d/%m/%Y") if perro.fecha_nacimiento else ""
    _set_run(t1.rows[2].cells[2].paragraphs[0], 2, fecha_str)

    # Fila 3 col 0: CAPA — run[1] es valor
    _set_run(t1.rows[3].cells[0].paragraphs[0], 1, perro.color or "")

    # Fila 3 col 1: TAMAÑO — run[1] es valor
    _set_run(t1.rows[3].cells[1].paragraphs[0], 1, perro.tamano or "")

    # Fila 3 (cols 2-3 fusionadas): ESTERILIZADO — run[1] es valor (reemplaza "PEND. ADOP")
    _set_run(t1.rows[3].cells[2].paragraphs[0], 1, "SÍ" if perro.esterilizado else "PEND. ADOP")

    # ── Párrafo 21: tasa adopción ────────────────────────────────────────────
    _fill_tasa(doc, perro.tasa)

    # ── Párrafo fecha firma ──────────────────────────────────────────────────
    _fill_fecha(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def generar_contrato_adopcion(familia, perro) -> tuple[bytes | None, bytes]:
    """Devuelve (pdf_bytes_o_None, docx_bytes)."""
    from app.utils.pdf_utils import docx_a_pdf

    docx_bytes = _generar_docx(familia, perro)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(docx_bytes)
        docx_path = tmp.name

    try:
        pdf_bytes = docx_a_pdf(docx_path)
    except Exception as e:
        logger.error("Error convirtiendo contrato adopción a PDF: %s", e)
        pdf_bytes = None
    finally:
        os.unlink(docx_path)

    return pdf_bytes, docx_bytes
