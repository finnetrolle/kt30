import type {
  RecommendationItem,
  ResultPayload,
  RiskItem,
  TaskItem,
  WbsPhase,
  WorkPackage
} from "@/entities/result/model";

function readText(record: Record<string, unknown>, key: string, fallback = "n/a") {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value : fallback;
}

function readNumber(record: Record<string, unknown>, key: string, fallback = 0) {
  const value = record[key];
  return typeof value === "number" ? value : fallback;
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json"
  });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}

function TaskCard({ task }: { task: TaskItem }) {
  return (
    <div className="task-card">
      <div className="task-card-header">
        <strong>
          {task.id} {task.name}
        </strong>
        <span>
          {task.estimated_hours ?? 0} h
          {task.duration_days ? ` / ${task.duration_days} d` : ""}
        </span>
      </div>
      {task.description ? <p>{task.description}</p> : null}
      {task.dependencies?.length ? (
        <p className="muted-copy">Depends on: {task.dependencies.join(", ")}</p>
      ) : null}
      {task.skills_required?.length ? (
        <div className="badge-row">
          {task.skills_required.map((skill) => (
            <span key={skill} className="soft-badge">
              {skill}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function WorkPackageCard({ workPackage }: { workPackage: WorkPackage }) {
  return (
    <details className="nested-card" open>
      <summary className="details-summary">
        <div>
          <strong>
            {workPackage.id} {workPackage.name}
          </strong>
          {workPackage.can_start_parallel ? (
            <span className="soft-badge">Parallel</span>
          ) : null}
        </div>
        <span>
          {workPackage.estimated_hours ?? 0} h
          {workPackage.duration_days ? ` / ${workPackage.duration_days} d` : ""}
        </span>
      </summary>
      {workPackage.description ? <p>{workPackage.description}</p> : null}
      {workPackage.dependencies?.length ? (
        <p className="muted-copy">Depends on: {workPackage.dependencies.join(", ")}</p>
      ) : null}
      {workPackage.deliverables?.length ? (
        <div className="stack tight-stack">
          <strong>Deliverables</strong>
          <ul className="compact-list">
            {workPackage.deliverables.map((deliverable) => (
              <li key={deliverable}>{deliverable}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {workPackage.skills_required?.length ? (
        <div className="badge-row">
          {workPackage.skills_required.map((skill) => (
            <span key={skill} className="soft-badge">
              {skill}
            </span>
          ))}
        </div>
      ) : null}
      {workPackage.tasks?.length ? (
        <div className="stack tight-stack">
          <strong>Tasks</strong>
          <div className="stack">
            {workPackage.tasks.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </div>
        </div>
      ) : null}
    </details>
  );
}

function PhaseCard({ phase }: { phase: WbsPhase }) {
  return (
    <details className="panel phase-panel" open>
      <summary className="details-summary">
        <div>
          <h3>
            {phase.id} {phase.name}
          </h3>
          {phase.description ? <p>{phase.description}</p> : null}
        </div>
        <span className="pill">{phase.duration ?? "n/a"}</span>
      </summary>
      {phase.work_packages?.length ? (
        <div className="stack">
          {phase.work_packages.map((workPackage) => (
            <WorkPackageCard key={workPackage.id} workPackage={workPackage} />
          ))}
        </div>
      ) : (
        <p className="muted-copy">No work packages were generated for this phase.</p>
      )}
    </details>
  );
}

function RiskList({ risks }: { risks: RiskItem[] }) {
  return (
    <div className="panel">
      <h2>Risks</h2>
      <div className="stack">
        {risks.map((risk) => (
          <div key={risk.id} className="nested-card">
            <div className="nested-card-header">
              <strong>{risk.id}</strong>
              <span>
                {risk.probability ?? "n/a"} / {risk.impact ?? "n/a"}
              </span>
            </div>
            <p>{risk.description}</p>
            {risk.mitigation ? <p className="muted-copy">{risk.mitigation}</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function RecommendationList({ items }: { items: RecommendationItem[] }) {
  return (
    <div className="panel">
      <h2>Recommendations</h2>
      <div className="stack">
        {items.map((item, index) => (
          <div key={`${item.category ?? "item"}-${index}`} className="nested-card">
            <div className="nested-card-header">
              <strong>{item.category ?? "General"}</strong>
              <span>{item.priority ?? "normal"}</span>
            </div>
            <p>{item.recommendation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ResultSummary({ payload }: { payload: ResultPayload }) {
  const projectInfo = payload.result.project_info ?? {};
  const phases = payload.result.wbs?.phases ?? [];
  const usage = payload.usage as Record<string, unknown>;

  return (
    <>
      <div className="panel hero-panel">
        <div className="section-heading">
          <div>
            <h2>{projectInfo.project_name ?? payload.filename}</h2>
            <p>{projectInfo.description ?? "The backend did not include a project description."}</p>
          </div>
          <div className="button-cluster">
            <a href={payload.links.excel_export} className="primary-button">
              Export Excel
            </a>
            <button
              type="button"
              className="secondary-button"
              onClick={() => downloadJson(`${payload.result_id}.json`, payload)}
            >
              Export JSON
            </button>
            <button type="button" className="secondary-button" onClick={() => window.print()}>
              Print
            </button>
            <a href={payload.links.legacy_html} className="secondary-button">
              Open legacy view
            </a>
          </div>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <span className="summary-label">Result ID</span>
            <strong>{payload.result_id}</strong>
          </div>
          <div className="stat-card">
            <span className="summary-label">Duration</span>
            <strong>
              {payload.calculated_duration.total_days} d / {payload.calculated_duration.total_weeks} w
            </strong>
          </div>
          <div className="stat-card">
            <span className="summary-label">Complexity</span>
            <strong>{projectInfo.complexity_level ?? "n/a"}</strong>
          </div>
          <div className="stat-card">
            <span className="summary-label">Tokens</span>
            <strong>{payload.token_usage.totals?.total_tokens ?? 0}</strong>
          </div>
        </div>

        <div className="info-grid">
          <div className="info-tile">
            <span className="summary-label">Source file</span>
            <strong>{payload.filename}</strong>
          </div>
          <div className="info-tile">
            <span className="summary-label">Timestamp</span>
            <strong>{payload.timestamp}</strong>
          </div>
          <div className="info-tile">
            <span className="summary-label">Model profile</span>
            <strong>{readText(usage, "llm_profile")}</strong>
          </div>
          <div className="info-tile">
            <span className="summary-label">Agent mode</span>
            <strong>{readText(usage, "agent_system", "single-agent")}</strong>
          </div>
          <div className="info-tile">
            <span className="summary-label">Iterations</span>
            <strong>{readNumber(usage, "iterations", 1)}</strong>
          </div>
          <div className="info-tile">
            <span className="summary-label">Elapsed seconds</span>
            <strong>{readNumber(usage, "elapsed_seconds", 0)}</strong>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="section-heading">
          <div>
            <h2>Token usage</h2>
            <p>Totals and per-stage usage from the backend pipeline.</p>
          </div>
        </div>
        <div className="stats-grid">
          <div className="stat-card">
            <span className="summary-label">Total</span>
            <strong>{payload.token_usage.totals?.total_tokens ?? 0}</strong>
          </div>
          <div className="stat-card">
            <span className="summary-label">Prompt</span>
            <strong>{payload.token_usage.totals?.prompt_tokens ?? 0}</strong>
          </div>
          <div className="stat-card">
            <span className="summary-label">Completion</span>
            <strong>{payload.token_usage.totals?.completion_tokens ?? 0}</strong>
          </div>
          <div className="stat-card">
            <span className="summary-label">Requests</span>
            <strong>{payload.token_usage.request_count ?? 0}</strong>
          </div>
        </div>
        {payload.token_usage.stages?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Total</th>
                  <th>Prompt</th>
                  <th>Completion</th>
                  <th>Requests</th>
                </tr>
              </thead>
              <tbody>
                {payload.token_usage.stages.map((stage) => (
                  <tr key={stage.message}>
                    <td>{stage.message}</td>
                    <td>{stage.usage.total_tokens ?? 0}</td>
                    <td>{stage.usage.prompt_tokens ?? 0}</td>
                    <td>{stage.usage.completion_tokens ?? 0}</td>
                    <td>{stage.request_count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted-copy">The result does not include stage-level token stats yet.</p>
        )}
      </div>

      <div className="panel">
        <h2>WBS</h2>
        <div className="stack">
          {phases.length ? (
            phases.map((phase) => <PhaseCard key={phase.id} phase={phase} />)
          ) : (
            <p className="muted-copy">No phases were returned yet.</p>
          )}
        </div>
      </div>

      {payload.result.dependencies_matrix?.length ? (
        <div className="panel">
          <h2>Dependencies</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Depends on</th>
                  <th>Parallel with</th>
                </tr>
              </thead>
              <tbody>
                {payload.result.dependencies_matrix.map((dependency) => (
                  <tr key={dependency.task_id}>
                    <td>{dependency.task_id}</td>
                    <td>{dependency.depends_on.join(", ") || "-"}</td>
                    <td>{dependency.parallel_with.join(", ") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {payload.result.risks?.length ? <RiskList risks={payload.result.risks} /> : null}
      {payload.result.assumptions?.length ? (
        <div className="panel">
          <h2>Assumptions</h2>
          <ul className="compact-list">
            {payload.result.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {payload.result.recommendations?.length ? (
        <RecommendationList items={payload.result.recommendations} />
      ) : null}
    </>
  );
}
