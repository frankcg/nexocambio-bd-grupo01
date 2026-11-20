// NexoCambio · Genera demo/guion_demo.docx a partir de demo/guion_demo.md.
// Uso (desde la raíz del proyecto): node generador/word/guion_word.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType,
  ShadingType, BorderStyle, AlignmentType, Header, Footer, PageNumber, LevelFormat, HeadingLevel,
  TabStopType,
} = require("docx");

const RAIZ = path.resolve(__dirname, "..", "..");
const FUENTE = path.join(RAIZ, "demo", "guion_demo.md");
const SALIDA = path.join(RAIZ, "demo", "guion_demo.docx");
const LOGO = path.join(RAIZ, "docs", "fuentes", "recursos", "logo_utec_posgrado.png");

const FONT = "Arial", MONO = "Consolas";
const ACENTO = "0097AD", TINTA = "232627", GRIS = "5B6467", FONDO = "EEF2F3", FONDO_DECIR = "E6F5F7";
const ANCHO = 9638; // A4 con márgenes de 2 cm

// ------------------------------------------------------------------ texto en línea (**negrita**, `código`)
function runs(texto, base = {}) {
  const partes = texto.split(/(\*\*[^*]+\*\*|`[^`]+`)/).filter(Boolean);
  return partes.map((p) => {
    if (p.startsWith("**")) return new TextRun({ ...base, text: p.slice(2, -2), bold: true });
    if (p.startsWith("`")) return new TextRun({ ...base, text: p.slice(1, -1), font: MONO, size: (base.size || 22) - 2 });
    return new TextRun({ ...base, text: p });
  });
}

// ------------------------------------------------------------------ lectura del Markdown
const lineas = fs.readFileSync(FUENTE, "utf8").replace(/\r/g, "").split("\n");
const doc = { titulo: "", intro: [], secciones: [] };
let actual = null, enCodigo = false, codigo = [], cita = null;

function cerrarCita() { if (cita) { actual.items.push({ tipo: "decir", texto: cita.join(" ") }); cita = null; } }

for (const l of lineas) {
  if (enCodigo) {
    if (l.startsWith("```")) { actual.items.push({ tipo: "codigo", texto: codigo.join("\n") }); enCodigo = false; codigo = []; }
    else codigo.push(l);
    continue;
  }
  if (l.startsWith("```")) { cerrarCita(); enCodigo = true; continue; }
  if (l.startsWith("# ")) { doc.titulo = l.slice(2).trim(); continue; }
  if (l.startsWith("## ")) {
    cerrarCita();
    actual = { titulo: l.slice(3).trim(), items: [] };
    doc.secciones.push(actual);
    continue;
  }
  if (l.trim() === "---") { cerrarCita(); continue; }
  if (!actual) { if (l.trim()) doc.intro.push(l.trim()); else doc.intro.push(""); continue; }
  if (l.startsWith(">")) { const t = l.replace(/^>\s?/, "").trim(); (cita = cita || []).push(t); continue; }
  cerrarCita();
  if (!l.trim()) continue;
  if (l.startsWith("|")) {
    const celdas = l.split("|").slice(1, -1).map((c) => c.trim());
    if (celdas.every((c) => /^-+$/.test(c))) continue;
    const ult = actual.items[actual.items.length - 1];
    if (ult && ult.tipo === "tabla") ult.filas.push(celdas); else actual.items.push({ tipo: "tabla", filas: [celdas] });
    continue;
  }
  if (l.startsWith("- ")) { actual.items.push({ tipo: "lista", texto: l.slice(2).trim() }); continue; }
  if (/^\[.*\]$/.test(l.trim())) { actual.items.push({ tipo: "pantalla", texto: l.trim().slice(1, -1) }); continue; }
  actual.items.push({ tipo: "texto", texto: l.trim() });
}
cerrarCita();

// Párrafos de la introducción (unir líneas consecutivas)
const intro = [];
let buf = [];
for (const l of [...doc.intro, ""]) { if (l) buf.push(l); else if (buf.length) { intro.push(buf.join(" ")); buf = []; } }

const guion = doc.secciones.filter((s) => /^\d+:\d\d/.test(s.titulo));
const anexos = doc.secciones.filter((s) => !/^\d+:\d\d/.test(s.titulo));

// ------------------------------------------------------------------ bloques de Word
const borde = (color) => ({ style: BorderStyle.SINGLE, size: 4, color });
const sinBorde = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };

function celda(contenido, ancho, opciones = {}) {
  return new TableCell({
    width: { size: ancho, type: WidthType.DXA },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    shading: opciones.fondo ? { type: ShadingType.CLEAR, color: "auto", fill: opciones.fondo } : undefined,
    children: (Array.isArray(contenido) ? contenido : [contenido]).map((t) =>
      t instanceof Paragraph ? t : new Paragraph({ children: runs(t, { size: 20, bold: opciones.negrita, color: opciones.color }) })),
  });
}

function tabla(filas, anchos) {
  return new Table({
    width: { size: ANCHO, type: WidthType.DXA },
    columnWidths: anchos,
    borders: { top: borde("CFD6D8"), bottom: borde("CFD6D8"), left: borde("CFD6D8"), right: borde("CFD6D8"),
               insideHorizontal: borde("CFD6D8"), insideVertical: borde("CFD6D8") },
    rows: filas.map((f, i) => new TableRow({
      tableHeader: i === 0,
      cantSplit: true,
      children: f.map((c, j) => celda(c, anchos[j], i === 0 ? { fondo: TINTA, negrita: true, color: "FFFFFF" } : {})),
    })),
  });
}

function etiqueta(texto, color) {
  return new TextRun({ text: texto + "   ", bold: true, size: 16, color, characterSpacing: 20 });
}

function bloque(item) {
  if (item.tipo === "pantalla") {
    return [new Paragraph({
      spacing: { before: 100, after: 100 },
      shading: { type: ShadingType.CLEAR, color: "auto", fill: FONDO },
      border: { left: { style: BorderStyle.SINGLE, size: 18, color: GRIS, space: 8 } },
      indent: { left: 160 },
      children: [etiqueta("EN PANTALLA", GRIS), ...runs(item.texto, { size: 20, italics: true, color: GRIS })],
    })];
  }
  if (item.tipo === "codigo") {
    return item.texto.split("\n").map((l, i, a) => new Paragraph({
      spacing: { before: i === 0 ? 80 : 0, after: i === a.length - 1 ? 120 : 0 },
      shading: { type: ShadingType.CLEAR, color: "auto", fill: "F4F4F4" },
      indent: { left: 160 },
      children: [new TextRun({ text: l, font: MONO, size: 17, color: TINTA })],
    }));
  }
  if (item.tipo === "decir") {
    const texto = item.texto.replace(/^"|"$/g, "");
    return [new Paragraph({
      spacing: { before: 120, after: 160, line: 300 },
      shading: { type: ShadingType.CLEAR, color: "auto", fill: FONDO_DECIR },
      border: { left: { style: BorderStyle.SINGLE, size: 24, color: ACENTO, space: 8 } },
      indent: { left: 160 },
      children: [etiqueta("DECIR", ACENTO), ...runs("«" + texto + "»", { size: 24, color: TINTA })],
    })];
  }
  if (item.tipo === "lista") {
    return [new Paragraph({ numbering: { reference: "vinetas", level: 0 }, spacing: { after: 60 }, children: runs(item.texto) })];
  }
  if (item.tipo === "tabla") {
    return [tabla(item.filas, [3400, ANCHO - 3400]), new Paragraph({ children: [] })];
  }
  return [new Paragraph({ spacing: { after: 120 }, children: runs(item.texto) })];
}

// Duración de cada bloque, a partir de "0:20 – 0:50"
function segundos(t) { const [m, s] = t.split(":").map(Number); return m * 60 + s; }
function partesTitulo(t) {
  const m = t.match(/^(\d+:\d\d)\s*[–-]\s*(\d+:\d\d)\s*·\s*(.*)$/);
  return m ? { desde: m[1], hasta: m[2], nombre: m[3], dur: segundos(m[2]) - segundos(m[1]) } : { desde: "", hasta: "", nombre: t, dur: 0 };
}
function acto(i) { return i <= 4 ? "Acto 1 · PostgreSQL" : "Acto 2 · Tiempo real y Databricks"; }

// Resumen: tabla de tiempos
const resumen = [["Tiempo", "Bloque", "Acto", "Dura"],
  ...guion.map((s, i) => { const p = partesTitulo(s.titulo); return [`${p.desde} – ${p.hasta}`, p.nombre, i <= 4 ? "1 · PostgreSQL" : "2 · Tiempo real", `${p.dur} s`]; })];

const cuerpo = [];
cuerpo.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun(doc.titulo.replace(/\s*\(.*\)$/, ""))] }));
cuerpo.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: "NexoCambio · Presentación final · Grupo 1 · Duración: 5 minutos", color: GRIS, size: 22 })] }));
for (const p of intro) cuerpo.push(new Paragraph({ spacing: { after: 140 }, children: runs(p) }));

cuerpo.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Mapa de tiempos")] }));
cuerpo.push(tabla(resumen, [1500, 5038, 2000, 1100]));
cuerpo.push(new Paragraph({ spacing: { before: 80 }, children: [new TextRun({ text: "Total: 5 minutos (300 s).", bold: true, size: 20 })] }));
cuerpo.push(new Paragraph({ spacing: { before: 120 }, children: [
  etiqueta("EN PANTALLA", GRIS), new TextRun({ text: "lo que se hace en la computadora.     ", size: 20, color: GRIS }),
  etiqueta("DECIR", ACENTO), new TextRun({ text: "lo que se dice en voz alta.", size: 20, color: GRIS })] }));

guion.forEach((s, i) => {
  const p = partesTitulo(s.titulo);
  if (i === 0 || i === 5) {
    cuerpo.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(acto(i))] }));
  }
  cuerpo.push(new Paragraph({
    heading: HeadingLevel.HEADING_2,
    tabStops: [{ type: TabStopType.RIGHT, position: ANCHO }],
    children: [new TextRun({ text: `${p.desde} – ${p.hasta}`, color: ACENTO }), new TextRun("   " + p.nombre),
               new TextRun({ text: `\t${p.dur} s`, color: GRIS, size: 20, bold: false })],
  }));
  for (const it of s.items) cuerpo.push(...bloque(it));
});

anexos.forEach((s, i) => {
  cuerpo.push(new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: i === 0 ? 480 : 280, after: 140 }, children: [new TextRun(s.titulo)] }));
  for (const it of s.items) cuerpo.push(...bloque(it));
});

// ------------------------------------------------------------------ encabezado con el logo
const png = fs.readFileSync(LOGO);
const ancho = png.readUInt32BE(16), alto = png.readUInt32BE(20);
const altoLogo = 34;
const encabezado = new Header({ children: [new Paragraph({
  tabStops: [{ type: TabStopType.RIGHT, position: ANCHO }],
  border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CFD6D8", space: 6 } },
  children: [
    new ImageRun({ type: "png", data: png, transformation: { width: Math.round(altoLogo * ancho / alto), height: altoLogo } }),
    new TextRun({ text: "\tNexoCambio · Guion de la demo", color: GRIS, size: 18 }),
  ],
})] });
const pie = new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
  new TextRun({ text: "Página ", color: GRIS, size: 18 }), new TextRun({ children: [PageNumber.CURRENT], color: GRIS, size: 18 })] })] });

const titulo = (size, color, before, after) => ({ run: { font: FONT, size, bold: true, color }, paragraph: { spacing: { before, after }, keepNext: true, keepLines: true } });

const documento = new Document({
  creator: "Grupo 1 · NexoCambio",
  title: "Guion de la demo",
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: TINTA } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 44, bold: true, color: TINTA }, paragraph: { spacing: { before: 0, after: 60 }, keepNext: true } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, ...titulo(30, TINTA, 280, 140), paragraph: { spacing: { before: 280, after: 140 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, ...titulo(24, TINTA, 280, 80), paragraph: { spacing: { before: 280, after: 80 }, keepNext: true, keepLines: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134, header: 567, footer: 567 } } },
    headers: { default: encabezado },
    footers: { default: pie },
    children: cuerpo,
  }],
});

Packer.toBuffer(documento).then((b) => { fs.writeFileSync(SALIDA, b); console.log("Generado:", SALIDA, `(${guion.length} bloques)`); });
