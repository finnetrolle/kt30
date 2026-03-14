# План миграции на отдельный frontend

Статус: planned

Дата фиксации: 2026-03-14

## Цель

Перевести текущий встроенный frontend на отдельное приложение в каталоге `frontend/` на базе:

- TypeScript
- Vite
- React 19
- TanStack Router
- TanStack Query
- Zod
- Vitest
- Playwright

При этом backend на Flask должен остаться источником бизнес-логики, очередей, SSE-прогресса, экспорта и работы с файлами.

## Почему идем этим путем

Сейчас проект уже близок к headless/BFF-модели:

- загрузка документа уже работает как API
- прогресс анализа уже отдается через SSE
- результаты уже доступны в JSON
- экспорт Excel уже выделен в отдельный endpoint

Главная задача миграции не в переписывании backend-логики, а в:

- переводе auth и CSRF из template-режима в API-режим
- выравнивании JSON-контрактов
- переносе UI на отдельный React-клиент

## Целевая архитектура

### Backend

Flask остается backend/BFF и отвечает за:

- аутентификацию
- прием файлов
- постановку задач в очередь
- SSE / статус длительных задач
- выдачу результатов анализа
- экспорт файлов

### Frontend

Отдельное приложение `frontend/` отвечает за:

- login/logout
- upload flow
- отображение live progress
- страницу результатов
- экспорт и клиентский UX

### Принцип интеграции

На первом этапе frontend живет в том же репозитории, но как отдельное приложение.

В production предпочтителен same-origin сценарий:

- frontend отдается как статическая сборка
- `/api/*` и SSE проксируются на Flask

Cross-origin допускается только как dev-режим при необходимости.

## Ограничения и принципы

- Не переносить бизнес-логику расчета WBS, duration и dependencies на frontend
- Не выносить frontend в отдельный репозиторий до стабилизации API
- Не удалять старый UI до достижения полного feature parity
- Сначала переносим сценарии, потом улучшаем визуальную часть
- Контракты API должны быть типизированы и валидируемы на frontend

## Этапы реализации

## Этап 1. Зафиксировать текущий контракт и сценарии

Цель: описать текущее поведение системы и определить минимальный scope миграции.

Задачи:

- зафиксировать пользовательские сценарии `login -> upload -> progress -> results -> export`
- описать существующие endpoints и payload'ы
- зафиксировать все SSE events и их форму
- определить, какие поля сейчас считаются только в HTML route
- составить список обязательного feature parity

Результат:

- короткий migration contract doc
- список обязательных экранов и сценариев

## Этап 2. Подготовить backend к standalone frontend

Цель: сделать backend независимым от `templates/` для основных пользовательских сценариев.

Задачи:

- перевести auth в API-формат
- добавить endpoint получения текущей сессии
- добавить endpoint получения CSRF token для API-клиента
- привести logout к API-формату
- унифицировать JSON-ошибки для `401`, `403`, `404`, `429`, `500`
- сделать единый JSON view-model для результатов анализа
- перенести SSE под единый API namespace
- при необходимости добавить dev-only CORS

Желаемый API-контур:

- `GET /api/auth/session`
- `GET /api/auth/csrf`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/uploads`
- `GET /api/tasks/:taskId`
- `POST /api/tasks/:taskId/cancel`
- `GET /api/tasks/:taskId/events`
- `GET /api/results/:resultId`
- `GET /api/results/:resultId/export.xlsx`

Результат:

- backend становится пригодным для отдельного frontend без server-rendered страниц

## Этап 3. Поднять каркас нового frontend

Цель: создать отдельное frontend-приложение внутри текущего репозитория.

Задачи:

- создать каталог `frontend/`
- инициализировать `TypeScript + Vite + React`
- подключить `TanStack Router`
- подключить `TanStack Query`
- подключить `Zod`
- настроить структуру проекта
- настроить dev proxy на Flask backend
- настроить базовый layout, routes и API client

Целевая структура:

- `frontend/src/app`
- `frontend/src/routes`
- `frontend/src/features/auth`
- `frontend/src/features/upload-spec`
- `frontend/src/features/task-progress`
- `frontend/src/features/result-view`
- `frontend/src/entities/task`
- `frontend/src/entities/result`
- `frontend/src/shared/api`
- `frontend/src/shared/ui`

Результат:

- отдельное frontend-приложение собрано и подключено к backend API

## Этап 4. Перенести login, upload и progress

Цель: новый frontend должен уметь запускать анализ без использования legacy UI.

Задачи:

- реализовать экран логина
- реализовать загрузку файла
- реализовать клиентскую валидацию файла
- реализовать запуск анализа
- реализовать подписку на SSE
- реализовать live progress log
- реализовать cancel task
- обработать разрывы соединения и ошибки авторизации

Критерий готовности:

- пользователь может полностью запустить анализ из нового frontend

## Этап 5. Перенести экран результатов

Цель: новый frontend должен полностью закрывать сценарий просмотра результата.

Задачи:

- реализовать route результатов
- показать project info
- показать token usage
- показать WBS phases, work packages и tasks
- показать dependencies view
- реализовать export JSON
- реализовать export Excel

Критерий готовности:

- новый frontend функционально покрывает текущую страницу результатов

## Этап 6. Тесты, доставка и переключение

Цель: подготовить безопасный вывод нового frontend в эксплуатацию.

Задачи:

- настроить unit tests на `Vitest`
- настроить e2e на `Playwright`
- покрыть сценарии `login -> upload -> progress -> results -> export`
- настроить production build и раздачу статики
- настроить proxy для `/api/*` и SSE
- провести smoke test на staging или локальном production-like окружении
- переключить пользователей на новый frontend
- удалить legacy templates/static UI после стабилизации

Результат:

- standalone frontend введен в эксплуатацию

## Milestones

- Milestone 1: backend готов для standalone frontend
- Milestone 2: новый frontend умеет login + upload + progress
- Milestone 3: новый frontend умеет results + export
- Milestone 4: legacy UI выключен

## Definition of Done

Миграцию считаем завершенной, когда:

- все основные пользовательские сценарии работают через `frontend/`
- backend не зависит от `templates/` для основных flows
- новые API-контракты стабилизированы и покрыты тестами
- production использует новый frontend
- старые `templates/` и `static/js` больше не участвуют в пользовательском сценарии

## Что делаем первым

При следующем заходе начинаем с Этапа 2.

Первый практический набор задач:

- описать текущий API-контракт в документе
- спроектировать API для auth/session/csrf
- привести `/api/results/:id` к полному view-model
- определить финальный namespace для SSE и uploads

## Примечание

До завершения migration phase старый UI сохраняем как fallback и не удаляем преждевременно.
