# KT30 Production Runbook

## Topology

- `web`: Flask + Gunicorn, принимает upload/API/SSE запросы.
- `worker`: отдельный процесс `python worker.py`, забирает задачи из SQLite queue.
- Shared storage нужен для `uploads`, `progress_data`, `results_data`, `analysis_runs`, `runtime`.

## Required Environment

- `APP_ENV=production`
- `SECRET_KEY` задан явно
- `OPENAI_API_KEY` задан
- `EMBEDDED_WORKER_ENABLED=false`
- `JOB_QUEUE_DB_PATH`, `RATE_LIMIT_DB_PATH`, `UPLOAD_FOLDER`, `RESULTS_STORAGE_DIR`, `PROGRESS_STORAGE_DIR`, `ARTIFACTS_ROOT`, `RUNTIME_DIR` указывают на shared writable storage

## Pre-Go-Live Checks

1. Проверить, что `GET /health` отвечает `200`.
2. Проверить, что `GET /ready` отвечает `200` и `checks.worker_available=true`.
3. Прогнать `make test-all`.
4. Загрузить тестовый `pdf` или `docx`, дождаться завершения и скачать `Excel`.
5. Проверить, что worker heartbeat обновляется в `runtime/job_queue.sqlite3`.

## Deployment

### Docker Compose

1. Обновить `.env`.
2. Выполнить `docker compose up -d --build`.
3. Проверить `docker compose ps`.
4. Проверить логи `docker compose logs -f app worker`.

### systemd

1. Разместить код в `/opt/kt30/current`.
2. Создать пользователя `kt30`.
3. Подготовить `/etc/kt30/kt30.env` по шаблону `deploy/systemd/kt30.env.example`.
4. Установить юниты из `deploy/systemd/`.
5. Выполнить `systemctl daemon-reload && systemctl enable --now kt30-web kt30-worker`.

## Smoke Test

1. Открыть главную страницу.
2. Выполнить логин, если включён `APP_AUTH_PASSWORD`.
3. Загрузить документ размером 1-2 MB.
4. Убедиться, что `/api/tasks/<task_id>` проходит статусы `queued -> running -> succeeded`.
5. Открыть `/results/<result_id>`.
6. Скачать `JSON` и `Excel`.

## Incident Response

### `/ready` возвращает `503`

- Проверить `checks` в payload ответа.
- Если `worker_available=false`, проверить worker container/service и heartbeat в `worker_heartbeats`.
- Если отсутствует `job_queue_db` или `rate_limit_db`, проверить права на shared storage.

### Задачи застряли в `queued`

- Проверить, запущен ли worker.
- Проверить логи worker.
- Проверить, что `WORKER_ID` уникален и heartbeat обновляется.
- При необходимости перезапустить worker: stale jobs автоматически вернутся в очередь после `JOB_STALE_AFTER_SECONDS`.

### Задачи застряли в `running`

- Проверить heartbeat worker.
- Проверить, не завис внешний LLM endpoint.
- При падении worker stale jobs будут requeue автоматически.
- Если задача больше не нужна, вызвать `POST /api/tasks/<task_id>/cancel`.

### Ошибки загрузки файла

- Проверить MIME/signature mismatch.
- Проверить `MAX_CONTENT_LENGTH`.
- Проверить права записи в `UPLOAD_FOLDER`.

### Ошибки OpenAI/LLM

- Проверить `OPENAI_API_BASE`, `OPENAI_MODEL`, `OPENAI_API_KEY`.
- Проверить сетевую доступность провайдера.
- Повторить задачу после восстановления провайдера.

### Диск заполняется

- Проверить retention значения `RESULT_TTL_SECONDS`, `PROGRESS_TTL_SECONDS`, `ARTIFACT_RETENTION_SECONDS`, `JOB_RETENTION_SECONDS`.
- Очистить устаревшие артефакты и результаты.
- Убедиться, что volume имеет запас по месту.

## Rollback

1. Остановить rollout нового web/worker.
2. Вернуть предыдущий image/tag.
3. Поднять предыдущие web и worker вместе.
4. Проверить `GET /ready`.
5. Прогнать smoke test.

## Backups

- Backup shared storage минимум для `results_data`, `analysis_runs`, `runtime`.
- Проверять восстановление из backup на staging.

## Operational Notes

- В текущей версии queue и rate limiting основаны на SQLite и shared filesystem.
- Для multi-node production следующая эволюция архитектуры: `Redis/Postgres/S3`.
