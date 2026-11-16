/*
 * NexoCambio · Genera grupo_01/informe.docx a partir de docs/fuentes/informe.md.
 *
 *   python generador/word/diagramas_png.py docs/fuentes/informe.md   # diagramas Mermaid → PNG
 *   node generador/word/generar_word.js
 *
 * El Markdown se interpreta con marked (mismo parser que el PDF) y se traduce a elementos
 * de Word con la librería docx. La portada se arma con párrafos simples para que se pueda
 * personalizar directamente en Word.
 */
const fs = require("fs");
const path = require("path");
const { marked } = require("marked");
const {
  AlignmentType, BorderStyle, Document, Footer, Header, HeadingLevel, ImageRun, LevelFormat,
  Packer, PageNumber, Paragraph, ShadingType, Table, TableCell, TableRow, TextRun, WidthType,
} = require("docx");

const RAIZ = path.resolve(__dirname, "..", "..");
const FUENTE = path.join(RAIZ, "docs", "fuentes", "informe.md");
const SALIDA = path.join(RAIZ, "grupo_01", "informe.docx");
const IMAGENES = path.join(__dirname, "_img");

const ACENTO = "0F5B78";
const SUAVE = "5A6675";
const LINEA = "D5DBE1";
const ANCHO_UTIL = 9638; // A4 (11906 dxa) menos márgenes de 2 cm (1134 dxa por lado)
const FUENTE_TEXTO = "Calibri";
const FUENTE_CODIGO = "Consolas";

// ------------------------------------------------------------------ utilidades
const ENTIDADES = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " " };
const decodificar = (s) => s.replace(/&(amp|lt|gt|quot|#39|nbsp);/g, (m) => ENTIDADES[m]);
const textoPlano = (html) => decodificar(html.replace(/<[^>]+>/g, "").trim());

/** Convierte tokens inline de marked en TextRun, acumulando el formato. */
function runs(tokens, fmt = {}) {
  const out = [];
  for (const t of tokens || []) {
    switch (t.type) {
      case "strong":
        out.push(...runs(t.tokens, { ...fmt, bold: true }));
        break;
      case "em":
        out.push(...runs(t.tokens, { ...fmt, italics: true }));
        break;
      case "del":
        out.push(...runs(t.tokens, { ...fmt, strike: true }));
        break;
      case "codespan":
        out.push(new TextRun({
          text: decodificar(t.text), font: FUENTE_CODIGO, size: fmt.size ? fmt.size - 2 : 18,
          bold: fmt.bold, shading: { type: ShadingType.CLEAR, color: "auto", fill: "F1F4F7" },
        }));
        break;
      case "link":
        out.push(...runs(t.tokens, { ...fmt, color: ACENTO }));
        break;
      case "br":
        out.push(new TextRun({ break: 1 }));
        break;
      case "text":
        if (t.tokens && t.tokens.length) out.push(...runs(t.tokens, fmt));
        else out.push(new TextRun({ text: decodificar(t.text), ...fmt }));
        break;
      case "escape":
        out.push(new TextRun({ text: decodificar(t.text), ...fmt }));
        break;
      case "html": {
        const s = textoPlano(t.text);
        if (s) out.push(new TextRun({ text: s, ...fmt }));
        break;
      }
      default:
        if (t.text) out.push(new TextRun({ text: decodificar(t.text), ...fmt }));
    }
  }
  return out;
}

// ------------------------------------------------------------------ bloques
let instanciaLista = 0;

function lista(token, nivel = 0, instancia = null) {
  const inst = instancia ?? ++instanciaLista;
  const out = [];
  for (const item of token.items) {
    let primero = true;
    for (const t of item.tokens) {
      if (t.type === "list") {
        out.push(...lista(t, nivel + 1, t.ordered ? null : inst));
      } else if (t.type === "text" || t.type === "paragraph") {
        out.push(new Paragraph({
          children: runs(t.tokens || [{ type: "text", text: t.text }]),
          numbering: primero
            ? { reference: token.ordered ? "numerada" : "vinetas", level: nivel, instance: inst }
            : undefined,
          indent: primero ? undefined : { left: 720 * (nivel + 1) },
          spacing: { after: 60 },
        }));
        primero = false;
      } else {
        out.push(...bloque(t));
      }
    }
  }
  return out;
}

function tabla(token) {
  const filas = [token.header, ...token.rows];
  const nCols = token.header.length;
  // Ancho de cada columna proporcional al texto más largo (con mínimos y máximos razonables).
  const largos = Array.from({ length: nCols }, (_, c) =>
    Math.min(60, Math.max(6, ...filas.map((f) => decodificar(f[c]?.text || "").length))));
  const total = largos.reduce((a, b) => a + b, 0);
  const anchos = largos.map((l) => Math.floor((l / total) * ANCHO_UTIL));
  anchos[nCols - 1] += ANCHO_UTIL - anchos.reduce((a, b) => a + b, 0);

  const borde = { style: BorderStyle.SINGLE, size: 4, color: LINEA };
  const celda = (contenido, c, encabezado) => new TableCell({
    width: { size: anchos[c], type: WidthType.DXA },
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    shading: encabezado ? { type: ShadingType.CLEAR, color: "auto", fill: "EAF1F5" } : undefined,
    borders: {
      top: borde, left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      bottom: encabezado ? { style: BorderStyle.SINGLE, size: 10, color: ACENTO } : borde,
    },
    children: [new Paragraph({
      children: runs(contenido.tokens, { size: 17, bold: encabezado || undefined }),
      spacing: { before: 0, after: 0 },
    })],
  });

  return [
    new Table({
      width: { size: ANCHO_UTIL, type: WidthType.DXA },
      columnWidths: anchos,
      rows: filas.map((f, i) => new TableRow({
        tableHeader: i === 0,
        cantSplit: true,
        children: f.map((c, j) => celda(c, j, i === 0)),
      })),
    }),
    new Paragraph({ children: [], spacing: { after: 80 } }),
  ];
}

let numDiagrama = 0;

function codigo(token) {
  if (token.lang === "mermaid") {
    numDiagrama += 1;
    const png = path.join(IMAGENES, `informe_${numDiagrama}.png`);
    if (!fs.existsSync(png)) throw new Error(`Falta ${png}: ejecute diagramas_png.py primero`);
    const datos = fs.readFileSync(png);
    const ancho = datos.readUInt32BE(16);
    const alto = datos.readUInt32BE(20);
    const w = 640; // px a 96 ppp ≈ ancho útil de la página
    return [new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 120, after: 160 },
      children: [new ImageRun({
        type: "png", data: datos, transformation: { width: w, height: Math.round((alto / ancho) * w) },
        altText: { title: "Diagrama", description: "Diagrama entidad-relación de NexoCambio", name: "diagrama" },
      })],
    })];
  }
  const lineas = token.text.split("\n");
  return lineas.map((l, i) => new Paragraph({
    children: [new TextRun({ text: l.length ? l : " ", font: FUENTE_CODIGO, size: 15 })],
    shading: { type: ShadingType.CLEAR, color: "auto", fill: "F6F8FA" },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: ACENTO, space: 6 } },
    spacing: { before: i === 0 ? 80 : 0, after: i === lineas.length - 1 ? 160 : 0, line: 240 },
    indent: { left: 120 },
  }));
}

function bloque(t) {
  switch (t.type) {
    case "heading": {
      const niveles = [null, HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3, HeadingLevel.HEADING_4];
      return [new Paragraph({
        heading: niveles[Math.min(t.depth, 4)],
        pageBreakBefore: t.depth === 1,
        children: runs(t.tokens),
      })];
    }
    case "paragraph":
      return [new Paragraph({ children: runs(t.tokens), spacing: { after: 120 } })];
    case "list":
      return lista(t);
    case "table":
      return tabla(t);
    case "code":
      return codigo(t);
    case "blockquote":
      return t.tokens.flatMap((b) => bloque(b)).map((p) => p);
    case "hr":
      return [new Paragraph({ children: [], border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: LINEA, space: 1 } } })];
    case "html":
    case "space":
      return []; // contenedores <div> de estilo del PDF: no aplican en Word
    default:
      return t.text ? [new Paragraph({ children: [new TextRun(decodificar(t.text))] })] : [];
  }
}

// ------------------------------------------------------------------ portada
// Formato de UTEC Posgrado: institución, logo, título, y los bloques AUTORES / DOCENTE / CURSO.
function portada(html) {
  const campo = (clase) => textoPlano((html.match(new RegExp(`class="${clase}">([\\s\\S]*?)</div>`)) || [])[1] || "");
  const datos = [...html.matchAll(/<p>([\s\S]*?)<\/p>/g)].map((m) => ({ texto: textoPlano(m[1]), rotulo: m[1].includes("<strong>") }));
  // El src apunta a docs/fuentes/recursos/ (relativo al HTML intermedio del PDF): se toma el nombre del archivo.
  const logo = path.join(path.dirname(FUENTE), "recursos", path.basename((html.match(/<img class="logo" src="([^"]+)"/) || [])[1]));
  const serif = { font: "Times New Roman" };
  const p = (texto, opciones = {}, parrafo = {}) =>
    new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: texto, ...serif, ...opciones })], ...parrafo });

  return [
    p(campo("institucion").toUpperCase(), { bold: true, size: 34 }, { spacing: { before: 240 } }),
    p(campo("escuela").toUpperCase(), { size: 30 }, { spacing: { after: 1000 } }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 1000 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(logo), transformation: { width: 234, height: 91 } })],
    }),
    p(campo("titulo").toUpperCase(), { bold: true, size: 44 }, { spacing: { after: 120 } }),
    p(campo("subtitulo"), { size: 26 }, { spacing: { after: 1100 } }),
    ...datos.map((d, i) => p(d.texto, { bold: d.rotulo, size: 24 }, {
      spacing: { before: i === datos.length - 2 ? 1400 : (d.rotulo && i > 0 ? 240 : 0) },
    })),
  ];
}

// ------------------------------------------------------------------ documento
function main() {
  const md = fs.readFileSync(FUENTE, "utf8");
  const m = md.match(/^<div class="portada">[\s\S]*?\n<\/div>\n<\/div>\n/);
  if (!m) throw new Error("No se encontró la portada en informe.md");
  const cuerpo = marked.lexer(md.slice(m[0].length), { gfm: true }).flatMap(bloque);

  const vineta = (nivel, simbolo) => ({
    level: nivel, format: LevelFormat.BULLET, text: simbolo, alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 720 * (nivel + 1), hanging: 280 } } },
  });
  const numero = (nivel) => ({
    level: nivel, format: nivel === 0 ? LevelFormat.DECIMAL : LevelFormat.LOWER_LETTER,
    text: `%${nivel + 1}.`, alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 720 * (nivel + 1), hanging: 360 } } },
  });

  const doc = new Document({
    creator: "Grupo 1 · NexoCambio",
    title: "NexoCambio · Informe Parte 1",
    description: "Análisis de negocio, modelo relacional y explotación de datos en PostgreSQL",
    styles: {
      default: { document: { run: { font: FUENTE_TEXTO, size: 21, color: "1D2733" }, paragraph: { spacing: { line: 276 } } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 34, bold: true, color: ACENTO },
          paragraph: { spacing: { before: 0, after: 200 }, outlineLevel: 0,
            border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACENTO, space: 4 } } } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 26, bold: true, color: ACENTO }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1, keepNext: true } },
        { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 23, bold: true }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2, keepNext: true } },
        { id: "Heading4", name: "Heading 4", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 21, bold: true, color: SUAVE }, paragraph: { spacing: { before: 160, after: 60 }, outlineLevel: 3, keepNext: true } },
      ],
    },
    numbering: {
      config: [
        { reference: "vinetas", levels: [vineta(0, "•"), vineta(1, "◦"), vineta(2, "▪")] },
        { reference: "numerada", levels: [numero(0), numero(1)] },
      ],
    },
    sections: [{
      properties: {
        titlePage: true,
        page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } },
      },
      headers: {
        first: new Header({ children: [] }),
        default: new Header({ children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: "NexoCambio · Proyecto de Base de Datos · Parte 1", size: 16, color: SUAVE })],
        })] }),
      },
      footers: {
        first: new Footer({ children: [] }),
        default: new Footer({ children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [
            new TextRun({ text: "Página ", size: 16, color: SUAVE }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: SUAVE }),
            new TextRun({ text: " de ", size: 16, color: SUAVE }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: SUAVE }),
          ],
        })] }),
      },
      children: [...portada(m[0]), ...cuerpo],
    }],
  });

  Packer.toBuffer(doc).then((buf) => {
    fs.writeFileSync(SALIDA, buf);
    console.log(`${path.relative(RAIZ, SALIDA)}  (${Math.round(buf.length / 1024)} KB)`);
  });
}

main();
