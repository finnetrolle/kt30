import { startTransition, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";

import type { TaskEvent, TaskProgressSnapshot } from "@/entities/task/model";
import { TaskProgressPanel } from "@/features/task-progress/TaskProgressPanel";
import { useTaskProgress } from "@/features/task-progress/useTaskProgress";
import { UploadPanel } from "@/features/upload-spec/UploadPanel";
import {
  ApiError,
  cancelTask,
  getSession,
  getTask,
  getTaskProgressSnapshot,
  uploadFile
} from "@/shared/api/client";
import {
  isDocumentVisible,
  resolveTaskPollingInterval,
  shouldUseBrowserCompatibilityMode
} from "@/shared/lib/browser";
import { formatElapsedTime, translateEventType, translateTaskStatus, translateText } from "@/shared/lib/locale";
import { LoadingState } from "@/shared/ui/LoadingState";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

function formatLogTimestamp(timestamp: number) {
  if (!Number.isFinite(timestamp)) {
    return "н/д";
  }

  return new Date(timestamp * 1000).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function summaryValue(value: number) {
  return value.toLocaleString("ru-RU");
}

function SafeJournalCard({
  taskId,
  snapshot,
  error,
  isLoading,
  onRefresh
}: {
  taskId: string | null;
  snapshot?: TaskProgressSnapshot;
  error: string | null;
  isLoading: boolean;
  onRefresh: () => Promise<void>;
}) {
  return (
    <Card className="border-border/70 bg-card">
      <CardHeader className="gap-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <CardTitle className="text-xl">Безопасный журнал для Safari</CardTitle>
            <CardDescription>
              Автоматический поток отключен. Журнал загружается только по кнопке, одним коротким snapshot-запросом.
            </CardDescription>
          </div>
          <Button variant="secondary" onClick={() => void onRefresh()} disabled={!taskId || isLoading}>
            {isLoading ? "Обновляем..." : "Обновить журнал"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-xl border border-border/70 bg-muted/20 px-4 py-3 text-sm leading-6 text-muted-foreground">
          На этой странице Safari получает только устойчивый статус задачи. Детальный журнал по умолчанию не грузится,
          чтобы не перегружать WebKit и не вешать весь браузер.
        </div>
        {error ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
            {error}
          </div>
        ) : null}
        {!snapshot && !error ? (
          <div className="rounded-xl border border-dashed border-border/70 bg-background/40 px-4 py-3 text-sm text-muted-foreground">
            Нажмите «Обновить журнал», если нужен текущий снимок выполнения.
          </div>
        ) : null}
        {snapshot ? (
          <>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
                <span className="compact-label">Этап</span>
                <strong className="mt-2 block text-sm">{translateText(snapshot.current_stage, "Ожидание")}</strong>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
                <span className="compact-label">Токены</span>
                <strong className="mt-2 block text-sm">{summaryValue(snapshot.overall_usage.total_tokens)}</strong>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
                <span className="compact-label">Запросы</span>
                <strong className="mt-2 block text-sm">{summaryValue(snapshot.request_count)}</strong>
              </div>
            </div>
            <div className="grid max-h-[360px] gap-3 overflow-auto pr-1">
              {snapshot.events.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border/70 bg-background/40 px-4 py-3 text-sm text-muted-foreground">
                  В snapshot-журнале пока нет событий.
                </div>
              ) : (
                snapshot.events.map((event) => (
                  <div
                    key={`${event.type}-${event.timestamp}-${event.message}`}
                    className="rounded-xl border border-border/70 bg-background/55 px-4 py-3"
                  >
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <strong className="text-sm text-foreground">{translateText(event.message)}</strong>
                      <span className="text-xs text-muted-foreground">
                        {translateEventType(event.type)} | {formatLogTimestamp(event.timestamp)}
                      </span>
                    </div>
                    {event.data.agent || event.data.model || event.data.worker_id || event.data.usage ? (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        {event.data.agent ? `Агент: ${translateText(String(event.data.agent), String(event.data.agent))}. ` : ""}
                        {event.data.model ? `Модель: ${String(event.data.model)}. ` : ""}
                        {event.data.worker_id ? `Воркер: ${String(event.data.worker_id)}. ` : ""}
                        {event.data.usage
                          ? `Токены: ${summaryValue(Number(event.data.usage.total_tokens ?? 0))}.`
                          : ""}
                      </p>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function HomePage() {
  const navigate = useNavigate();
  const search = useSearch({ from: "/" });
  const queryClient = useQueryClient();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [manualLogError, setManualLogError] = useState<string | null>(null);
  const taskId = search.taskId ?? null;
  const compatibilityMode = shouldUseBrowserCompatibilityMode();
  const liveProgressEnabled = Boolean(taskId) && !compatibilityMode;

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession
  });

  const taskStatusQuery = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(taskId ?? ""),
    enabled: Boolean(taskId),
    retry: (failureCount, mutationError) => {
      if (mutationError instanceof ApiError && mutationError.status === 404) {
        return false;
      }

      return failureCount < 2;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === "queued" || status === "running") {
        return resolveTaskPollingInterval(compatibilityMode, isDocumentVisible());
      }
      return false;
    }
  });

  const manualLogQuery = useQuery({
    queryKey: ["task-progress-manual", taskId],
    queryFn: () => getTaskProgressSnapshot(taskId ?? "", { compact: true }),
    enabled: false,
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false
  });

  const uploadMutation = useMutation({
    mutationFn: uploadFile,
    onSuccess: (payload) => {
      setTaskError(null);
      setManualLogError(null);
      startTransition(() => {
        void navigate({
          to: "/",
          search: (current) => ({
            ...current,
            taskId: payload.task_id
          })
        });
      });
    },
    onError: (mutationError) => {
      setUploadError(
        mutationError instanceof Error ? translateText(mutationError.message, mutationError.message) : "Не удалось загрузить файл"
      );
    }
  });

  const cancelMutation = useMutation({
    mutationFn: cancelTask,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task", taskId] });
    }
  });

  const progress = useTaskProgress({
    taskId,
    enabled: liveProgressEnabled,
    streamingEnabled: !["succeeded", "failed", "canceled"].includes(taskStatusQuery.data?.status ?? ""),
    pollIntervalMs: resolveTaskPollingInterval(compatibilityMode, true),
    compactSnapshot: compatibilityMode,
    onComplete: (event: TaskEvent) => {
      const resultId = event.data.result_id;
      if (typeof resultId !== "string") {
        return;
      }

      startTransition(() => {
        void navigate({
          to: "/results/$resultId",
          params: { resultId }
        });
      });
    }
  });

  useEffect(() => {
    setManualLogError(null);
  }, [taskId]);

  useEffect(() => {
    if (!sessionQuery.data) {
      return;
    }

    if (sessionQuery.data.auth_enabled && !sessionQuery.data.authenticated) {
      startTransition(() => {
        void navigate({ to: "/login" });
      });
    }
  }, [navigate, sessionQuery.data]);

  useEffect(() => {
    if (!taskStatusQuery.data) {
      return;
    }

    const restoredResultId = taskStatusQuery.data.result_id;

    if (taskStatusQuery.data.status === "succeeded" && restoredResultId) {
      startTransition(() => {
        void navigate({
          to: "/results/$resultId",
          params: { resultId: restoredResultId }
        });
      });
      return;
    }

    if (taskStatusQuery.data.status === "failed") {
      setTaskError(translateText(taskStatusQuery.data.error, "Анализ завершился с ошибкой."));
      return;
    }

    if (taskStatusQuery.data.status === "canceled") {
      setTaskError(translateText(taskStatusQuery.data.error, "Задача была отменена."));
      return;
    }

    setTaskError(null);
  }, [navigate, taskStatusQuery.data]);

  if (sessionQuery.isLoading) {
    return <LoadingState title="Запускаем интерфейс" message="Проверяем серверную сессию и состояние CSRF." />;
  }

  const progressError =
    taskError ??
    (taskStatusQuery.isError
      ? taskStatusQuery.error instanceof Error
        ? translateText(taskStatusQuery.error.message, taskStatusQuery.error.message)
        : "Не удалось загрузить устойчивый статус задачи."
      : progress.error);
  const currentStageFromStatus = translateText(
    taskStatusQuery.data?.current_stage,
    taskStatusQuery.data?.status === "queued" ? "Задача поставлена в очередь" : "Ожидание"
  );
  const startedAt = taskStatusQuery.data?.started_at ?? taskStatusQuery.data?.created_at;
  const fallbackElapsedSeconds =
    typeof startedAt === "number" ? Math.max(0, Math.floor(Date.now() / 1000 - startedAt)) : 0;
  const effectiveStage =
    liveProgressEnabled && (progress.events.length > 0 || progress.isStreaming) ? progress.stage : currentStageFromStatus;
  const effectiveTotalTokens = progress.totalTokens > 0 ? progress.totalTokens : Number(taskStatusQuery.data?.total_tokens ?? 0);
  const effectiveRequestCount = progress.requestCount > 0 ? progress.requestCount : Number(taskStatusQuery.data?.request_count ?? 0);
  const effectiveElapsedSeconds = progress.elapsedSeconds > 0 || progress.isStreaming ? progress.elapsedSeconds : fallbackElapsedSeconds;
  const compatibilityNotice = compatibilityMode
    ? "Для Safari включен безопасный режим: страница больше не держит живой журнал автоматически и обновляет только устойчивый статус задачи."
    : null;
  const canCancel = taskStatusQuery.data?.status === "queued" || taskStatusQuery.data?.status === "running";

  return (
    <section className="space-y-4">
      <div className="rounded-[calc(var(--radius)+8px)] border border-border/70 bg-card px-6 py-6 sm:px-8">
        <p className="compact-label">Новый анализ</p>
        <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Запуск и контроль анализа</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
          Загрузите документ, дождитесь результата и при необходимости вернитесь к задаче по `taskId` в адресной
          строке. В Safari страница работает в безопасном режиме без постоянного живого лога.
        </p>
      </div>
      <UploadPanel
        onUpload={async (file) => {
          setUploadError(null);
          setTaskError(null);
          await uploadMutation.mutateAsync(file);
        }}
        isUploading={uploadMutation.isPending}
        error={uploadError}
      />
      <Card className="border-border/70 bg-card">
        <CardHeader className="gap-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <CardTitle className="text-2xl">{taskId ? "Текущая задача" : "Задача пока не запущена"}</CardTitle>
              <CardDescription>
                {taskId
                  ? "Страница держит устойчивый статус задачи и позволяет безопасно продолжить работу после перезагрузки."
                  : "После загрузки документа здесь появятся `taskId`, статус, токены и ссылка на результат."}
              </CardDescription>
            </div>
            <Button
              variant="secondary"
              onClick={() => {
                if (!taskId) {
                  return;
                }
                void cancelMutation.mutateAsync(taskId);
              }}
              disabled={!taskId || !canCancel || cancelMutation.isPending}
            >
              {cancelMutation.isPending ? "Отменяем..." : "Отменить задачу"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
              <span className="compact-label">Task ID</span>
              <strong className="mt-2 block break-all text-sm">{taskId ?? "Появится после загрузки"}</strong>
            </div>
            <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
              <span className="compact-label">Статус</span>
              <strong className="mt-2 block text-sm">
                {translateTaskStatus(taskStatusQuery.data?.status ?? null, progress.isStreaming)}
              </strong>
            </div>
            <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
              <span className="compact-label">Этап</span>
              <strong className="mt-2 block text-sm">{effectiveStage}</strong>
            </div>
            <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
              <span className="compact-label">Токены</span>
              <strong className="mt-2 block text-sm">{summaryValue(effectiveTotalTokens)}</strong>
            </div>
            <div className="rounded-xl border border-border/70 bg-background/55 px-4 py-3">
              <span className="compact-label">Запросы / время</span>
              <strong className="mt-2 block text-sm">
                {summaryValue(effectiveRequestCount)} / {formatElapsedTime(effectiveElapsedSeconds)}
              </strong>
            </div>
          </div>
          {progressError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
              {progressError}
            </div>
          ) : null}
          {compatibilityNotice ? (
            <div className="rounded-lg border border-primary/20 bg-primary/10 px-3 py-2 text-sm text-sky-100">
              {compatibilityNotice}
            </div>
          ) : null}
        </CardContent>
      </Card>
      {compatibilityMode ? (
        <SafeJournalCard
          taskId={taskId}
          snapshot={manualLogQuery.data}
          error={
            manualLogError ??
            (manualLogQuery.error instanceof Error ? translateText(manualLogQuery.error.message) : null)
          }
          isLoading={manualLogQuery.isFetching}
          onRefresh={async () => {
            if (!taskId) {
              return;
            }

            setManualLogError(null);
            const result = await manualLogQuery.refetch();
            if (result.error instanceof Error) {
              setManualLogError(translateText(result.error.message, result.error.message));
            }
          }}
        />
      ) : (
        <TaskProgressPanel
          taskId={taskId}
          stage={effectiveStage}
          events={progress.events}
          totalTokens={effectiveTotalTokens}
          requestCount={effectiveRequestCount}
          elapsedSeconds={effectiveElapsedSeconds}
          stageUsage={progress.stageUsage}
          jobStatus={taskStatusQuery.data?.status ?? null}
          isStreaming={progress.isStreaming}
          error={progressError}
          compactMode={false}
          compatibilityNotice={null}
          isCanceling={cancelMutation.isPending}
          onCancel={async () => {
            if (!taskId) {
              return;
            }
            await cancelMutation.mutateAsync(taskId);
          }}
        />
      )}
    </section>
  );
}
