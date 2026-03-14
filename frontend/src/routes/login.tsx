import { startTransition, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { LoginForm } from "@/features/auth/LoginForm";
import { getSession, login } from "@/shared/api/client";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";

export function LoginPage() {
  const navigate = useNavigate();
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
      setError(mutationError instanceof Error ? mutationError.message : "Login failed");
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
    return <LoadingState title="Checking session" message="Looking up the current auth state." />;
  }

  return (
    <PageShell
      title="Sign in"
      description="The standalone frontend uses the same Flask session and CSRF protection as the legacy app."
    >
      <LoginForm
        onSubmit={async (password) => {
          setError(null);
          await loginMutation.mutateAsync(password);
        }}
        isSubmitting={loginMutation.isPending}
        error={error}
      />
    </PageShell>
  );
}
