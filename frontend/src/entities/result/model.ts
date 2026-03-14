export interface DependencyRow {
  task_id: string;
  depends_on: string[];
  parallel_with: string[];
}

export interface TaskItem {
  id: string;
  name: string;
  description?: string;
  estimated_hours?: number;
  duration_days?: number;
  dependencies?: string[];
  skills_required?: string[];
  can_start_parallel?: boolean;
}

export interface WorkPackage {
  id: string;
  name: string;
  description?: string;
  estimated_hours?: number;
  duration_days?: number;
  dependencies?: string[];
  deliverables?: string[];
  skills_required?: string[];
  can_start_parallel?: boolean;
  tasks?: TaskItem[];
}

export interface WbsPhase {
  id: string;
  name: string;
  description?: string;
  duration?: string;
  duration_days?: number;
  work_packages?: WorkPackage[];
}

export interface RiskItem {
  id: string;
  description: string;
  probability?: string;
  impact?: string;
  mitigation?: string;
}

export interface RecommendationItem {
  category?: string;
  priority?: string;
  recommendation: string;
}

export interface ProjectInfo {
  project_name?: string;
  description?: string;
  estimated_duration?: string;
  calculated_duration_days?: number;
  calculated_duration_weeks?: number;
  complexity_level?: string;
  [key: string]: unknown;
}

export interface ResultDocument {
  project_info?: ProjectInfo;
  wbs?: {
    phases?: WbsPhase[];
  };
  dependencies_matrix?: DependencyRow[];
  risks?: RiskItem[];
  assumptions?: string[];
  recommendations?: RecommendationItem[];
  [key: string]: unknown;
}

export interface CalculatedDuration {
  total_days: number;
  total_weeks: number;
  phase_durations?: Record<string, number>;
}

export interface ResultPayload {
  result_id: string;
  filename: string;
  timestamp: string;
  usage: Record<string, unknown>;
  metadata: Record<string, unknown>;
  token_usage: {
    totals?: {
      total_tokens?: number;
      prompt_tokens?: number;
      completion_tokens?: number;
    };
    request_count?: number;
    stages?: Array<{
      message: string;
      request_count?: number;
      usage: {
        total_tokens?: number;
        prompt_tokens?: number;
        completion_tokens?: number;
      };
    }>;
  };
  calculated_duration: CalculatedDuration;
  links: {
    self: string;
    legacy_html: string;
    excel_export: string;
    legacy_excel_export: string;
  };
  result: ResultDocument;
}
