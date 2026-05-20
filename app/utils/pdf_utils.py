import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def docx_a_pdf(docx_path: str) -> bytes | None:
    # Intenta con Word COM (Windows) — inicializa COM para contexto multi-hilo
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        word = None
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = os.path.join(tmpdir, "contrato.pdf")
                doc = word.Documents.Open(docx_path)
                doc.SaveAs(pdf_path, FileFormat=17)  # 17 = wdFormatPDF
                doc.Close(False)
                with open(pdf_path, "rb") as f:
                    return f.read()
        finally:
            if word:
                word.Quit()
            pythoncom.CoUninitialize()
    except Exception as e:
        logger.error("Word COM falló: %s: %s", type(e).__name__, e)

    # Fallback: LibreOffice (Linux/Render)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "/usr/bin/soffice",
                    "--headless",
                    "-env:UserInstallation=file:///tmp/libreoffice_profile",
                    "--convert-to", "pdf",
                    "--outdir", tmpdir,
                    docx_path,
                ],
                capture_output=True, timeout=60,
            )
            logger.warning("soffice returncode: %s", result.returncode)
            logger.warning("soffice stdout: %s", result.stdout.decode(errors="replace"))
            logger.warning("soffice stderr: %s", result.stderr.decode(errors="replace"))
            if result.returncode != 0:
                return None
            base = os.path.splitext(os.path.basename(docx_path))[0]
            pdf_path = os.path.join(tmpdir, base + ".pdf")
            with open(pdf_path, "rb") as f:
                return f.read()
    except FileNotFoundError:
        logger.warning("soffice no encontrado en el sistema")
        return None
