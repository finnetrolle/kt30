import { startTransition, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";

import type { ActiveTaskSummary } from "@/entities/task/model";
import { cancelTask, getActiveTasks, getSession } from "@/shared/api/client";
import { shouldUseBrowserCompatibilityMode } from "@/shared/lib/browser";
import {
  formatFileSize,
  formatUnixTime,
  translateTaskStatus,
  translateText
} from "@/shared/lib/locale";
import { EmptyState } from "@/shared/ui/EmptyState";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

function resolveStage(task: ActiveTaskSummary) {
  if (task.current_stage) {
    return translateText(task.current_stage, task.current_stage);
  }

  if (task.status === "queued") {
    return "Ожидает запуска воркером";
  }

  return "Выполняется в фоновом режиме";
}

function isCancelable(task: ActiveTaskSummary) {
  return (task.status === "queued" || task.status === "running") && !task.cancel_requested;
}

function resolveStatusVariant(status: string) {
  if (status === "running" || status === "succeeded") {
    return "success" as const;
  }

  if (status === "queued") {
    return "info" as const;
  }

  if (status === "failed" || status === "canceled") {
    return "destructive" as const;
  }

  return "secondary" as const;
}

function MetaTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3">
      <span className="compact-label">{label}</span>
      <strong className="mt-2 block text-sm font-semibold text-foreground break-words">{value}</strong>
    </div>
  );
}

function ActiveTaskCard({
  task,
  cancelDisabled,
  isCurrentCancel,
  onCancel
}: {
  task: ActiveTaskSummary;
  cancelDisabled: boolean;
  isCurrentCancel: boolean;
  onCancel: (taskId: string) => Promise<unknown>;
}) {
  return (
    <Card className="border-border/70 bg-card/90">
      <CardHeader className="gap-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant={resolveStatusVariant(task.status)}>{translateTaskStatus(task.status)}</Badge>
              {task.cancel_requested ? <Badge variant="warning">Отмена запрошена</Badge> : null}
            </div>
            <div className="space-y-2">
              <CardTitle className="text-2xl">{task.filename || "Без имени"}</CardTitle>
              <CardDescription className="text-sm leading-6 text-foreground/85">{resolveStage(task)}</CardDescription>
              <p className="font-mono text-xs break-all text-muted-foreground">Задача: {task.task_id}</p>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button asChild variant="secondary">
              <Link to="/" search={{ taskId: task.task_id }}>
                Открыть
              </Link>
            </Button>
            <Button variant="secondary" disabled={cancelDisabled} onClick={() => void onCancel(task.task_id)}>
              {isCurrentCancel ? "Отменяем..." : "Отменить"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetaTile label="Создана" value={formatUnixTime(task.created_at)} />
        <MetaTile label="Обновлена" value={formatUnixTime(task.updated_at)} />
        <MetaTile label="Старт" value={formatUnixTime(task.started_at)} />
        <MetaTile label="Файл" value={typeof task.file_size === "number" ? formatFileSize(task.file_size) : "н/д"} />
        <MetaTile label="Токены" value={task.total_tokens.toLocaleString("ru-RU")} />
        <MetaTile label="Запросы" value={task.request_count.toLocaleString("ru-RU")} />
        <MetaTile label="Worker" value={task.worker_id || "Назначается"} />
        <MetaTile label="Request ID" value={task.request_id || "н/д"} />
      </CardContent>
    </Card>
  );
}

function RecentResultCard({ task }: { task: ActiveTaskSummary }) {
  if (!task.result_id) {
    return null;
  }

  return (
    <Card className="border-border/70 bg-card/90">
      <CardHeader className="gap-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant={resolveStatusVariant(task.status)}>{translateTaskStatus(task.status)}</Badge>
            </div>
            <div className="space-y-2">
              <CardTitle className="text-2xl">{task.filename || "Без имени"}</CardTitle>
              <CardDescription className="text-sm leading-6 text-foreground/85">
                Анализ завершен, результат сохранен и готов к просмотру.
              </CardDescription>
              <p className="font-mono text-xs break-all text-muted-foreground">Задача: {task.task_id}</p>
              <p className="font-mono text-xs break-all text-muted-foreground">Результат: {task.result_id}</p>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button asChild>
              <Link to="/results/$resultId" params={{ resultId: task.result_id }}>
                Открыть результат
              </Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/" search={{ taskId: task.task_id }}>
                Открыть задачу
              </Link>
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetaTile label="Создана" value={formatUnixTime(task.created_at)} />
        <MetaTile label="Завершена" value={formatUnixTime(task.finished_at)} />
        <MetaTile label="Файл" value={typeof task.file_size === "number" ? formatFileSize(task.file_size) : "н/д"} />
        <MetaTile label="Токены" value={task.total_tokens.toLocaleString("ru-RU")} />
        <MetaTile label="Запросы" value={task.request_count.toLocaleString("ru-RU")} />
      </CardContent>
    </Card>
  );
}

export function ActiveTasksPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [cancelingTaskId, setCancelingTaskId] = useState<string | null>(null);
  const compatibilityMode = shouldUseBrowserCompatibilityMode();

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession
  });
  const activeTasksQuery = useQuery({
    queryKey: ["tasks", "active"],
    queryFn: getActiveTasks,
    enabled: !sessionQuery.isLoading && (!sessionQuery.data?.auth_enabled || sessionQuery.data?.authenticated),
    refetchInterval: compatibilityMode ? 8000 : 4000
  });
  const cancelMutation = useMutation({
    mutationFn: async (taskId: string) => {
      setCancelingTaskId(taskId);
      return cancelTask(taskId);
    },
    onSuccess: async (_payload, taskId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tasks", "active"] }),
        queryClient.invalidateQueries({ queryKey: ["task", taskId] })
      ]);
    },
    onSettled: () => {
      setCancelingTaskId(null);
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

  if (sessionQuery.isLoading) {
    return <LoadingState title="Проверяем сессию" message="Подтверждаем доступ к панели активных работ." />;
  }

  if (sessionQuery.data?.auth_enabled && !sessionQuery.data.authenticated) {
    return <LoadingState title="Перенаправляем на вход" message="Для панели операторов нужна активная авторизованная сессия." />;
  }

  if (activeTasksQuery.isLoading) {
    return <LoadingState title="Собираем активные работы" message="Читаем устойчивое состояние очереди и прогресса из бэкенда." />;
  }

  if (activeTasksQuery.isError) {
    return (
      <PageShell title="Активные работы" description="Панель не смогла получить текущее состояние очереди.">
        <EmptyState
          title="Не удалось загрузить список"
          message={
            activeTasksQuery.error instanceof Error
              ? translateText(activeTasksQuery.error.message, activeTasksQuery.error.message)
              : "Неизвестная ошибка"
          }
        />
      </PageShell>
    );
  }

  const payload = activeTasksQuery.data;
  if (!payload) {
    return <LoadingState title="Собираем активные работы" message="Почти готово, ждем подтверждения от API." />;
  }

  return (
    <PageShell
      title="Активные работы"
      description="Здесь собраны все задания, которые прямо сейчас стоят в очереди или выполняются воркером. Данные автоматически обновляются каждые несколько секунд."
      actions={
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button asChild variant="secondary">
            <Link to="/">Новый анализ</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link to="/results">История результатов</Link>
          </Button>
        </div>
      }
    >
      <Card className="border-dashed border-border/80 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-xl">Почему без новой БД</CardTitle>
          <CardDescription>
            Для этой панели используется уже существующая SQLite-очередь задач и persisted progress. Этого достаточно
            для надежного списка активных работ без лишней инфраструктуры.
          </CardDescription>
          {compatibilityMode ? (
            <p className="text-xs leading-5 text-muted-foreground">
              Для Safari включен облегченный режим: обновляем список реже и без тяжелых визуальных эффектов.
            </p>
          ) : null}
        </CardHeader>
      </Card>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetaTile label="Активно сейчас" value={payload.counts.total.toLocaleString("ru-RU")} />
        <MetaTile label="Выполняются" value={payload.counts.running.toLocaleString("ru-RU")} />
        <MetaTile label="В очереди" value={payload.counts.queued.toLocaleString("ru-RU")} />
        <MetaTile label="Отмена запрошена" value={payload.counts.cancel_requested.toLocaleString("ru-RU")} />
      </div>

      {payload.items.length === 0 && payload.recent_results.length === 0 ? (
        <EmptyState
          title="Сейчас нет активных работ"
          message="Когда вы загрузите новый документ, он появится здесь и будет доступен для быстрого перехода или отмены."
        />
      ) : null}

      {payload.items.length === 0 && payload.recent_results.length > 0 ? (
        <Card className="border-dashed border-border/80 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="text-xl">Активных задач сейчас нет</CardTitle>
            <CardDescription>
              Последние завершенные анализы остаются доступны ниже, так что результат можно открыть даже после
              исчезновения из активного списка.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {payload.items.length > 0 ? (
        <div className="grid gap-4">
          {payload.items.map((task) => {
            const cancelDisabled = !isCancelable(task) || cancelMutation.isPending;
            const isCurrentCancel = cancelingTaskId === task.task_id;

            return (
              <ActiveTaskCard
                key={task.task_id}
                task={task}
                cancelDisabled={cancelDisabled}
                isCurrentCancel={isCurrentCancel}
                onCancel={(taskId) => cancelMutation.mutateAsync(taskId)}
              />
            );
          })}
        </div>
      ) : null}

      {payload.recent_results.length > 0 ? (
        <div className="space-y-4">
          <div className="space-y-2">
            <div>
              <h2 className="font-heading text-2xl text-foreground">Недавние результаты</h2>
              <p className="text-sm leading-6 text-muted-foreground">
                Завершенные анализы, которые еще доступны для открытия из текущего retention-окна.
              </p>
            </div>
          </div>
          <div className="grid gap-4">
            {payload.recent_results.map((task) => (
              <RecentResultCard key={task.task_id} task={task} />
            ))}
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}
