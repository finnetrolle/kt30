import { startTransition, useDeferredValue, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";

import { ResultSummary } from "@/features/result-view/ResultSummary";
import { getResult, getSession } from "@/shared/api/client";
import { EmptyState } from "@/shared/ui/EmptyState";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";

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
    return <LoadingState title="Checking session" message="Confirming access to the requested result." />;
  }

  if (sessionQuery.data?.auth_enabled && !sessionQuery.data.authenticated) {
    return <LoadingState title="Redirecting to sign in" message="The requested result requires an authenticated session." />;
  }

  if (resultQuery.isError) {
    return (
      <PageShell
        title="Result unavailable"
        description="The backend could not return the requested result."
      >
        <EmptyState
          title="Could not load result"
          message={resultQuery.error instanceof Error ? resultQuery.error.message : "Unknown error"}
        />
      </PageShell>
    );
  }

  if (resultQuery.isLoading || !deferredPayload) {
    return <LoadingState title="Loading result" message="Fetching the latest WBS payload from Flask." />;
  }

  return (
    <PageShell
      title="Analysis result"
      description="This route already uses the new headless result view-model."
      actions={
        <Link to="/" className="secondary-button">
          New analysis
        </Link>
      }
    >
      <ResultSummary payload={deferredPayload} />
    </PageShell>
  );
}
