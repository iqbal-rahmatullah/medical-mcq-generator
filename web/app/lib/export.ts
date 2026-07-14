import type { ApiQuestion } from "./generate"
import {
  QUESTION_OPTION_KEYS,
  type DisplayLanguage,
  resolveQuestionForDisplay,
} from "./question-display"

const EXPORT_TITLE = "AQG — Generated Questions"
const EXPORT_FILENAME_PREFIX = "aqg_questions_export"

function todayStr() {
  return new Date().toISOString().split("T")[0]
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function exportJSON(questions: ApiQuestion[], lang: DisplayLanguage) {
  const exported = questions.map((q, i) => {
    const r = resolveQuestionForDisplay(q, lang)
    return {
      number: i + 1,
      topic: r.topic,
      competency: r.competency,
      stem: r.stem,
      options: {
        A: r.options.A,
        B: r.options.B,
        C: r.options.C,
        D: r.options.D,
      },
      answer_key: r.answer_key,
      explanation: r.explanation,
      evidence: r.evidence.map((e) => ({
        doc_id: e.doc_id,
        source: e.source,
        span_text: e.span_text,
      })),
    }
  })

  const payload = {
    exported_at: new Date().toISOString(),
    language: lang,
    total_questions: questions.length,
    questions: exported,
  }

  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  })
  triggerDownload(blob, `${EXPORT_FILENAME_PREFIX}_${todayStr()}.json`)
}

export async function exportPDF(
  questions: ApiQuestion[],
  lang: DisplayLanguage,
) {
  const { default: jsPDF } = await import("jspdf")

  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" })

  const PAGE_W = 210
  const MARGIN = 18
  const CONTENT_W = PAGE_W - MARGIN * 2
  const LINE_H = 6
  let y = MARGIN

  const checkPage = (needed = LINE_H * 2) => {
    if (y + needed > 285) {
      doc.addPage()
      y = MARGIN
    }
  }

  const writeText = (
    text: string,
    size: number,
    style: "normal" | "bold" = "normal",
    color: [number, number, number] = [30, 30, 30],
    indent = 0,
  ) => {
    doc.setFontSize(size)
    doc.setFont("helvetica", style)
    doc.setTextColor(...color)
    const lines = doc.splitTextToSize(text, CONTENT_W - indent)
    checkPage(lines.length * LINE_H + 2)
    doc.text(lines, MARGIN + indent, y)
    y += lines.length * LINE_H
  }

  const writeLine = () => {
    checkPage(4)
    doc.setDrawColor(220, 220, 220)
    doc.line(MARGIN, y, MARGIN + CONTENT_W, y)
    y += 4
  }

  doc.setFillColor(20, 80, 200)
  doc.rect(0, 0, 210, 28, "F")
  doc.setFontSize(16)
  doc.setFont("helvetica", "bold")
  doc.setTextColor(255, 255, 255)
  doc.text(EXPORT_TITLE, MARGIN, 13)
  doc.setFontSize(9)
  doc.setFont("helvetica", "normal")
  doc.text(
    `Exported: ${new Date().toLocaleString()}   |   Language: ${lang.toUpperCase()}   |   Total: ${questions.length} questions`,
    MARGIN,
    21,
  )
  y = 36

  // Questions
  questions.forEach((q, i) => {
    const r = resolveQuestionForDisplay(q, lang)
    const num = i + 1

    checkPage(30)

    doc.setFillColor(240, 244, 255)
    doc.roundedRect(MARGIN, y - 1, CONTENT_W, 8, 2, 2, "F")
    doc.setFontSize(10)
    doc.setFont("helvetica", "bold")
    doc.setTextColor(20, 80, 200)
    doc.text(`Q${num}.`, MARGIN + 2, y + 5)
    doc.setFont("helvetica", "normal")
    doc.setFontSize(8)
    doc.setTextColor(80, 80, 120)
    const badge = [r.topic, r.competency].filter(Boolean).join(" · ")
    doc.text(badge, MARGIN + 14, y + 5)
    y += 10

    // Stem
    writeText(r.stem, 10, "normal", [20, 20, 20])
    y += 2

    // Options
    QUESTION_OPTION_KEYS.forEach((key) => {
      const text = r.options[key]
      const isAnswer = key === r.answer_key
      doc.setFontSize(10)
      doc.setFont("helvetica", isAnswer ? "bold" : "normal")
      doc.setTextColor(
        isAnswer ? 20 : 50,
        isAnswer ? 120 : 50,
        isAnswer ? 20 : 50,
      )
      const lines = doc.splitTextToSize(`${key}. ${text}`, CONTENT_W - 6)
      checkPage(lines.length * LINE_H + 1)
      if (isAnswer) {
        doc.setFillColor(235, 255, 235)
        doc.roundedRect(
          MARGIN,
          y - 4,
          CONTENT_W,
          lines.length * LINE_H + 2,
          1,
          1,
          "F",
        )
      }
      doc.text(lines, MARGIN + 3, y)
      y += lines.length * LINE_H + 1
    })
    y += 2

    // Answer key
    doc.setFontSize(9)
    doc.setFont("helvetica", "bold")
    doc.setTextColor(20, 120, 20)
    doc.text(`✓ Answer: ${r.answer_key}`, MARGIN + 2, y)
    y += LINE_H + 1

    // Explanation
    if (r.explanation) {
      writeText(`Explanation: ${r.explanation}`, 9, "normal", [60, 60, 80], 2)
      y += 1
    }

    // Evidence
    if (r.evidence.length > 0) {
      writeText("Evidence Sources:", 8, "bold", [100, 100, 140])
      r.evidence.forEach((ev) => {
        const evText = `• [${ev.doc_id}] ${ev.source}${ev.span_text ? ` — "${ev.span_text.slice(0, 120)}${ev.span_text.length > 120 ? "…" : ""}"` : ""}`
        writeText(evText, 7.5, "normal", [120, 120, 150], 3)
      })
    }

    y += 2
    writeLine()
    y += 2
  })

  doc.save(`${EXPORT_FILENAME_PREFIX}_${todayStr()}.pdf`)
}

export async function exportDOCX(
  questions: ApiQuestion[],
  lang: DisplayLanguage,
) {
  const {
    Document,
    Packer,
    Paragraph,
    TextRun,
    HeadingLevel,
    BorderStyle,
    AlignmentType,
    ShadingType,
  } = await import("docx")

  const children: InstanceType<typeof Paragraph>[] = []

  // Cover title
  children.push(
    new Paragraph({
      text: EXPORT_TITLE,
      heading: HeadingLevel.TITLE,
      spacing: { after: 200 },
    }),
    new Paragraph({
      children: [
        new TextRun({
          text: `Exported: ${new Date().toLocaleString()} | Language: ${lang.toUpperCase()} | Total: ${questions.length} questions`,
          size: 18,
          color: "666666",
        }),
      ],
      spacing: { after: 400 },
    }),
  )

  questions.forEach((q, i) => {
    const r = resolveQuestionForDisplay(q, lang)
    const num = i + 1

    // Question heading
    children.push(
      new Paragraph({
        children: [
          new TextRun({
            text: `Q${num}. `,
            bold: true,
            size: 24,
            color: "1450C8",
          }),
          new TextRun({
            text: [r.topic, r.competency].filter(Boolean).join(" · "),
            size: 18,
            color: "555577",
          }),
        ],
        spacing: { before: 300, after: 120 },
        shading: { type: ShadingType.SOLID, color: "EEF2FF", fill: "EEF2FF" },
        border: {
          left: { style: BorderStyle.SINGLE, size: 12, color: "1450C8" },
        },
      }),
    )

    // Stem
    children.push(
      new Paragraph({
        children: [new TextRun({ text: r.stem, size: 22 })],
        spacing: { after: 160 },
      }),
    )

    // Options
    QUESTION_OPTION_KEYS.forEach((key) => {
      const isAnswer = key === r.answer_key
      children.push(
        new Paragraph({
          children: [
            new TextRun({
              text: `${key}. `,
              bold: isAnswer,
              color: isAnswer ? "147214" : "222222",
              size: 22,
            }),
            new TextRun({
              text: r.options[key],
              bold: isAnswer,
              color: isAnswer ? "147214" : "222222",
              size: 22,
            }),
          ],
          spacing: { after: 80 },
          shading: isAnswer
            ? { type: ShadingType.SOLID, color: "EAFAEA", fill: "EAFAEA" }
            : undefined,
        }),
      )
    })

    // Answer key
    children.push(
      new Paragraph({
        children: [
          new TextRun({
            text: `✓ Answer: ${r.answer_key}`,
            bold: true,
            color: "147214",
            size: 20,
          }),
        ],
        spacing: { before: 80, after: 80 },
      }),
    )

    // Explanation
    if (r.explanation) {
      children.push(
        new Paragraph({
          children: [
            new TextRun({
              text: "Explanation: ",
              bold: true,
              size: 19,
              color: "444466",
            }),
            new TextRun({ text: r.explanation, size: 19, color: "444466" }),
          ],
          spacing: { after: 100 },
        }),
      )
    }

    // Evidence
    if (r.evidence.length > 0) {
      children.push(
        new Paragraph({
          children: [
            new TextRun({
              text: "Evidence Sources:",
              bold: true,
              size: 17,
              color: "777799",
            }),
          ],
          spacing: { before: 60, after: 60 },
        }),
      )
      r.evidence.forEach((ev) => {
        const span = ev.span_text
          ? ` — "${ev.span_text.slice(0, 150)}${ev.span_text.length > 150 ? "…" : ""}"`
          : ""
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: `• [${ev.doc_id}] ${ev.source}${span}`,
                size: 16,
                color: "888899",
              }),
            ],
            spacing: { after: 40 },
          }),
        )
      })
    }

    // Divider paragraph
    children.push(
      new Paragraph({
        text: "",
        border: {
          bottom: { style: BorderStyle.SINGLE, size: 4, color: "DDDDEE" },
        },
        spacing: { before: 200, after: 200 },
      }),
    )
  })

  const doc = new Document({
    styles: {
      default: {
        document: {
          run: { font: "Calibri", size: 22 },
        },
      },
    },
    sections: [
      {
        properties: {
          page: {
            margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 },
          },
        },
        children,
      },
    ],
  })

  const blob = await Packer.toBlob(doc)
  triggerDownload(blob, `${EXPORT_FILENAME_PREFIX}_${todayStr()}.docx`)
}
