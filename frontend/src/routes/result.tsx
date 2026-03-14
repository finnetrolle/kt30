import { useDeferredValue } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";

import { ResultSummary } from "@/features/result-view/ResultSummary";
import { getResult } from "@/shared/api/client";
import { EmptyState } from "@/shared/ui/EmptyState";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";

export function ResultPage() {
  const { resultId } = useParams({ from: "/results/$resultId" });
  const resultQuery = useQuery({
    queryKey: ["result", resultId],
    queryFn: () => getResult(resultId)
  });
  const deferredPayload = useDeferredValue(resultQuery.data);

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
