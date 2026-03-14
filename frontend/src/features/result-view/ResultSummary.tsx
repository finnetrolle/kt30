import type {
  RecommendationItem,
  ResultPayload,
  RiskItem,
  WbsPhase,
  WorkPackage
} from "@/entities/result/model";

function WorkPackageCard({ workPackage }: { workPackage: WorkPackage }) {
  return (
    <div className="nested-card">
      <div className="nested-card-header">
        <strong>
          {workPackage.id} {workPackage.name}
        </strong>
        <span>{workPackage.estimated_hours ?? 0} h</span>
      </div>
      {workPackage.description ? <p>{workPackage.description}</p> : null}
      {workPackage.dependencies?.length ? (
        <p className="muted-copy">Depends on: {workPackage.dependencies.join(", ")}</p>
      ) : null}
      {workPackage.tasks?.length ? (
        <ul className="compact-list">
          {workPackage.tasks.map((task) => (
            <li key={task.id}>
              <strong>{task.id}</strong> {task.name} ({task.estimated_hours ?? 0} h)
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function PhaseCard({ phase }: { phase: WbsPhase }) {
  return (
    <div className="panel">
      <div className="section-heading">
        <div>
          <h3>
            {phase.id} {phase.name}
          </h3>
          {phase.description ? <p>{phase.description}</p> : null}
        </div>
        <span className="pill">{phase.duration ?? "n/a"}</span>
      </div>
      {phase.work_packages?.length ? (
        <div className="stack">
          {phase.work_packages.map((workPackage) => (
            <WorkPackageCard key={workPackage.id} workPackage={workPackage} />
          ))}
        </div>
      ) : (
        <p className="muted-copy">No work packages were generated for this phase.</p>
      )}
    </div>
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
      <ul className="compact-list">
        {items.map((item, index) => (
          <li key={`${item.category ?? "item"}-${index}`}>
            <strong>{item.category ?? "General"}</strong>: {item.recommendation}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ResultSummary({ payload }: { payload: ResultPayload }) {
  const projectInfo = payload.result.project_info ?? {};
  const phases = payload.result.wbs?.phases ?? [];

  return (
    <>
      <div className="panel hero-panel">
        <div className="section-heading">
          <div>
            <h2>{projectInfo.project_name ?? payload.filename}</h2>
            <p>{projectInfo.description ?? "The backend did not include a project description."}</p>
          </div>
          <a href={payload.links.excel_export} className="primary-button">
            Export Excel
          </a>
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
      {payload.result.recommendations?.length ? (
        <RecommendationList items={payload.result.recommendations} />
      ) : null}
    </>
  );
}
