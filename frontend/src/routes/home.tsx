import { startTransition, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";

import type { TaskEvent } from "@/entities/task/model";
import { TaskProgressPanel } from "@/features/task-progress/TaskProgressPanel";
import { useTaskProgress } from "@/features/task-progress/useTaskProgress";
import { UploadPanel } from "@/features/upload-spec/UploadPanel";
import { ApiError, cancelTask, getSession, getTask, logout, uploadFile } from "@/shared/api/client";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";

export function HomePage() {
  const navigate = useNavigate();
  const search = useSearch({ from: "/" });
  const queryClient = useQueryClient();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const taskId = search.taskId ?? null;

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
      setUploadError(mutationError instanceof Error ? mutationError.message : "Upload failed");
    }
  });

  const cancelMutation = useMutation({
    mutationFn: cancelTask,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["task", taskId] });
    }
  });

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      startTransition(() => {
        void navigate({ to: "/login" });
      });
    }
  });

  const progress = useTaskProgress({
    taskId,
    enabled: !["succeeded", "failed", "canceled"].includes(taskStatusQuery.data?.status ?? ""),
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
      setTaskError(taskStatusQuery.data.error ?? "Analysis failed.");
      return;
    }

    if (taskStatusQuery.data.status === "canceled") {
      setTaskError(taskStatusQuery.data.error ?? "Task was canceled.");
      return;
    }

    setTaskError(null);
  }, [navigate, taskStatusQuery.data]);

  if (sessionQuery.isLoading) {
    return <LoadingState title="Booting frontend" message="Checking backend session and CSRF state." />;
  }

  const progressError =
    taskError ??
    (taskStatusQuery.isError
      ? taskStatusQuery.error instanceof Error
        ? taskStatusQuery.error.message
        : "Could not load the durable task status."
      : progress.error);

  return (
    <PageShell
      title="Upload and monitor"
      description="This page talks to the standalone API surface: login, upload, durable task status and resumable SSE progress."
      actions={
        sessionQuery.data?.auth_enabled ? (
          <button
            type="button"
            className="secondary-button"
            onClick={() => void logoutMutation.mutateAsync()}
            disabled={logoutMutation.isPending}
          >
            {logoutMutation.isPending ? "Signing out..." : "Sign out"}
          </button>
        ) : null
      }
    >
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
        stage={progress.stage}
        events={progress.events}
        totalTokens={progress.totalTokens}
        requestCount={progress.requestCount}
        elapsedSeconds={progress.elapsedSeconds}
        stageUsage={progress.stageUsage}
        jobStatus={taskStatusQuery.data?.status ?? null}
        isStreaming={progress.isStreaming}
        error={progressError}
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
