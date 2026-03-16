import { useState, type ReactNode } from "react";

import type {
  RecommendationItem,
  ResultPayload,
  RiskItem,
  TaskItem,
  WbsPhase,
  WorkPackage
} from "@/entities/result/model";
import { cn } from "@/shared/lib/cn";
import {
  formatDateTime,
  formatDuration,
  formatEffort,
  translateText,
  translateValue
} from "@/shared/lib/locale";
import { downloadResultPdf } from "@/shared/lib/result-pdf";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

function readText(record: Record<string, unknown>, key: string, fallback = "н/д") {
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

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3">
      <span className="compact-label">{label}</span>
      <strong className="mt-2 block text-sm font-semibold text-foreground break-words">{value}</strong>
    </div>
  );
}

function Surface({
  className,
  children
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("rounded-xl border border-border/70 bg-background/55 p-4 shadow-sm", className)}>
      {children}
    </div>
  );
}

function TaskCard({ task }: { task: TaskItem }) {
  return (
    <Surface>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <strong className="text-sm">
          {task.id} {task.name}
        </strong>
        <span className="text-xs text-muted-foreground">{formatEffort(task.estimated_hours, task.duration_days)}</span>
      </div>
      {task.description ? <p className="mt-2 text-sm leading-6 text-foreground/90">{task.description}</p> : null}
      {task.dependencies?.length ? (
        <p className="mt-2 text-xs leading-5 text-muted-foreground">Зависит от: {task.dependencies.join(", ")}</p>
      ) : null}
      {task.skills_required?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {task.skills_required.map((skill) => (
            <Badge key={skill} variant="secondary">
              {skill}
            </Badge>
          ))}
        </div>
      ) : null}
    </Surface>
  );
}

function WorkPackageCard({ workPackage }: { workPackage: WorkPackage }) {
  return (
    <details className="rounded-xl border border-border/70 bg-background/55 p-4 shadow-sm" open>
      <summary className="flex cursor-pointer list-none flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <strong className="text-sm">
            {workPackage.id} {workPackage.name}
          </strong>
          {workPackage.can_start_parallel ? <Badge variant="outline">Параллельно</Badge> : null}
        </div>
        <span className="text-xs text-muted-foreground">{formatEffort(workPackage.estimated_hours, workPackage.duration_days)}</span>
      </summary>
      <div className="mt-4 space-y-4">
        {workPackage.description ? <p className="text-sm leading-6 text-foreground/90">{workPackage.description}</p> : null}
        {workPackage.dependencies?.length ? (
          <p className="text-xs leading-5 text-muted-foreground">Зависит от: {workPackage.dependencies.join(", ")}</p>
        ) : null}
        {workPackage.deliverables?.length ? (
          <div className="space-y-2">
            <strong className="text-sm">Артефакты</strong>
            <ul className="space-y-2 pl-5 text-sm leading-6 text-muted-foreground">
              {workPackage.deliverables.map((deliverable) => (
                <li key={deliverable}>{deliverable}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {workPackage.skills_required?.length ? (
          <div className="flex flex-wrap gap-2">
            {workPackage.skills_required.map((skill) => (
              <Badge key={skill} variant="secondary">
                {skill}
              </Badge>
            ))}
          </div>
        ) : null}
        {workPackage.tasks?.length ? (
          <div className="space-y-3">
            <strong className="text-sm">Задачи</strong>
            <div className="grid gap-3">
              {workPackage.tasks.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </details>
  );
}

function PhaseCard({ phase }: { phase: WbsPhase }) {
  return (
    <details className="rounded-xl border border-border/70 bg-background/60 p-5 shadow-sm" open>
      <summary className="flex cursor-pointer list-none flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <h3 className="font-heading text-xl font-semibold text-foreground">
            {phase.id} {phase.name}
          </h3>
          {phase.description ? <p className="text-sm leading-6 text-muted-foreground">{phase.description}</p> : null}
        </div>
        <Badge variant="outline">{translateValue(phase.duration ?? "н/д")}</Badge>
      </summary>
      <div className="mt-4">
        {phase.work_packages?.length ? (
          <div className="grid gap-3">
            {phase.work_packages.map((workPackage) => (
              <WorkPackageCard key={workPackage.id} workPackage={workPackage} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Для этой фазы пока не сгенерированы пакеты работ.</p>
        )}
      </div>
    </details>
  );
}

function RiskList({ risks }: { risks: RiskItem[] }) {
  return (
    <Card className="border-border/70 bg-card/85">
      <CardHeader>
        <CardTitle className="text-2xl">Риски</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {risks.map((risk) => (
          <Surface key={risk.id}>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <strong className="text-sm">{risk.id}</strong>
              <span className="text-xs text-muted-foreground">
                {translateValue(risk.probability ?? "н/д")} / {translateValue(risk.impact ?? "н/д")}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-foreground/90">{risk.description}</p>
            {risk.mitigation ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{risk.mitigation}</p> : null}
          </Surface>
        ))}
      </CardContent>
    </Card>
  );
}

function RecommendationList({ items }: { items: RecommendationItem[] }) {
  return (
    <Card className="border-border/70 bg-card/85">
      <CardHeader>
        <CardTitle className="text-2xl">Рекомендации</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((item, index) => (
          <Surface key={`${item.category ?? "item"}-${index}`}>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <strong className="text-sm">{translateValue(item.category ?? "Общее")}</strong>
              <span className="text-xs text-muted-foreground">{translateValue(item.priority ?? "normal")}</span>
            </div>
            <p className="mt-2 text-sm leading-6 text-foreground/90">{item.recommendation}</p>
          </Surface>
        ))}
      </CardContent>
    </Card>
  );
}

export function ResultSummary({ payload }: { payload: ResultPayload }) {
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [pdfExportError, setPdfExportError] = useState<string | null>(null);
  const projectInfo = payload.result.project_info ?? {};
  const phases = payload.result.wbs?.phases ?? [];
  const usage = payload.usage as Record<string, unknown>;

  async function handlePdfDownload() {
    setPdfExportError(null);
    setIsExportingPdf(true);

    try {
      await downloadResultPdf(payload);
    } catch (error) {
      setPdfExportError(error instanceof Error ? error.message : "Не удалось сформировать PDF.");
    } finally {
      setIsExportingPdf(false);
    }
  }

  return (
    <>
      <Card className="overflow-hidden border-primary/20 bg-card/90 shadow-2xl">
        <CardHeader className="gap-5">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <CardTitle className="text-3xl">{projectInfo.project_name ?? payload.filename}</CardTitle>
              <CardDescription className="max-w-3xl text-sm leading-6 text-foreground/85">
                {projectInfo.description ?? "Сервер не передал описание проекта."}
              </CardDescription>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <Button asChild>
                <a href={payload.links.excel_export}>Скачать Excel</a>
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  void handlePdfDownload();
                }}
                disabled={isExportingPdf}
              >
                {isExportingPdf ? "Готовим PDF..." : "Скачать PDF"}
              </Button>
              <Button variant="secondary" onClick={() => downloadJson(`${payload.result_id}.json`, payload)}>
                Скачать JSON
              </Button>
              <Button variant="secondary" onClick={() => window.print()}>
                Печать
              </Button>
              <Button asChild variant="secondary">
                <a href={payload.links.self} target="_blank" rel="noreferrer">
                  Открыть JSON API
                </a>
              </Button>
            </div>
          </div>
          {pdfExportError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
              {translateText(pdfExportError, pdfExportError)}
            </div>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3">
            <MetricTile label="ID результата" value={payload.result_id} />
            <MetricTile
              label="Длительность"
              value={formatDuration(payload.calculated_duration.total_days, payload.calculated_duration.total_weeks)}
            />
            <MetricTile label="Сложность" value={translateValue(projectInfo.complexity_level ?? "н/д")} />
            <MetricTile label="Токены" value={(payload.token_usage.totals?.total_tokens ?? 0).toLocaleString("ru-RU")} />
          </div>

          <div className="grid gap-3">
            <MetricTile label="Исходный файл" value={payload.filename} />
            <MetricTile label="Время" value={formatDateTime(payload.timestamp)} />
            <MetricTile label="Профиль модели" value={readText(usage, "llm_profile")} />
            <MetricTile label="Режим агентов" value={translateValue(readText(usage, "agent_system", "single-agent"))} />
            <MetricTile label="Итерации" value={readNumber(usage, "iterations", 1).toLocaleString("ru-RU")} />
            <MetricTile label="Время работы" value={`${readNumber(usage, "elapsed_seconds", 0).toLocaleString("ru-RU")} с`} />
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/85">
        <CardHeader>
          <CardTitle className="text-2xl">Использование токенов</CardTitle>
          <CardDescription>Сводка по токенам и разбивка по этапам из серверного пайплайна.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3">
            <MetricTile label="Всего" value={(payload.token_usage.totals?.total_tokens ?? 0).toLocaleString("ru-RU")} />
            <MetricTile label="Промпт" value={(payload.token_usage.totals?.prompt_tokens ?? 0).toLocaleString("ru-RU")} />
            <MetricTile
              label="Ответ"
              value={(payload.token_usage.totals?.completion_tokens ?? 0).toLocaleString("ru-RU")}
            />
            <MetricTile label="Запросы" value={(payload.token_usage.request_count ?? 0).toLocaleString("ru-RU")} />
          </div>
          {payload.token_usage.stages?.length ? (
            <div className="overflow-auto rounded-xl border border-border/70 bg-background/55">
              <table className="min-w-[520px] w-full border-collapse text-sm">
                <thead className="bg-white/5">
                  <tr>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Этап</th>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Всего</th>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Промпт</th>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Ответ</th>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Запросы</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.token_usage.stages.map((stage) => (
                    <tr key={stage.message} className="border-t border-border/70">
                      <td className="px-3 py-3 text-muted-foreground">{translateText(stage.message)}</td>
                      <td className="px-3 py-3 text-muted-foreground">{(stage.usage.total_tokens ?? 0).toLocaleString("ru-RU")}</td>
                      <td className="px-3 py-3 text-muted-foreground">{(stage.usage.prompt_tokens ?? 0).toLocaleString("ru-RU")}</td>
                      <td className="px-3 py-3 text-muted-foreground">{(stage.usage.completion_tokens ?? 0).toLocaleString("ru-RU")}</td>
                      <td className="px-3 py-3 text-muted-foreground">{(stage.request_count ?? 0).toLocaleString("ru-RU")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">В результате пока нет статистики токенов по этапам.</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/85">
        <CardHeader>
          <CardTitle className="text-2xl">ИСР</CardTitle>
        </CardHeader>
        <CardContent>
          {phases.length ? (
            <div className="grid gap-4">
              {phases.map((phase) => (
                <PhaseCard key={phase.id} phase={phase} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Фазы пока не были возвращены.</p>
          )}
        </CardContent>
      </Card>

      {payload.result.dependencies_matrix?.length ? (
        <Card className="border-border/70 bg-card/85">
          <CardHeader>
            <CardTitle className="text-2xl">Зависимости</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto rounded-xl border border-border/70 bg-background/55">
              <table className="min-w-[520px] w-full border-collapse text-sm">
                <thead className="bg-white/5">
                  <tr>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Задача</th>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Зависит от</th>
                    <th className="px-3 py-3 text-left font-semibold text-foreground">Параллельно с</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.result.dependencies_matrix.map((dependency) => (
                    <tr key={dependency.task_id} className="border-t border-border/70">
                      <td className="px-3 py-3 text-muted-foreground">{dependency.task_id}</td>
                      <td className="px-3 py-3 text-muted-foreground">{dependency.depends_on.join(", ") || "-"}</td>
                      <td className="px-3 py-3 text-muted-foreground">{dependency.parallel_with.join(", ") || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {payload.result.risks?.length ? <RiskList risks={payload.result.risks} /> : null}

      {payload.result.assumptions?.length ? (
        <Card className="border-border/70 bg-card/85">
          <CardHeader>
            <CardTitle className="text-2xl">Допущения</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 pl-5 text-sm leading-6 text-muted-foreground">
              {payload.result.assumptions.map((assumption) => (
                <li key={assumption}>{assumption}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {payload.result.recommendations?.length ? <RecommendationList items={payload.result.recommendations} /> : null}
    </>
  );
}
