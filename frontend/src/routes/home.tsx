import { startTransition, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import type { TaskEvent } from "@/entities/task/model";
import { TaskProgressPanel } from "@/features/task-progress/TaskProgressPanel";
import { useTaskProgress } from "@/features/task-progress/useTaskProgress";
import { UploadPanel } from "@/features/upload-spec/UploadPanel";
import { cancelTask, getSession, logout, uploadFile } from "@/shared/api/client";
import { LoadingState } from "@/shared/ui/LoadingState";
import { PageShell } from "@/shared/ui/PageShell";

export function HomePage() {
  const navigate = useNavigate();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession
  });

  const uploadMutation = useMutation({
    mutationFn: uploadFile,
    onSuccess: (payload) => {
      setTaskId(payload.task_id);
    },
    onError: (mutationError) => {
      setUploadError(mutationError instanceof Error ? mutationError.message : "Upload failed");
    }
  });

  const cancelMutation = useMutation({
    mutationFn: cancelTask
  });

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      startTransition(() => {
        void navigate({ to: "/login" });
      });
    }
  });

  const progress = useTaskProgress({
    taskId,
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

  if (sessionQuery.isLoading) {
    return <LoadingState title="Booting frontend" message="Checking backend session and CSRF state." />;
  }

  return (
    <PageShell
      title="Upload and monitor"
      description="This page already talks to the new API namespace: login, upload, task status and SSE progress."
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
        isStreaming={progress.isStreaming}
        error={progress.error}
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
