"""
NexoCambio · Genera los PDF de los entregables a partir de docs/fuentes/.

    docs/fuentes/*.md         → grupo_01/   (Parte 1)
    docs/fuentes/parte2/*.md  → entrega_2/  (Parte 2, segundo entregable)

Cada Markdown se envuelve en un HTML que lo renderiza en el navegador (marked para el
texto, Mermaid para los diagramas) y se imprime a PDF con Edge o Chrome en modo headless.

    python generador/generar_pdfs.py             # todos los documentos
    python generador/generar_pdfs.py informe     # solo el documento indicado

Opciones por documento (primera línea del .md):
    <!-- pagina: A3 landscape -->
"""
import html
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "docs" / "fuentes"
DESTINOS = [(FUENTES, RAIZ / "grupo_01"), (FUENTES / "parte2", RAIZ / "entrega_2")]
TEMPORAL = RAIZ / "docs" / "fuentes" / "_html"  # HTML intermedio (no se versiona)
NAVEGADORES = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
               Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
               Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")]

PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{titulo}</title>
<style>{css}
@page {{ size: {pagina}; margin: 16mm 15mm 16mm 15mm; }}</style>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
</head><body>
<main id="contenido"></main>
<script type="text/markdown" id="fuente">{markdown}</script>
<script>
  const md = document.getElementById('fuente').textContent;
  document.getElementById('contenido').innerHTML = marked.parse(md, {{ gfm: true }});
  document.querySelectorAll('code.language-mermaid').forEach(c => {{
    const d = document.createElement('div');
    d.className = 'mermaid';
    d.textContent = c.textContent;
    c.parentElement.replaceWith(d);
  }});
  mermaid.initialize({{ startOnLoad: false, theme: 'neutral', er: {{ useMaxWidth: true }},
                        flowchart: {{ useMaxWidth: true, htmlLabels: true }}, fontFamily: 'Segoe UI, Arial' }});
  mermaid.run();
</script>
</body></html>
"""


def navegador() -> Path:
    for n in NAVEGADORES:
        if n.exists():
            return n
    sys.exit("No se encontró Edge ni Chrome.")


def construir(md_path: Path, css: str, exe: Path, salida: Path):
    texto = md_path.read_text(encoding="utf-8")
    m = re.match(r"<!--\s*pagina:\s*(.+?)\s*-->", texto)
    pagina = m.group(1) if m else "A4"
    titulo = next((l[2:].strip() for l in texto.splitlines() if l.startswith("# ")), md_path.stem)
    # Dentro de <script type="text/markdown"> solo hay que evitar el cierre literal de la etiqueta.
    cuerpo = texto.replace("</script", "<\\/script")
    pagina_html = PLANTILLA.format(titulo=html.escape(titulo), css=css, pagina=pagina, markdown=cuerpo)
    TEMPORAL.mkdir(exist_ok=True)
    html_path = TEMPORAL / f"{md_path.stem}.html"
    html_path.write_text(pagina_html, encoding="utf-8")
    salida.mkdir(exist_ok=True)
    pdf = salida / f"{md_path.stem}.pdf"
    # Edge no avisa si no puede sobrescribir el PDF (por ejemplo, si está abierto en un visor):
    # se borra antes para detectarlo.
    try:
        pdf.unlink(missing_ok=True)
    except PermissionError:
        sys.exit(f"No se puede reemplazar {pdf.relative_to(RAIZ)}: ciérrelo en el visor de PDF y reintente.")
    subprocess.run([str(exe), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=20000", f"--print-to-pdf={pdf}", html_path.as_uri()],
                   check=True, capture_output=True)
    if not pdf.exists():
        sys.exit(f"Edge no generó {pdf.relative_to(RAIZ)}.")
    print(f"{pdf.relative_to(RAIZ)}  ({pdf.stat().st_size // 1024} KB)")


def main():
    css = (FUENTES / "estilos.css").read_text(encoding="utf-8")
    exe = navegador()
    pedidos = sys.argv[1:]
    for carpeta, salida in DESTINOS:
        for md in sorted(carpeta.glob("*.md")):
            if not pedidos or md.stem in pedidos:
                construir(md, css, exe, salida)


if __name__ == "__main__":
    main()
