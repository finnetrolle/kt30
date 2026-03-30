# Agent Eval Runner

Детерминированный офлайн runner для оценки результатов мульти-агентного WBS-пайплайна.

Что умеет:

- оценивать golden cases из JSON-файла
- оценивать уже сохранённые артефакты из `analysis_runs/*/final_result.json`
- собирать draft golden case из реального `analysis_runs/<run>` или `final_result.json`
- считать общий score, pass/fail и покомпонентные проверки
- опционально запускать LLM judge по trace-артефактам (`llm_calls.ndjson`, `intermediate_results.ndjson`, `progress_events.ndjson`)

Основные проверки:

- traceability по `requirement_ids`
- соответствие диапазону `total_hours_range`
- confidence против целевого порога
- покрытие ожидаемых фаз
- структурная полнота WBS

Примеры запуска:

```bash
.venv/bin/python ops/run_agent_eval.py --cases evals/golden_cases.starter.json
```

```bash
make eval
```

```bash
.venv/bin/python ops/run_agent_eval.py --analysis-runs analysis_runs --output runtime/agent_eval_report.json
```

```bash
.venv/bin/python ops/run_agent_eval.py --cases evals/golden_cases.starter.json --fail-on-failing-cases
```

```bash
.venv/bin/python ops/run_agent_eval.py --analysis-runs analysis_runs --llm-judge
```

```bash
.venv/bin/python ops/run_agent_eval.py --analysis-runs analysis_runs --llm-judge --judge-model gpt-4.1
```

Сборка draft golden case из реального результата:

```bash
.venv/bin/python ops/bootstrap_golden_case.py --source analysis_runs/20260323_123000_demo --cases-file evals/golden_cases.local.json
```

```bash
.venv/bin/python ops/bootstrap_golden_case.py --source analysis_runs/20260323_123000_demo/final_result.json --cases-file evals/golden_cases.local.json --replace-existing --stdout
```

`bootstrap_golden_case.py` не пытается автоматически сделать кейс «идеальным». Он заполняет черновик на основе фактического результата и добавляет `REVIEW_REQUIRED` notes, чтобы вы вручную уточнили:

- `expected.total_hours_range` по исходному ТЗ, а не только по текущему результату
- список `required_requirement_ids`, если в traceability-матрице их слишком много
- `required_phase_names`, если для конкретного типа проекта нужны более строгие фазы

Формат golden case:

```json
{
  "case_id": "payments-api",
  "expected": {
    "project_type": "API сервис",
    "complexity_level": "Высокий",
    "total_hours_range": [120, 560],
    "required_requirement_ids": ["FR-1", "FR-2"],
    "required_phase_names": ["Разработка", "Тестирование"],
    "min_confidence_score": 0.7,
    "min_total_score": 75
  },
  "result": {
    "...": "payload from final_result.json or result store"
  }
}
```

Если хотите использовать LLM judge для golden case, можно дополнительно указать:

```json
{
  "trace_dir": "../analysis_runs/20260323_123000_demo_case"
}
```

или встроить готовый `trace`-bundle прямо в JSON.

Лучше всего этот runner работает, если кейсы сохраняются вместе с `metadata.requirements_coverage` и `validation`.
Для LLM judge trace-артефакты должны лежать рядом с `final_result.json` или быть явно переданы через `trace_dir` / `trace`.

Рекомендуемый starter-набор для `make eval` и CI лежит в `evals/golden_cases.starter.json`. Упрощённый smoke-набор сохранён в `evals/golden_cases.smoke.json`, а пример одиночного кейса в `evals/golden_cases.example.json`.

Краткие rationale по starter-кейсам лежат в `evals/STARTER_NOTES.md`.
