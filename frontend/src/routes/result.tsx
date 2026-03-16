import { startTransition, useDeferredValue, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";

import { ResultSummary } from "@/features/result-view/ResultSummary";
import { getResult, getSession } from "@/shared/api/client";
import { translateText } from "@/shared/lib/locale";
import { EmptyState } from "@/shared/ui/EmptyState";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";
import { Button } from "@/shared/ui/button";

export function ResultPage() {
  const navigate = useNavigate();
  const { resultId } = useParams({ from: "/results/$resultId" });
  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession
  });
  const resultQuery = useQuery({
    queryKey: ["result", resultId],
    queryFn: () => getResult(resultId),
    enabled: !sessionQuery.isLoading && (!sessionQuery.data?.auth_enabled || sessionQuery.data?.authenticated)
  });
  const deferredPayload = useDeferredValue(resultQuery.data);

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
    return <LoadingState title="Проверяем сессию" message="Подтверждаем доступ к выбранному результату." />;
  }

  if (sessionQuery.data?.auth_enabled && !sessionQuery.data.authenticated) {
    return <LoadingState title="Перенаправляем на вход" message="Для просмотра результата нужна активная авторизованная сессия." />;
  }

  if (resultQuery.isError) {
    return (
      <PageShell
        title="Результат недоступен"
        description="Сервер не смог вернуть запрошенный результат."
      >
        <EmptyState
          title="Не удалось загрузить результат"
          message={
            resultQuery.error instanceof Error
              ? translateText(resultQuery.error.message, resultQuery.error.message)
              : "Неизвестная ошибка"
          }
        />
      </PageShell>
    );
  }

  if (resultQuery.isLoading || !deferredPayload) {
    return <LoadingState title="Загружаем результат" message="Получаем актуальные данные ИСР из Flask." />;
  }

  return (
    <PageShell
      title="Результат анализа"
      description="Здесь показана новая модель результата с экспортом и подробной структурой ИСР."
      actions={
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button asChild variant="secondary">
            <Link to="/results">История результатов</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link to="/">Новый анализ</Link>
          </Button>
        </div>
      }
    >
      <ResultSummary payload={deferredPayload} />
    </PageShell>
  );
}
