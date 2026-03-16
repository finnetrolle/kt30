# KT30

KT30 - это приложение для анализа технических заданий из `.docx` и `.pdf` с генерацией WBS/ИСР, оценок, рисков и итоговых артефактов через OpenAI-совместимый API.

Текущее состояние проекта:

- Flask backend с headless API
- standalone React/Vite frontend, который считается основным UI
- durable очередь задач на SQLite
- отдельный worker для production и Docker Compose
- SSE-прогресс, история результатов и панель активных задач
- optional password auth, CSRF, rate limiting и базовые security headers

## Что умеет приложение

- загружать `.docx` и `.pdf` файлы размером до 16 МБ
- проверять не только расширение, но и сигнатуру файла
- запускать анализ асинхронно через очередь задач
- показывать живой прогресс анализа через SSE
- восстанавливать in-flight задачу после refresh по `taskId` в URL
- генерировать WBS с фазами, пакетами работ, задачами, зависимостями и оценками
- показывать риски, assumptions, рекомендации и token usage
- хранить результаты и промежуточные артефакты на диске с TTL-cleanup
- экспортировать результат в Excel на backend и в JSON/PDF из frontend
- работать как с OpenAI API, так и с локальными OpenAI-совместимыми LLM

## Архитектура

```text
Browser (/app) or Vite dev server
        |
        v
Flask web/API layer (app.py)
  - upload/auth/results/tasks/health/ready
  - CSRF + rate limits + security headers
  - SSE for task progress
        |
        +--> SQLite job queue + worker heartbeats
        +--> file storage: uploads / analysis_runs / progress_data / results_data / runtime
        |
        v
Worker (embedded in development or separate worker.py in production)
        |
        v
document_parser.py + multi-agent pipeline + OpenAI-compatible API
```

Ключевой нюанс текущей версии: web-процесс больше не выполняет тяжелый анализ синхронно. Он сохраняет upload, ставит задачу в durable queue и отдает `task_id`. Анализ выполняется worker-процессом, а frontend читает устойчивый статус через `/api/tasks/<task_id>` и поток событий через SSE.

## Основные компоненты

- `app.py` - Flask-приложение, API, auth, SSE, health/readiness
- `worker.py` - отдельный entrypoint фонового worker-процесса
- `job_queue.py` - durable SQLite-backed очередь задач
- `job_worker.py` - polling loop и lease/heartbeat логика worker-а
- `analysis_jobs.py` - общий runtime для выполнения analysis job
- `agents/` - multi-agent pipeline для анализа ТЗ и построения WBS
- `frontend/` - основной standalone frontend на React + Vite + TypeScript
- `result_store.py`, `progress_tracker.py`, `run_artifacts.py` - файловое хранение результатов, прогресса и run artifacts
- `ops/` - healthcheck scripts и production runbook
- `deploy/systemd/` - готовые unit-файлы для web и worker

## Требования

- Python 3.12+ рекомендуется
- Node.js 20+ для работы с `frontend/`
- npm для frontend-зависимостей
- OpenAI API key или другой OpenAI-совместимый endpoint

Поддерживаемые форматы входных файлов:

- `.docx`
- `.pdf`

`.doc` сейчас не поддерживается.

## Быстрый старт через Docker Compose

Это основной и самый близкий к production способ локального запуска.

1. Создайте конфиг:

```bash
cp .env.example .env
```

2. Заполните как минимум:

```env
OPENAI_API_KEY=your-key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4
OPENAI_JSON_MODE=true
```

3. Поднимите web + worker:

```bash
docker compose up -d --build
```

4. Откройте:

- UI: `http://localhost:8000/app/`
- health: `http://localhost:8000/health`
- ready: `http://localhost:8000/ready`

Compose-конфигурация уже запускает:

- отдельный `app` сервис
- отдельный `worker` сервис
- встроенный frontend build внутри Docker image
- shared named volumes для `uploads`, `results_data`, `progress_data`, `analysis_runs`, `runtime`

Полезные команды:

```bash
docker compose ps
docker compose logs -f app worker
docker compose down
```

## Локальная разработка

### Вариант 1: backend + встроенный worker + собранный frontend

Подходит, если вы хотите открывать приложение через Flask на `http://localhost:8000/app/`.

1. Установите backend-зависимости:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Установите frontend-зависимости и соберите frontend:

```bash
cd frontend
npm install
npm run build
cd ..
```

3. Создайте `.env`:

```bash
cp .env.example .env
```

4. Запустите backend:

```bash
make run-web
```

По умолчанию в `APP_ENV=development` включен `EMBEDDED_WORKER_ENABLED=true`, поэтому отдельный `worker.py` обычно не нужен.

Важно: если `frontend/dist` не собран и вы не запустили Vite dev server, Flask вернет error page вместо UI.

### Вариант 2: backend + Vite dev server

Подходит для активной работы над frontend.

Терминал 1:

```bash
make run-web
```

Терминал 2:

```bash
cd frontend
npm install
npm run dev
```

Открывайте приложение по адресу `http://localhost:5173/app/`.

Vite проксирует на backend:

- `/api`
- `/health`
- `/ready`

### Вариант 3: production-like локально

Если хотите локально проверить схему с отдельным worker:

```bash
EMBEDDED_WORKER_ENABLED=false make run-web
EMBEDDED_WORKER_ENABLED=false make run-worker
```

Или:

```bash
make run-gunicorn
make run-worker
```

## Frontend в текущем состоянии

`frontend/` больше не просто миграционный черновик. Сейчас там уже основной UI приложения:

- `/app/` - загрузка и отслеживание анализа
- `/app/login` - вход, если включен `APP_AUTH_PASSWORD`
- `/app/tasks` - список активных задач и недавних завершенных работ
- `/app/results` - история сохраненных результатов
- `/app/results/:resultId` - просмотр результата

Frontend умеет:

- восстанавливать задачу по `taskId` после reload
- показывать live progress и fallback на polling для совместимости с браузером
- скачивать Excel, JSON и PDF
- печатать результат
- открывать raw JSON API результата

## Конфигурация

Базовый шаблон находится в `.env.example`.

### Самые важные переменные

| Переменная | Назначение | По умолчанию/заметка |
| --- | --- | --- |
| `APP_ENV` | `development`, `production`, `testing` | `development` |
| `SECRET_KEY` | Flask session secret | в production должен быть задан явно |
| `APP_AUTH_PASSWORD` | включает password auth для UI и API | пустое значение отключает auth |
| `OPENAI_API_KEY` | API key провайдера | обязателен для большинства провайдеров |
| `OPENAI_API_BASE` | базовый URL OpenAI-совместимого API | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | имя модели | в шаблоне `gpt-4` |
| `OPENAI_JSON_MODE` | использовать `response_format=json_object` | для official OpenAI обычно `true`, для local LLM чаще `false` |
| `LLM_PROFILE` | профиль `default` или `small` | `default` |
| `EMBEDDED_WORKER_ENABLED` | запускать worker в процессе web | по умолчанию `true` в development, `false` в production |
| `SERVE_FRONTEND_BUILD` | раздавать `frontend/dist` через Flask | `true` |
| `FRONTEND_DIST_DIR` | путь к production build frontend | `frontend/dist` |
| `FRONTEND_ROUTE_PREFIX` | base path standalone frontend | `app` |
| `MAX_CONTENT_LENGTH` | максимальный размер upload | `16777216` байт |

### Хранилища и runtime

| Переменная | Назначение |
| --- | --- |
| `RUNTIME_DIR` | корень runtime-состояния |
| `UPLOAD_FOLDER` | временные исходные uploads |
| `ARTIFACTS_ROOT` | артефакты каждого analysis run |
| `RESULTS_STORAGE_DIR` | сохраненные результаты |
| `PROGRESS_STORAGE_DIR` | persisted progress и event log |
| `JOB_QUEUE_DB_PATH` | SQLite queue |
| `RATE_LIMIT_DB_PATH` | SQLite rate limiter |

### TTL и cleanup

| Переменная | Что хранит |
| --- | --- |
| `RESULT_TTL_SECONDS` | срок жизни результатов |
| `PROGRESS_TTL_SECONDS` | срок жизни progress state |
| `ARTIFACT_RETENTION_SECONDS` | срок жизни run artifacts |
| `JOB_RETENTION_SECONDS` | срок хранения записей о задачах |
| `JOB_STALE_AFTER_SECONDS` | когда running job считается stale и может быть requeued |
| `WORKER_POLL_INTERVAL_SECONDS` | задержка между poll-итерациями worker-а |

### OpenAI / local LLM примеры

Official OpenAI:

```env
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4
OPENAI_JSON_MODE=true
```

Local LLM без Docker:

```env
OPENAI_API_BASE=http://127.0.0.1:1234/v1
OPENAI_API_KEY=not-needed
OPENAI_MODEL=your-local-model
OPENAI_JSON_MODE=false
LLM_PROFILE=small
```

Local LLM из Docker Compose:

```env
OPENAI_API_BASE=http://host.docker.internal:1234/v1
OPENAI_API_KEY=not-needed
OPENAI_MODEL=your-local-model
OPENAI_JSON_MODE=false
LLM_PROFILE=small
```

## Multi-agent pipeline и режимы работы LLM

Сейчас backend использует multi-agent pipeline как основной путь, а старый single-agent режим остается fallback-механизмом при ошибке orchestration.

Внутри пайплайна уже есть:

- chunked-анализ ТЗ
- параллельная обработка фрагментов
- построение skeleton WBS
- генерация work packages и задач
- валидация и нормализация результата
- сбор token usage и conversation artifacts

### `LLM_PROFILE=small`

Профиль `small` предназначен для локальных и компактных моделей. Он уменьшает размеры chunk-ов и токенные лимиты, снижает параллелизм и по умолчанию отключает часть дорогостоящих LLM-этапов.

### Режимы стабилизации

| Режим | Назначение |
| --- | --- |
| `single` | один проход, минимум стабилизации |
| `validate` | один проход + валидация и нормализация |
| `ensemble` | несколько проходов + консенсус |
| `ensemble_validate` | ensemble + валидация |

Текущий нюанс:

- в `.env.example` указан `STABILIZATION_MODE=validate`
- `ProductionConfig` по умолчанию тянет `ensemble_validate`, если env не переопределяет значение

## Хранение данных

Во время выполнения задачи используются несколько каталогов:

- `uploads/` - исходный временный upload
- `analysis_runs/` - артефакты конкретного запуска, включая копию исходного файла и JSON-артефакты этапов
- `progress_data/` - persisted progress state и SSE events
- `results_data/` - итоговые результаты, доступные через history и result pages
- `runtime/` - SQLite базы очереди и rate limiter

Важный operational detail: для схемы с отдельным `app` и `worker` эти каталоги должны быть общими и writable для обоих процессов.

## HTTP API и маршруты

### UI и compatibility routes

| Route | Что делает |
| --- | --- |
| `/` | redirect в standalone frontend |
| `/login` | compatibility route для логина |
| `/results/<result_id>` | compatibility route результата |
| `/app/*` | основной standalone frontend |

### Auth API

| Endpoint | Method | Описание |
| --- | --- | --- |
| `/api/auth/session` | `GET` | состояние сессии, auth и csrf |
| `/api/auth/csrf` | `GET` | выдает CSRF token |
| `/api/auth/login` | `POST` | логин в API/frontend |
| `/api/auth/logout` | `POST` | logout |

### Upload / tasks

| Endpoint | Method | Описание |
| --- | --- | --- |
| `/api/uploads` | `POST` | основной upload endpoint |
| `/upload` | `POST` | legacy alias upload |
| `/api/tasks/<task_id>` | `GET` | устойчивый статус задачи |
| `/api/tasks/<task_id>/events` | `GET` | SSE поток прогресса |
| `/progress/<task_id>` | `GET` | legacy alias SSE |
| `/api/tasks` | `GET` | операторский список активных задач |
| `/api/tasks/<task_id>/cancel` | `POST` | запрос на отмену задачи |

### Results

| Endpoint | Method | Описание |
| --- | --- | --- |
| `/api/results` | `GET` | история последних результатов |
| `/api/results/<result_id>` | `GET` | результат в JSON |
| `/api/results/<result_id>/export.xlsx` | `GET` | экспорт Excel |
| `/export/excel/<result_id>` | `GET` | legacy alias Excel export |

### Health

| Endpoint | Method | Описание |
| --- | --- | --- |
| `/health` | `GET` | liveness и worker health summary |
| `/ready` | `GET` | readiness с проверкой директорий, SQLite DB и доступности worker-а |

Все небезопасные методы (`POST` и др.) защищены CSRF. Для API-клиента сначала нужно получить токен через `/api/auth/csrf`, затем передавать его в заголовке `X-CSRF-Token`.

## Безопасность в текущей версии

- optional password auth через `APP_AUTH_PASSWORD`
- CSRF protection для всех unsafe request-ов
- basic rate limiting для login, upload, progress и cancel
- security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`
- в production включается `Strict-Transport-Security` для secure request-ов
- проверка file signature для `.docx` и `.pdf`

## Тесты и полезные команды

Backend:

```bash
make compile
make test
make test-all
```

Frontend:

```bash
cd frontend
npm test
npm run test:e2e
```

Примечания:

- backend тесты написаны на `unittest`
- frontend unit/component тесты идут через `Vitest`
- e2e идут через `Playwright`
- текущий Playwright config ожидает локально доступный Chrome channel

Health и smoke:

```bash
python ops/healthcheck_web.py
python ops/healthcheck_worker.py
make smoke
```

Docker и Compose:

```bash
make docker-build
make compose-up
make compose-build
make compose-down
make compose-logs
```

## CI

GitHub Actions в текущем репозитории запускает:

- backend compile check
- backend unit tests
- Docker image build

Frontend тесты пока не входят в корневой CI workflow.

## Production notes

Для production сейчас предусмотрены два основных сценария:

- Docker Compose
- systemd unit-файлы из `deploy/systemd/`

Минимальные требования к production-конфигурации:

- `APP_ENV=production`
- явный `SECRET_KEY`
- `EMBEDDED_WORKER_ENABLED=false`
- запущены и web, и worker
- shared writable storage для `uploads`, `analysis_runs`, `progress_data`, `results_data`, `runtime`

Рекомендуемые проверки после деплоя:

1. `GET /health` возвращает `200`
2. `GET /ready` возвращает `200`
3. `checks.worker_available=true`
4. загружается тестовый `.docx` или `.pdf`
5. результат открывается и скачивается в Excel

Подробности эксплуатации находятся в `ops/RUNBOOK.md`.

## Ограничения текущей архитектуры

- очередь задач и rate limiting сейчас основаны на SQLite и shared filesystem
- это хороший pragmatic вариант для single-host или shared-volume deployment
- для полноценного multi-node production следующим шагом архитектуры будут внешние сервисы вроде Redis/Postgres/object storage

## Структура репозитория

```text
.
├── app.py
├── worker.py
├── analysis_jobs.py
├── job_queue.py
├── job_worker.py
├── config.py
├── openai_client.py
├── document_parser.py
├── result_store.py
├── progress_tracker.py
├── run_artifacts.py
├── agents/
├── frontend/
├── ops/
├── deploy/systemd/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── .env.example
```
