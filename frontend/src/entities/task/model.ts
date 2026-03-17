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
  agent?: string;
  model?: string;
  request_id?: string;
  worker_id?: string;
  llm_event?: string;
  attempt?: number;
  max_tokens?: number;
  temperature?: number;
  elapsed_seconds?: number;
  retry_in_seconds?: number;
  queue_wait_seconds?: number;
  prompt_preview?: string;
  response_preview?: string;
  prompt_characters?: number;
  response_characters?: number;
  system_prompt_preview?: string;
  system_prompt_characters?: number;
  job_status?: string;
  worker_available?: boolean;
  worker_health?: {
    healthy_workers?: number;
    known_workers?: number;
  } | null;
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

export interface TaskProgressSnapshot {
  task_id: string;
  status?: TaskLifecycleStatus | null;
  current_stage?: string | null;
  current_stage_id?: number | null;
  request_count: number;
  overall_usage: TokenUsageBucket;
  stage_usage: TaskStageUsage[];
  events: TaskEvent[];
  completed: boolean;
  error: boolean;
  artifacts_dir?: string | null;
  worker_available: boolean;
  worker_health?: {
    healthy_workers?: number;
    known_workers?: number;
  } | null;
}

export type TaskLifecycleStatus = "queued" | "running" | "succeeded" | "failed" | "canceled" | string;

export interface TaskStatus {
  task_id: string;
  status: TaskLifecycleStatus;
  error?: string | null;
  result_id?: string | null;
  worker_id?: string | null;
  cancel_requested?: boolean | number | null;
  filename?: string | null;
  file_size?: number | null;
  current_stage?: string | null;
  current_stage_id?: number | null;
  request_count?: number;
  total_tokens?: number;
  created_at?: number;
  updated_at?: number;
  started_at?: number | null;
  finished_at?: number | null;
  payload?: Record<string, unknown>;
}

export interface ActiveTaskSummary {
  task_id: string;
  status: TaskLifecycleStatus;
  error?: string | null;
  result_id?: string | null;
  worker_id?: string | null;
  cancel_requested?: boolean;
  filename?: string | null;
  file_size?: number | null;
  request_id?: string | null;
  current_stage?: string | null;
  current_stage_id?: number | null;
  request_count: number;
  total_tokens: number;
  created_at: number;
  updated_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  artifacts_dir?: string | null;
}

export interface ActiveTaskList {
  scope: string;
  generated_at: string;
  counts: {
    total: number;
    queued: number;
    running: number;
    cancel_requested: number;
  };
  items: ActiveTaskSummary[];
  recent_results: ActiveTaskSummary[];
}
