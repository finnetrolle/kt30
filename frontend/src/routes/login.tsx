import { startTransition, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";

import { LoginForm } from "@/features/auth/LoginForm";
import { getSession, login } from "@/shared/api/client";
import { translateText } from "@/shared/lib/locale";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";

export function LoginPage() {
  const navigate = useNavigate();
  const search = useSearch({ from: "/login" });
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession
  });

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      startTransition(() => {
        void navigate({ to: "/" });
      });
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof Error ? translateText(mutationError.message, mutationError.message) : "Не удалось выполнить вход"
      );
    }
  });

  useEffect(() => {
    if (!sessionQuery.data) {
      return;
    }

    if (!sessionQuery.data.auth_enabled || sessionQuery.data.authenticated) {
      startTransition(() => {
        void navigate({ to: "/" });
      });
    }
  }, [navigate, sessionQuery.data]);

  if (sessionQuery.isLoading) {
    return <LoadingState title="Проверяем сессию" message="Уточняем текущее состояние авторизации." />;
  }

  const compatibilityError =
    search.legacyError === "invalid-password" ? "Неверный пароль" : null;

  return (
    <PageShell
      title="Вход в систему"
      description="Новый интерфейс использует ту же сессию Flask и ту же защиту CSRF, что и старое приложение."
    >
      <LoginForm
        onSubmit={async (password) => {
          setError(null);
          await loginMutation.mutateAsync(password);
        }}
        isSubmitting={loginMutation.isPending}
        error={error ?? compatibilityError}
      />
    </PageShell>
  );
}
