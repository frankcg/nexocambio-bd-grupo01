"""
Convierte los bloques ```mermaid de un Markdown en imágenes PNG (para el Word).

    python generador/word/diagramas_png.py docs/fuentes/informe.md

Cada diagrama se dibuja con Mermaid en Edge headless, se captura en alta resolución y se
recorta el borde blanco. Las imágenes quedan en generador/word/_img/<documento>_<n>.png.
"""
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI / "_img"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

PLANTILLA = """<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>html, body {{ margin: 0; background: #fff; }} #d {{ width: 1500px; padding: 20px; }}</style>
</head><body><div id="d" class="mermaid">{codigo}</div>
<script>mermaid.initialize({{ startOnLoad: true, theme: 'neutral', fontFamily: 'Segoe UI, Arial' }});</script>
</body></html>"""


def recortar(png: Path):
    img = Image.open(png).convert("RGB")
    fondo = Image.new("RGB", img.size, (255, 255, 255))
    caja = ImageChops.difference(img, fondo).getbbox()
    if caja:
        margen = 16
        img.crop((max(0, caja[0] - margen), max(0, caja[1] - margen),
                  min(img.width, caja[2] + margen), min(img.height, caja[3] + margen))).save(png)


def main():
    md = Path(sys.argv[1]).resolve()
    texto = md.read_text(encoding="utf-8")
    SALIDA.mkdir(exist_ok=True)
    for n, codigo in enumerate(re.findall(r"```mermaid\n(.*?)```", texto, re.S), 1):
        html = SALIDA / f"{md.stem}_{n}.html"
        png = SALIDA / f"{md.stem}_{n}.png"
        html.write_text(PLANTILLA.format(codigo=codigo), encoding="utf-8")
        subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=2", "--window-size=1540,1400",
                        "--virtual-time-budget=15000", f"--screenshot={png}", html.as_uri()],
                       check=True, capture_output=True)
        recortar(png)
        ancho, alto = Image.open(png).size
        print(f"{png.name}: {ancho}x{alto}")


if __name__ == "__main__":
    main()
