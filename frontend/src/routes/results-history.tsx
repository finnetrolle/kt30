import { startTransition, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";

import { getResultsHistory, getSession } from "@/shared/api/client";
import { formatDateTime, formatDuration, translateText, translateValue } from "@/shared/lib/locale";
import { EmptyState } from "@/shared/ui/EmptyState";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

function MetaTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-muted/35 px-3 py-2">
      <span className="text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</span>
      <strong className="mt-1 block text-xs font-semibold leading-5 text-foreground break-words">{value}</strong>
    </div>
  );
}

export function ResultsHistoryPage() {
  const navigate = useNavigate();
  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession
  });
  const resultsHistoryQuery = useQuery({
    queryKey: ["results", "history"],
    queryFn: getResultsHistory,
    enabled: !sessionQuery.isLoading && (!sessionQuery.data?.auth_enabled || sessionQuery.data?.authenticated)
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
    return <LoadingState title="Проверяем сессию" message="Подтверждаем доступ к истории результатов." />;
  }

  if (sessionQuery.data?.auth_enabled && !sessionQuery.data?.authenticated) {
    return <LoadingState title="Перенаправляем на вход" message="Для истории результатов нужна активная авторизованная сессия." />;
  }

  if (resultsHistoryQuery.isLoading) {
    return <LoadingState title="Собираем историю" message="Читаем сохраненные результаты из file-based storage." />;
  }

  if (resultsHistoryQuery.isError) {
    return (
      <PageShell title="История результатов" description="Список сохраненных анализов пока недоступен.">
        <EmptyState
          title="Не удалось загрузить историю"
          message={
            resultsHistoryQuery.error instanceof Error
              ? translateText(resultsHistoryQuery.error.message, resultsHistoryQuery.error.message)
              : "Неизвестная ошибка"
          }
        />
      </PageShell>
    );
  }

  const payload = resultsHistoryQuery.data;
  if (!payload) {
    return <LoadingState title="Собираем историю" message="Почти готово, ждем подтверждения от API." />;
  }

  return (
    <PageShell
      title="История результатов"
      description="Здесь собраны недавние завершенные анализы, которые еще доступны в retention-окне хранения."
      actions={
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button asChild variant="secondary">
            <Link to="/">Новый анализ</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link to="/tasks">Активные работы</Link>
          </Button>
        </div>
      }
    >
      <Card className="border-dashed border-border/80 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-xl">Как работает история</CardTitle>
          <CardDescription>
            Страница показывает результаты, которые еще лежат в хранилище результатов. Если retention истечет, запись
            автоматически исчезнет из списка.
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid gap-3">
        <MetaTile label="Доступно результатов" value={payload.items.length.toLocaleString("ru-RU")} />
        <MetaTile label="Сгенерировано" value={formatDateTime(payload.generated_at)} />
      </div>

      {payload.items.length === 0 ? (
        <EmptyState
          title="История пока пуста"
          message="Когда завершится хотя бы один анализ и результат сохранится, он появится здесь."
        />
      ) : (
        <div className="grid gap-4">
          {payload.items.map((item) => (
            <Card key={item.result_id} className="border-border/70 bg-card/90">
              <CardHeader className="gap-4">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="success">Завершено</Badge>
                      {item.complexity_level ? <Badge variant="secondary">{translateValue(item.complexity_level)}</Badge> : null}
                    </div>
                    <div className="space-y-2">
                      <CardTitle className="text-2xl">{item.project_name || item.filename}</CardTitle>
                      <CardDescription className="text-sm leading-6 text-foreground/85">
                        {item.description || "Описание проекта не было передано сервером."}
                      </CardDescription>
                      <p className="font-mono text-xs break-all text-muted-foreground">Результат: {item.result_id}</p>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Button asChild>
                      <Link to="/results/$resultId" params={{ resultId: item.result_id }}>
                        Открыть результат
                      </Link>
                    </Button>
                    <Button asChild variant="secondary">
                      <a href={item.links.excel_export}>Скачать Excel</a>
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                <MetaTile label="Исходный файл" value={item.filename} />
                <MetaTile label="Время анализа" value={formatDateTime(item.timestamp)} />
                <MetaTile
                  label="Длительность"
                  value={formatDuration(item.calculated_duration.total_days, item.calculated_duration.total_weeks)}
                />
                <MetaTile label="Токены" value={(item.token_usage.totals?.total_tokens ?? 0).toLocaleString("ru-RU")} />
                <MetaTile label="Запросы" value={(item.token_usage.request_count ?? 0).toLocaleString("ru-RU")} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </PageShell>
  );
}
