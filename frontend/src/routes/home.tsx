import { startTransition, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";

import type { TaskEvent } from "@/entities/task/model";
import { TaskProgressPanel } from "@/features/task-progress/TaskProgressPanel";
import { useTaskProgress } from "@/features/task-progress/useTaskProgress";
import { UploadPanel } from "@/features/upload-spec/UploadPanel";
import { ApiError, cancelTask, getSession, getTask, uploadFile } from "@/shared/api/client";
import { shouldUseBrowserCompatibilityMode } from "@/shared/lib/browser";
import { translateText } from "@/shared/lib/locale";
import { LoadingState } from "@/shared/ui/LoadingState";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { PageShell } from "@/shared/ui/PageShell";

export function HomePage() {
  const navigate = useNavigate();
  const search = useSearch({ from: "/" });
  const queryClient = useQueryClient();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const taskId = search.taskId ?? null;
  const compatibilityMode = shouldUseBrowserCompatibilityMode();

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
      return !status || status === "queued" || status === "running" ? 3000 : false;
    }
  });

  const uploadMutation = useMutation({
    mutationFn: uploadFile,
    onSuccess: (payload) => {
      setTaskError(null);
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
    enabled: !compatibilityMode && !["succeeded", "failed", "canceled"].includes(taskStatusQuery.data?.status ?? ""),
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
  const effectiveStage = progress.events.length > 0 || progress.isStreaming ? progress.stage : currentStageFromStatus;
  const effectiveTotalTokens = progress.totalTokens > 0 ? progress.totalTokens : Number(taskStatusQuery.data?.total_tokens ?? 0);
  const effectiveRequestCount = progress.requestCount > 0 ? progress.requestCount : Number(taskStatusQuery.data?.request_count ?? 0);
  const effectiveElapsedSeconds = progress.elapsedSeconds > 0 || progress.isStreaming ? progress.elapsedSeconds : fallbackElapsedSeconds;
  const compatibilityNotice = compatibilityMode
    ? "Для Safari включен безопасный режим: живой SSE-поток отключен, а статус задачи обновляется легким опросом."
    : null;

  return (
    <PageShell
      title="Загрузка и контроль анализа"
      description="Здесь можно загрузить исходный файл, отслеживать устойчивый статус задачи и смотреть живой поток прогресса."
    >
      {taskId ? (
        <Card className="border-dashed border-border/80 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="text-xl">Возобновляемая задача</CardTitle>
            <CardDescription>
              Сохраните эту ссылку: пока идет анализ, интерфейс сможет восстановить прогресс по `taskId` в адресной
              строке.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <Card className="border-dashed border-border/80 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="text-xl">Как это работает</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 lg:grid-cols-3">
              <div className="rounded-xl border border-border/70 bg-background/55 p-4">
                <strong className="text-sm">1. Загрузите исходный файл</strong>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Поддерживаются документы `.docx` и `.pdf` размером до 16 МБ.
                </p>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/55 p-4">
                <strong className="text-sm">2. Следите за прогрессом</strong>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Статус не теряется после обновления страницы, а события приходят в реальном времени через SSE.
                </p>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/55 p-4">
                <strong className="text-sm">3. Изучите результат</strong>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Откройте готовую ИСР, проверьте зависимости и при необходимости экспортируйте JSON или Excel.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
      <UploadPanel
        onUpload={async (file) => {
          setUploadError(null);
          setTaskError(null);
          await uploadMutation.mutateAsync(file);
        }}
        isUploading={uploadMutation.isPending}
        error={uploadError}
      />
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
        compatibilityNotice={compatibilityNotice}
        isCanceling={cancelMutation.isPending}
        onCancel={async () => {
          if (!taskId) {
            return;
          }
          await cancelMutation.mutateAsync(taskId);
        }}
      />
    </PageShell>
  );
}
