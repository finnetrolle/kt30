export interface TokenUsageBucket {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface TaskStageUsage {
  stage_id: number;
  message: string;
  usage: TokenUsageBucket;
  request_count: number;
}

export interface TokenUsageStage {
  stage_id: number;
  message: string;
  usage: TokenUsageBucket;
  request_count: number;
}

export interface UsageSummary {
  totals: TokenUsageBucket;
  request_count: number;
  stages: TokenUsageStage[];
}

export interface TaskEventPayload {
  result_id?: string;
  redirect_url?: string;
  usage_summary?: UsageSummary;
  overall_usage?: TokenUsageBucket;
  usage?: TokenUsageBucket;
  stage_usage?: TokenUsageBucket;
  stage_id?: number;
  stage_message?: string;
  request_count?: number;
  stage_request_count?: number;
  [key: string]: unknown;
}

export interface TaskEvent {
  type: string;
  message: string;
  timestamp: number;
  data: TaskEventPayload;
}

export type TaskLifecycleStatus = "queued" | "running" | "succeeded" | "failed" | "canceled" | string;

export interface TaskStatus {
  task_id: string;
  status: TaskLifecycleStatus;
  error?: string | null;
  result_id?: string | null;
  worker_id?: string | null;
  cancel_requested?: boolean | number | null;
  payload?: Record<string, unknown>;
}
