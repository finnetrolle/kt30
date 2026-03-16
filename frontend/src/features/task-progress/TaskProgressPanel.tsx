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

        {stageUsage.length > 0 ? (
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
          {events.length >= 60 ? (
            <p className="text-xs text-muted-foreground">Показаны последние 60 событий, чтобы не перегружать браузер.</p>
          ) : null}
          <div className="grid max-h-[440px] gap-3 overflow-auto pr-1">
            {events.length === 0 ? (
              <p className="text-sm text-muted-foreground">Ждем первое событие от воркера.</p>
            ) : (
              events.map((event) => (
                <div
                  key={`${event.type}-${event.timestamp}`}
                  className="grid grid-cols-[auto_1fr] gap-3 rounded-xl border border-border/70 bg-background/60 px-4 py-3"
                >
                  <Badge variant={resolveEventVariant(event.type)}>{translateEventType(event.type)}</Badge>
                  <div className="space-y-1">
                    <strong className="block text-sm text-foreground">{translateText(event.message)}</strong>
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
