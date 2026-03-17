import type { TaskEvent, TaskLifecycleStatus, TaskStageUsage } from "@/entities/task/model";
import {
  formatElapsedTime,
  translateEventType,
  translateTaskStatus,
  translateText
} from "@/shared/lib/locale";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

function formatCompactValue(value: number) {
  return value.toLocaleString("ru-RU");
}

function formatSeconds(seconds: number) {
  if (!Number.isFinite(seconds)) {
    return "н/д";
  }

  if (seconds >= 60) {
    return formatElapsedTime(Math.round(seconds));
  }

  return `${seconds.toLocaleString("ru-RU")} с`;
}

function eventFacts(event: TaskEvent) {
  const facts: string[] = [];
  const { data } = event;

  if (data.agent) {
    facts.push(`Агент: ${translateText(String(data.agent), String(data.agent))}`);
  }

  if (data.model) {
    facts.push(`Модель: ${String(data.model)}`);
  }

  if (data.worker_id) {
    facts.push(`Воркер: ${String(data.worker_id)}`);
  }

  if (typeof data.attempt === "number") {
    facts.push(`Попытка: ${formatCompactValue(data.attempt)}`);
  }

  if (typeof data.elapsed_seconds === "number") {
    facts.push(`Время: ${formatSeconds(data.elapsed_seconds)}`);
  }

  if (typeof data.queue_wait_seconds === "number") {
    facts.push(`Ожидание в очереди: ${formatSeconds(data.queue_wait_seconds)}`);
  }

  if (typeof data.retry_in_seconds === "number") {
    facts.push(`Повтор через: ${formatSeconds(data.retry_in_seconds)}`);
  }

  if (data.request_id) {
    facts.push(`Request ID: ${String(data.request_id)}`);
  }

  if (typeof data.max_tokens === "number") {
    facts.push(`max_tokens: ${formatCompactValue(data.max_tokens)}`);
  }

  if (typeof data.temperature === "number") {
    facts.push(`temperature: ${String(data.temperature)}`);
  }

  if (data.usage && typeof data.usage === "object") {
    const usage = data.usage as { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
    facts.push(
      `Токены: ${formatCompactValue(Number(usage.total_tokens ?? 0))} ` +
        `(prompt ${formatCompactValue(Number(usage.prompt_tokens ?? 0))}, ` +
        `completion ${formatCompactValue(Number(usage.completion_tokens ?? 0))})`
    );
  }

  if (data.worker_health && typeof data.worker_health === "object") {
    const workerHealth = data.worker_health as { healthy_workers?: number; known_workers?: number };
    facts.push(
      `Воркеры: ${formatCompactValue(Number(workerHealth.healthy_workers ?? 0))}/${formatCompactValue(Number(workerHealth.known_workers ?? 0))}`
    );
  }

  return facts;
}

function resolveEventVariant(type: string) {
  if (type.includes("error")) {
    return "destructive" as const;
  }

  if (type.includes("complete")) {
    return "success" as const;
  }

  if (type.includes("usage") || type.includes("agent")) {
    return "warning" as const;
  }

  if (type.includes("stage")) {
    return "outline" as const;
  }

  return "info" as const;
}

interface TaskProgressPanelProps {
  taskId: string | null;
  stage: string;
  events: TaskEvent[];
  totalTokens: number;
  requestCount: number;
  elapsedSeconds: number;
  stageUsage: TaskStageUsage[];
  jobStatus: TaskLifecycleStatus | null;
  isStreaming: boolean;
  error: string | null;
  onCancel: () => Promise<void> | void;
  isCanceling: boolean;
  compactMode?: boolean;
  compatibilityNotice?: string | null;
}

export function TaskProgressPanel({
  taskId,
  stage,
  events,
  totalTokens,
  requestCount,
  elapsedSeconds,
  stageUsage,
  jobStatus,
  isStreaming,
  error,
  onCancel,
  isCanceling,
  compactMode = false,
  compatibilityNotice
}: TaskProgressPanelProps) {
  if (!taskId) {
    return (
      <Card className="border-dashed border-border/80 bg-card/70">
        <CardHeader>
          <CardTitle className="text-xl">Лента прогресса</CardTitle>
          <CardDescription>После следующей загрузки здесь появятся живые события воркера и статус анализа.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const canCancel = jobStatus === "queued" || jobStatus === "running";
  const visibleEvents = compactMode ? events.slice(-15) : events;
  const summaryItems = [
    { label: "Этап", value: translateText(stage) },
    { label: "Токены", value: totalTokens.toLocaleString("ru-RU") },
    { label: "Запросы", value: requestCount.toLocaleString("ru-RU") },
    { label: "Прошло", value: formatElapsedTime(elapsedSeconds) },
    { label: "Статус", value: translateTaskStatus(jobStatus, isStreaming) }
  ];

  return (
    <Card className="border-border/70 bg-card/85">
      <CardHeader className="gap-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <CardTitle className="text-2xl">Ход выполнения</CardTitle>
            <CardDescription className="font-mono text-xs break-all text-muted-foreground">Задача: {taskId}</CardDescription>
          </div>
          <Button variant="secondary" onClick={() => void onCancel()} disabled={!canCancel || isCanceling}>
            {isCanceling ? "Отменяем..." : "Отменить задачу"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {summaryItems.map((item) => (
            <div key={item.label} className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3">
              <span className="compact-label">{item.label}</span>
              <strong className="mt-2 block text-sm font-semibold text-foreground">{item.value}</strong>
            </div>
          ))}
        </div>

        {error ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
            {translateText(error, error)}
          </div>
        ) : null}
        {compatibilityNotice ? (
          <div className="rounded-lg border border-primary/20 bg-primary/10 px-3 py-2 text-sm text-sky-100">
            {compatibilityNotice}
          </div>
        ) : null}

        {stageUsage.length > 0 && !compactMode ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {stageUsage.map((entry) => (
              <Card key={entry.stage_id} className="border-border/70 bg-background/60">
                <CardContent className="space-y-3 p-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <strong className="text-sm">Этап {entry.stage_id}</strong>
                    <Badge variant="warning">{entry.usage.total_tokens.toLocaleString("ru-RU")} ток.</Badge>
                  </div>
                  <p className="text-sm leading-6 text-foreground/90">{translateText(entry.message)}</p>
                  <p className="text-xs leading-5 text-muted-foreground">
                    Запросы: {entry.request_count.toLocaleString("ru-RU")} | Промпт:{" "}
                    {entry.usage.prompt_tokens.toLocaleString("ru-RU")} | Ответ:{" "}
                    {entry.usage.completion_tokens.toLocaleString("ru-RU")}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}

        <div className="space-y-3">
          {events.length >= 60 && !compactMode ? (
            <p className="text-xs text-muted-foreground">Показаны последние 60 событий, чтобы не перегружать браузер.</p>
          ) : null}
          {compactMode && events.length > visibleEvents.length ? (
            <p className="text-xs text-muted-foreground">
              В Safari показываем только последние {visibleEvents.length} событий, чтобы не перегружать WebKit.
            </p>
          ) : null}
          <div className="grid max-h-[440px] gap-3 overflow-auto pr-1">
            {visibleEvents.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border/70 bg-background/40 px-4 py-3">
                <p className="text-sm text-foreground">Журнал пока пуст, но задача уже отслеживается.</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Статус: {translateTaskStatus(jobStatus, isStreaming)} | Этап: {translateText(stage)}
                </p>
              </div>
            ) : (
              visibleEvents.map((event) => (
                <div
                  key={`${event.type}-${event.timestamp}`}
                  className="grid grid-cols-[auto_1fr] gap-3 rounded-xl border border-border/70 bg-background/60 px-4 py-3"
                >
                  <Badge variant={resolveEventVariant(event.type)}>{translateEventType(event.type)}</Badge>
                  <div className="space-y-2">
                    <strong className="block text-sm text-foreground">{translateText(event.message)}</strong>
                    {eventFacts(event).length > 0 ? (
                      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        {compactMode ? (
                          <span>{eventFacts(event).join(" | ")}</span>
                        ) : (
                          eventFacts(event).map((fact) => (
                            <span key={fact} className="rounded-full border border-border/70 bg-muted/30 px-2 py-1">
                              {fact}
                            </span>
                          ))
                        )}
                      </div>
                    ) : null}
                    {!compactMode && event.data.prompt_preview ? (
                      <div className="rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Prompt preview</p>
                        <p className="mt-1 text-xs leading-5 text-foreground/90 break-words">{event.data.prompt_preview}</p>
                      </div>
                    ) : null}
                    {!compactMode && event.data.system_prompt_preview ? (
                      <div className="rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">System prompt</p>
                        <p className="mt-1 text-xs leading-5 text-foreground/80 break-words">
                          {event.data.system_prompt_preview}
                        </p>
                      </div>
                    ) : null}
                    {!compactMode && event.data.response_preview ? (
                      <div className="rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Response preview</p>
                        <p className="mt-1 text-xs leading-5 text-foreground/90 break-words">
                          {event.data.response_preview}
                        </p>
                      </div>
                    ) : null}
                    <p className="text-xs text-muted-foreground">
                      {new Date(event.timestamp * 1000).toLocaleTimeString("ru-RU")}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
