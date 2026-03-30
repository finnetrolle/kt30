# Starter Eval Notes

Этот starter-набор нужен как уже подготовленный baseline для офлайн-оценки агентов. Он не заменяет будущий набор из реальных production-case, но позволяет начать измерять качество сразу.

## Состав

- `payments-api-demo`
  Synthetic API case для проверки traceability, оценки часов и базовой структуры.
- `customer-portal-demo`
  Synthetic web-app case со стандартными фазами, чтобы проверять покрытие фаз и несколько требований.
- `analytics-dashboard-demo`
  Lightweight case для низкой сложности, чтобы видеть завышение часов и деградацию структуры на маленьких проектах.
- `ai-kb-chatbot-rfp-real`
  Curated case на основе реального PDF в [uploads/20260213_165118_21e5fc03-2b1c-454c-9011-21f7e9e45206_AI_-_12012026.pdf](/Users/finnetrolle/dev/kt30/uploads/20260213_165118_21e5fc03-2b1c-454c-9011-21f7e9e45206_AI_-_12012026.pdf).

## Реальный кейс: AI KB Chatbot

Из PDF были вручную выделены критичные требования:

- интеграция с Teamly API и учет структуры базы знаний
- RAG-поиск, reranking и генерация ответа строго по KB
- интеграция с Just AI и поддержка контекста диалога
- оценка релевантности/качества ответа и fallback
- инкрементальное обновление индексов по изменениям статей
- работа только в on-prem контуре, поддержка моделей через vLLM

Почему `project_type = "Интеграция"`:

- в проекте сильный упор на интеграционные слои, внешние API и on-prem инфраструктуру
- это значение уже поддерживается baseline-правилами в [data/estimation_rules.json](/Users/finnetrolle/dev/kt30/data/estimation_rules.json)

Почему `total_hours_range = [480, 680]`:

- есть несколько обязательных интеграционных контуров: Teamly, Just AI, RAG, on-prem LLM/vLLM
- в требованиях отдельно акцентированы безопасность, fallback, качество ответа и эксплуатация
- нужен не только MVP-ответ, но и обновление индексов, handover, документация и тестирование quality-scenarios

Что улучшать дальше:

- заменять synthetic cases реальными `analysis_runs`
- сужать диапазоны `total_hours_range` после экспертной калибровки
- добавлять trace-артефакты для `--llm-judge`

## Практический порядок пополнения

1. Прогоните реальный документ через пайплайн и получите `analysis_runs/<run_id>`.
2. Сгенерируйте draft case через [bootstrap_golden_case.py](/Users/finnetrolle/dev/kt30/ops/bootstrap_golden_case.py).
3. Перенесите лучший кейс в [golden_cases.starter.json](/Users/finnetrolle/dev/kt30/evals/golden_cases.starter.json) или отдельный curated-файл.
4. Обновите notes по диапазону часов и критичным требованиям.
