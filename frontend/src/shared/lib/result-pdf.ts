import type { ResultPayload } from "@/entities/result/model";
import {
  formatDateTime,
  formatDuration,
  formatEffort,
  translateText,
  translateValue
} from "@/shared/lib/locale";

type PdfBlockVariant = "title" | "subtitle" | "section" | "subsection" | "body" | "bullet";

export interface PdfTextBlock {
  indent?: number;
  text: string;
  variant: PdfBlockVariant;
}

interface PdfImagePage {
  height: number;
  jpegData: Uint8Array;
  width: number;
}

interface PdfTextStyle {
  color: string;
  font: string;
  indentOffset: number;
  lineHeight: number;
  size: number;
  spacingAfter: number;
  spacingBefore: number;
}

const PDF_PAGE_WIDTH_POINTS = 595.28;
const PDF_PAGE_HEIGHT_POINTS = 841.89;
const CANVAS_WIDTH = 1240;
const CANVAS_HEIGHT = 1754;
const PAGE_MARGIN_X = 92;
const PAGE_MARGIN_TOP = 110;
const PAGE_MARGIN_BOTTOM = 96;
const CONTENT_BOTTOM = CANVAS_HEIGHT - PAGE_MARGIN_BOTTOM;
const HEADER_HEIGHT = 56;
const DEFAULT_FILE_BASENAME = "result";
const PDF_HEADER = Uint8Array.from([37, 80, 68, 70, 45, 49, 46, 52, 10, 37, 255, 255, 255, 255, 10]);
const TEXT_ENCODER = new TextEncoder();
const FONT_STACK = '"Arial Unicode MS", "Arial Unicode", Arial, sans-serif';

const PDF_TEXT_STYLES: Record<PdfBlockVariant, PdfTextStyle> = {
  title: {
    color: "#0f172a",
    font: `700 34px ${FONT_STACK}`,
    indentOffset: 0,
    lineHeight: 44,
    size: 34,
    spacingAfter: 14,
    spacingBefore: 0
  },
  subtitle: {
    color: "#475569",
    font: `400 19px ${FONT_STACK}`,
    indentOffset: 0,
    lineHeight: 30,
    size: 19,
    spacingAfter: 20,
    spacingBefore: 0
  },
  section: {
    color: "#0b3b60",
    font: `700 24px ${FONT_STACK}`,
    indentOffset: 0,
    lineHeight: 34,
    size: 24,
    spacingAfter: 10,
    spacingBefore: 16
  },
  subsection: {
    color: "#17212b",
    font: `700 20px ${FONT_STACK}`,
    indentOffset: 0,
    lineHeight: 30,
    size: 20,
    spacingAfter: 8,
    spacingBefore: 12
  },
  body: {
    color: "#17212b",
    font: `400 18px ${FONT_STACK}`,
    indentOffset: 28,
    lineHeight: 27,
    size: 18,
    spacingAfter: 6,
    spacingBefore: 0
  },
  bullet: {
    color: "#17212b",
    font: `400 18px ${FONT_STACK}`,
    indentOffset: 28,
    lineHeight: 27,
    size: 18,
    spacingAfter: 4,
    spacingBefore: 0
  }
};

function readTextValue(record: Record<string, unknown>, key: string, fallback = "н/д") {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value : fallback;
}

function readNumberValue(record: Record<string, unknown>, key: string, fallback = 0) {
  const value = record[key];
  return typeof value === "number" ? value : fallback;
}

function appendBlock(blocks: PdfTextBlock[], variant: PdfBlockVariant, text: string, indent = 0) {
  const trimmed = text.trim();
  if (!trimmed) {
    return;
  }

  blocks.push({ indent, text: trimmed, variant });
}

function formatTokenCount(value: number | null | undefined) {
  return (value ?? 0).toLocaleString("ru-RU");
}

function sanitizeFilenameSegment(value: string | null | undefined) {
  if (typeof value !== "string") {
    return DEFAULT_FILE_BASENAME;
  }

  const sanitized = value
    .trim()
    .replace(/[<>:"/\\|?*\u0000-\u001F]+/g, "-")
    .replace(/\s+/g, " ")
    .replace(/^\.+|\.+$/g, "");

  return sanitized || DEFAULT_FILE_BASENAME;
}

function wrapLongToken(context: CanvasRenderingContext2D, token: string, maxWidth: number) {
  const parts: string[] = [];
  let current = "";

  for (const character of token) {
    const candidate = `${current}${character}`;
    if (current && context.measureText(candidate).width > maxWidth) {
      parts.push(current);
      current = character;
      continue;
    }

    current = candidate;
  }

  if (current) {
    parts.push(current);
  }

  return parts.length ? parts : [token];
}

function wrapText(context: CanvasRenderingContext2D, text: string, maxWidth: number) {
  const wrappedLines: string[] = [];

  for (const rawLine of text.split("\n")) {
    const words = rawLine.trim().split(/\s+/).filter(Boolean);

    if (words.length === 0) {
      wrappedLines.push("");
      continue;
    }

    let currentLine = "";

    for (const word of words) {
      const candidate = currentLine ? `${currentLine} ${word}` : word;
      if (context.measureText(candidate).width <= maxWidth) {
        currentLine = candidate;
        continue;
      }

      if (currentLine) {
        wrappedLines.push(currentLine);
      }

      if (context.measureText(word).width <= maxWidth) {
        currentLine = word;
        continue;
      }

      const parts = wrapLongToken(context, word, maxWidth);
      if (parts.length > 1) {
        wrappedLines.push(...parts.slice(0, -1));
      }
      currentLine = parts[parts.length - 1] ?? "";
    }

    if (currentLine) {
      wrappedLines.push(currentLine);
    }
  }

  return wrappedLines.length ? wrappedLines : [text];
}

function createCanvasPage(projectTitle: string, pageNumber: number) {
  const canvas = document.createElement("canvas");
  canvas.width = CANVAS_WIDTH;
  canvas.height = CANVAS_HEIGHT;

  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas 2D context is not available");
  }

  context.fillStyle = "#f8fafc";
  context.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

  context.fillStyle = "#0f172a";
  context.fillRect(0, 0, CANVAS_WIDTH, HEADER_HEIGHT);

  context.fillStyle = "#ffffff";
  context.font = `700 20px ${FONT_STACK}`;
  context.fillText("KT30", PAGE_MARGIN_X, 36);

  context.fillStyle = "#cbd5e1";
  context.font = `400 16px ${FONT_STACK}`;
  const safeTitle = projectTitle.length > 72 ? `${projectTitle.slice(0, 69)}...` : projectTitle;
  context.fillText(safeTitle, PAGE_MARGIN_X + 78, 36);

  const pageLabel = `Стр. ${pageNumber}`;
  const pageLabelWidth = context.measureText(pageLabel).width;
  context.fillText(pageLabel, CANVAS_WIDTH - PAGE_MARGIN_X - pageLabelWidth, 36);

  context.fillStyle = "#94a3b8";
  context.fillRect(PAGE_MARGIN_X, HEADER_HEIGHT + 18, CANVAS_WIDTH - PAGE_MARGIN_X * 2, 2);

  return { canvas, context };
}

async function canvasToJpegBytes(canvas: HTMLCanvasElement) {
  if (typeof canvas.toBlob === "function") {
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (value) => {
          if (value) {
            resolve(value);
            return;
          }
          reject(new Error("Failed to convert canvas to Blob"));
        },
        "image/jpeg",
        0.92
      );
    });

    return new Uint8Array(await blob.arrayBuffer());
  }

  const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
  const base64 = dataUrl.split(",", 2)[1] ?? "";
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
}

export function buildResultPdfBlocks(payload: ResultPayload): PdfTextBlock[] {
  const blocks: PdfTextBlock[] = [];
  const projectInfo = payload.result.project_info ?? {};
  const phases = payload.result.wbs?.phases ?? [];
  const usage = payload.usage as Record<string, unknown>;

  appendBlock(blocks, "title", projectInfo.project_name ?? payload.filename);
  appendBlock(
    blocks,
    "subtitle",
    projectInfo.description ?? "Экспорт результата анализа, подготовленный в интерфейсе KT30."
  );

  appendBlock(blocks, "section", "Сводка");
  appendBlock(blocks, "body", `ID результата: ${payload.result_id}`);
  appendBlock(blocks, "body", `Исходный файл: ${payload.filename}`);
  appendBlock(blocks, "body", `Время: ${formatDateTime(payload.timestamp)}`);
  appendBlock(
    blocks,
    "body",
    `Длительность: ${formatDuration(payload.calculated_duration.total_days, payload.calculated_duration.total_weeks)}`
  );
  appendBlock(blocks, "body", `Сложность: ${translateValue(projectInfo.complexity_level ?? "н/д")}`);
  appendBlock(blocks, "body", `Токены: ${formatTokenCount(payload.token_usage.totals?.total_tokens)}`);
  appendBlock(blocks, "body", `Профиль модели: ${readTextValue(usage, "llm_profile")}`);
  appendBlock(
    blocks,
    "body",
    `Режим агентов: ${translateValue(readTextValue(usage, "agent_system", "single-agent"))}`
  );
  appendBlock(blocks, "body", `Итерации: ${readNumberValue(usage, "iterations", 1).toLocaleString("ru-RU")}`);
  appendBlock(
    blocks,
    "body",
    `Время работы: ${readNumberValue(usage, "elapsed_seconds", 0).toLocaleString("ru-RU")} с`
  );

  appendBlock(blocks, "section", "Использование токенов");
  appendBlock(
    blocks,
    "body",
    [
      `Всего: ${formatTokenCount(payload.token_usage.totals?.total_tokens)}`,
      `Промпт: ${formatTokenCount(payload.token_usage.totals?.prompt_tokens)}`,
      `Ответ: ${formatTokenCount(payload.token_usage.totals?.completion_tokens)}`,
      `Запросы: ${formatTokenCount(payload.token_usage.request_count)}`
    ].join(" | ")
  );

  if (payload.token_usage.stages?.length) {
    for (const stage of payload.token_usage.stages) {
      appendBlock(
        blocks,
        "bullet",
        `${translateText(stage.message)}: всего ${formatTokenCount(stage.usage.total_tokens)}, промпт ${formatTokenCount(
          stage.usage.prompt_tokens
        )}, ответ ${formatTokenCount(stage.usage.completion_tokens)}, запросы ${formatTokenCount(stage.request_count)}`
      );
    }
  } else {
    appendBlock(blocks, "body", "Статистика по этапам пока отсутствует.");
  }

  appendBlock(blocks, "section", "ИСР");
  if (!phases.length) {
    appendBlock(blocks, "body", "Фазы пока не были возвращены.");
  }

  for (const phase of phases) {
    appendBlock(blocks, "subsection", `${phase.id} ${phase.name}`.trim());
    appendBlock(blocks, "body", `Длительность: ${translateValue(phase.duration ?? "н/д")}`);
    if (phase.description) {
      appendBlock(blocks, "body", phase.description);
    }

    if (!phase.work_packages?.length) {
      appendBlock(blocks, "body", "Для этой фазы пока не сгенерированы пакеты работ.", 1);
      continue;
    }

    for (const workPackage of phase.work_packages) {
      const workPackageLabel = [
        `${workPackage.id} ${workPackage.name}`.trim(),
        workPackage.can_start_parallel ? "(можно параллельно)" : null,
        `- ${formatEffort(workPackage.estimated_hours, workPackage.duration_days)}`
      ]
        .filter(Boolean)
        .join(" ");
      appendBlock(blocks, "bullet", workPackageLabel, 1);

      if (workPackage.description) {
        appendBlock(blocks, "body", workPackage.description, 2);
      }
      if (workPackage.dependencies?.length) {
        appendBlock(blocks, "body", `Зависит от: ${workPackage.dependencies.join(", ")}`, 2);
      }
      if (workPackage.deliverables?.length) {
        appendBlock(blocks, "body", `Артефакты: ${workPackage.deliverables.join(", ")}`, 2);
      }
      if (workPackage.skills_required?.length) {
        appendBlock(blocks, "body", `Навыки: ${workPackage.skills_required.join(", ")}`, 2);
      }

      if (!workPackage.tasks?.length) {
        continue;
      }

      for (const task of workPackage.tasks) {
        const taskLabel = [`${task.id} ${task.name}`.trim(), `- ${formatEffort(task.estimated_hours, task.duration_days)}`]
          .filter(Boolean)
          .join(" ");
        appendBlock(blocks, "bullet", taskLabel, 2);

        if (task.description) {
          appendBlock(blocks, "body", task.description, 3);
        }
        if (task.dependencies?.length) {
          appendBlock(blocks, "body", `Зависит от: ${task.dependencies.join(", ")}`, 3);
        }
        if (task.skills_required?.length) {
          appendBlock(blocks, "body", `Навыки: ${task.skills_required.join(", ")}`, 3);
        }
      }
    }
  }

  if (payload.result.dependencies_matrix?.length) {
    appendBlock(blocks, "section", "Зависимости");
    for (const dependency of payload.result.dependencies_matrix) {
      appendBlock(
        blocks,
        "bullet",
        `${dependency.task_id}: зависит от ${dependency.depends_on.join(", ") || "-"}, параллельно с ${
          dependency.parallel_with.join(", ") || "-"
        }`
      );
    }
  }

  if (payload.result.risks?.length) {
    appendBlock(blocks, "section", "Риски");
    for (const risk of payload.result.risks) {
      appendBlock(
        blocks,
        "bullet",
        `${risk.id}: ${risk.description} (${translateValue(risk.probability ?? "н/д")} / ${translateValue(
          risk.impact ?? "н/д"
        )})`
      );
      if (risk.mitigation) {
        appendBlock(blocks, "body", `Снижение риска: ${risk.mitigation}`, 1);
      }
    }
  }

  if (payload.result.assumptions?.length) {
    appendBlock(blocks, "section", "Допущения");
    for (const assumption of payload.result.assumptions) {
      appendBlock(blocks, "bullet", assumption);
    }
  }

  if (payload.result.recommendations?.length) {
    appendBlock(blocks, "section", "Рекомендации");
    for (const recommendation of payload.result.recommendations) {
      appendBlock(
        blocks,
        "bullet",
        `${translateValue(recommendation.category ?? "Общее")} [${translateValue(
          recommendation.priority ?? "normal"
        )}]: ${recommendation.recommendation}`
      );
    }
  }

  return blocks;
}

async function renderPdfPages(payload: ResultPayload) {
  if (typeof document === "undefined") {
    throw new Error("PDF export is only available in the browser");
  }

  await document.fonts?.ready;

  const blocks = buildResultPdfBlocks(payload);
  const projectTitle = (payload.result.project_info?.project_name ?? payload.filename).trim() || "Результат анализа";
  const pages: PdfImagePage[] = [];
  let pageNumber = 1;
  let { canvas, context } = createCanvasPage(projectTitle, pageNumber);
  let cursorY = PAGE_MARGIN_TOP;

  const startNewPage = async () => {
    pages.push({
      height: canvas.height,
      jpegData: await canvasToJpegBytes(canvas),
      width: canvas.width
    });
    pageNumber += 1;
    ({ canvas, context } = createCanvasPage(projectTitle, pageNumber));
    cursorY = PAGE_MARGIN_TOP;
  };

  for (const block of blocks) {
    const style = PDF_TEXT_STYLES[block.variant];
    context.font = style.font;
    context.fillStyle = style.color;
    context.textBaseline = "top";

    const indentLevel = block.indent ?? 0;
    const prefix = block.variant === "bullet" ? "- " : "";
    const x = PAGE_MARGIN_X + indentLevel * style.indentOffset;
    const maxWidth = CANVAS_WIDTH - x - PAGE_MARGIN_X;
    const lines = wrapText(context, `${prefix}${block.text}`, maxWidth);

    if (cursorY + style.spacingBefore + style.lineHeight > CONTENT_BOTTOM) {
      await startNewPage();
      context.font = style.font;
      context.fillStyle = style.color;
      context.textBaseline = "top";
    }

    cursorY += style.spacingBefore;

    for (const line of lines) {
      if (cursorY + style.lineHeight > CONTENT_BOTTOM) {
        await startNewPage();
        context.font = style.font;
        context.fillStyle = style.color;
        context.textBaseline = "top";
      }

      context.fillText(line, x, cursorY, maxWidth);
      cursorY += style.lineHeight;
    }

    cursorY += style.spacingAfter;
  }

  pages.push({
    height: canvas.height,
    jpegData: await canvasToJpegBytes(canvas),
    width: canvas.width
  });

  return pages;
}

function concatenateUint8Arrays(chunks: Uint8Array[]) {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Uint8Array(totalLength);
  let offset = 0;

  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  return merged;
}

export function buildPdfDocument(pages: PdfImagePage[]) {
  const chunks: Uint8Array[] = [PDF_HEADER];
  const objectOffsets: number[] = [0];
  let currentOffset = PDF_HEADER.length;

  const pushText = (text: string) => {
    const encoded = TEXT_ENCODER.encode(text);
    chunks.push(encoded);
    currentOffset += encoded.length;
  };

  const pushBytes = (bytes: Uint8Array) => {
    chunks.push(bytes);
    currentOffset += bytes.length;
  };

  objectOffsets[1] = currentOffset;
  pushText("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");

  objectOffsets[2] = currentOffset;
  const kids = pages.map((_, index) => `${3 + index * 3} 0 R`).join(" ");
  pushText(`2 0 obj\n<< /Type /Pages /Count ${pages.length} /Kids [${kids}] >>\nendobj\n`);

  for (let index = 0; index < pages.length; index += 1) {
    const page = pages[index];
    const pageObjectNumber = 3 + index * 3;
    const contentObjectNumber = pageObjectNumber + 1;
    const imageObjectNumber = pageObjectNumber + 2;
    const imageName = `Im${index + 1}`;
    const contentStream = TEXT_ENCODER.encode(
      `q\n${PDF_PAGE_WIDTH_POINTS.toFixed(2)} 0 0 ${PDF_PAGE_HEIGHT_POINTS.toFixed(2)} 0 0 cm\n/${imageName} Do\nQ\n`
    );

    objectOffsets[pageObjectNumber] = currentOffset;
    pushText(
      `${pageObjectNumber} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PDF_PAGE_WIDTH_POINTS.toFixed(
        2
      )} ${PDF_PAGE_HEIGHT_POINTS.toFixed(
        2
      )}] /Resources << /XObject << /${imageName} ${imageObjectNumber} 0 R >> >> /Contents ${contentObjectNumber} 0 R >>\nendobj\n`
    );

    objectOffsets[contentObjectNumber] = currentOffset;
    pushText(`${contentObjectNumber} 0 obj\n<< /Length ${contentStream.length} >>\nstream\n`);
    pushBytes(contentStream);
    pushText("\nendstream\nendobj\n");

    objectOffsets[imageObjectNumber] = currentOffset;
    pushText(
      `${imageObjectNumber} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.jpegData.length} >>\nstream\n`
    );
    pushBytes(page.jpegData);
    pushText("\nendstream\nendobj\n");
  }

  const xrefOffset = currentOffset;
  pushText(`xref\n0 ${objectOffsets.length}\n`);
  pushText("0000000000 65535 f \n");

  for (let index = 1; index < objectOffsets.length; index += 1) {
    pushText(`${objectOffsets[index].toString().padStart(10, "0")} 00000 n \n`);
  }

  pushText(`trailer\n<< /Size ${objectOffsets.length} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`);

  return concatenateUint8Arrays(chunks);
}

function triggerBrowserDownload(filename: string, bytes: Uint8Array, mimeType: string) {
  const arrayBuffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(arrayBuffer).set(bytes);
  const blob = new Blob([arrayBuffer], { type: mimeType });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
  }, 0);
}

export async function downloadResultPdf(payload: ResultPayload) {
  const pages = await renderPdfPages(payload);
  const pdfBytes = buildPdfDocument(pages);
  const filename = `${sanitizeFilenameSegment(payload.result_id || payload.filename)}.pdf`;

  triggerBrowserDownload(filename, pdfBytes, "application/pdf");
}
