const DIRECT_TRANSLATIONS: Record<string, string> = {
  Idle: "Ожидание",
  streaming: "Поток активен",
  queued: "В очереди",
  running: "Выполняется",
  succeeded: "Завершено",
  failed: "Ошибка",
  canceled: "Отменено",
  "Connecting to worker stream...": "Подключаемся к потоку воркера...",
  "Connection hiccup detected. Waiting for SSE to reconnect...":
    "Соединение прервалось. Ждем переподключения к потоку событий...",
  "Analysis failed": "Анализ завершился с ошибкой",
  "Analysis failed.": "Анализ завершился с ошибкой.",
  "Analysis complete": "Анализ завершен",
  "Task was canceled.": "Задача была отменена.",
  "Task was canceled by user.": "Задача была отменена пользователем.",
  "Task not found": "Задача не найдена",
  "Result not found": "Результат не найден",
  "Upload failed": "Не удалось загрузить файл",
  "Login failed": "Не удалось выполнить вход",
  "Unknown error": "Неизвестная ошибка",
  "CSRF validation failed": "Проверка CSRF не пройдена",
  "No file provided": "Файл не был передан",
  "Could not extract JSON from response": "Не удалось извлечь JSON из ответа",
  "Parsing specification": "Разбираем спецификацию",
  "Analyzing dependencies": "Анализируем зависимости",
  "Draft WBS": "Формируем черновик ИСР",
  planner: "планировщик",
  analyst: "аналитик",
  validator: "валидатор",
  "result stabilizer": "стабилизатор результата",
  "single-agent": "один агент",
  "multi-agent": "несколько агентов",
  high: "высокий",
  medium: "средний",
  low: "низкий",
  critical: "критический",
  normal: "стандартный",
  major: "сильное",
  minor: "слабое",
  "n/a": "н/д"
};

function translatePattern(value: string): string | null {
  const requestMatch = value.match(/^Request failed with status (\d+)$/i);
  if (requestMatch) {
    return `Ошибка запроса: статус ${requestMatch[1]}`;
  }

  const stageMatch = value.match(/^Stage (\d+)$/i);
  if (stageMatch) {
    return `Этап ${stageMatch[1]}`;
  }

  const tokenMatch = value.match(/^Tokens:\s*(.+)$/i);
  if (tokenMatch) {
    return `Токены: ${translateValue(tokenMatch[1])}`;
  }

  return null;
}

export function translateText(
  value: string | null | undefined,
  fallback = "н/д"
): string {
  if (typeof value !== "string") {
    return fallback;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return fallback;
  }

  return DIRECT_TRANSLATIONS[trimmed] ?? translatePattern(trimmed) ?? trimmed;
}

export function translateValue(
  value: string | number | null | undefined,
  fallback = "н/д"
): string {
  if (typeof value === "number") {
    return value.toLocaleString("ru-RU");
  }

  return translateText(value, fallback);
}

export function translateTaskStatus(status: string | null, isStreaming = false): string {
  if (!status) {
    return isStreaming ? "Поток активен" : "Ожидание";
  }

  return translateText(status, isStreaming ? "Поток активен" : "Ожидание");
}

export function translateEventType(type: string): string {
  return (
    {
      stage: "этап",
      info: "событие",
      agent: "агент",
      usage: "токены",
      complete: "готово",
      error: "ошибка"
    }[type] ?? type
  );
}

export function formatElapsedTime(seconds: number): string {
  if (seconds < 60) {
    return `${seconds} с`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes} мин ${remainder} с`;
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short"
  });
}

export function formatUnixTime(value: number | null | undefined, fallback = "н/д"): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }

  return formatDateTime(new Date(value * 1000).toISOString());
}

export function formatEffort(
  hours: number | null | undefined,
  durationDays?: number | null
): string {
  const safeHours = hours ?? 0;
  const daysSuffix = durationDays ? ` / ${durationDays} дн.` : "";
  return `${safeHours.toLocaleString("ru-RU")} ч${daysSuffix}`;
}

export function formatDuration(days: number, weeks: number): string {
  return `${days.toLocaleString("ru-RU")} дн. / ${weeks.toLocaleString("ru-RU")} нед.`;
}

export function formatFileSize(size: number): string {
  if (size < 1024 * 1024) {
    return `${Math.round(size / 1024).toLocaleString("ru-RU")} КБ`;
  }

  return `${(size / (1024 * 1024)).toFixed(1).replace(".", ",")} МБ`;
}
