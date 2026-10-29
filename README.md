# Marketplace Data Platform

Портфолио-проект для локальной демонстрации data engineering в fashion e-commerce. Все данные синтетические: проект не подключён к реальным маркетплейсам и не обрабатывает данные клиентов.

```text
Seller API → ingestion → PostgreSQL raw → dbt staging / marts → Streamlit
                  ↑                               ↑
                  └──────── Dagster job ───────────┘
```

Стек: Python 3.12, FastAPI, PostgreSQL 16, psycopg, httpx, dbt-core/dbt-postgres, Dagster, Streamlit, Docker Compose, uv, pytest и Ruff. Telegram-уведомления опциональны и по умолчанию выключены. dlt не используется: здесь важнее явно контролировать транзакции и checkpoint, чем добавлять ещё один слой state.

## Быстрый запуск

Нужны Docker с Compose, а для локальных тестов — Python 3.12 и [uv](https://docs.astral.sh/uv/). Все команды ниже выполняются из корня проекта. На Windows используйте Docker Desktop с Linux-контейнерами.

macOS/Linux:

```sh
cp .env.example .env
# Замените POSTGRES_PASSWORD в .env на собственный пароль.
docker compose up --build -d
curl http://localhost:8000/health
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
# Замените POSTGRES_PASSWORD в .env на собственный пароль.
docker compose up --build -d
Invoke-RestMethod http://localhost:8000/health
```

В UI Dagster на `http://localhost:3000` запустите `marketplace_job`. Сначала выполняется ingestion, затем `dbt build`. После успешного запуска откройте dashboard на `http://localhost:8501`. При первом открытии до построения моделей dashboard покажет сообщение об ошибке или отсутствии данных. API-документация: `http://localhost:8000/docs`.

По умолчанию все опубликованные порты доступны только на localhost. Это локальная демонстрация: в сервисах нет аутентификации, TLS, изоляции ролей БД и production-оркестрации. Не публикуйте их в интернет. Для остановки используйте `docker compose down`; данные PostgreSQL и история Dagster сохраняются в томах. Изменение пароля в `.env` не меняет пароль пользователя в уже инициализированном томе PostgreSQL. `docker compose down -v` удаляет оба тома и их содержимое.

## Локальный запуск на macOS без Docker

Если Docker Desktop недоступен, можно запустить демонстрацию с установленными Python 3.12, зависимостями проекта и PostgreSQL 16. Скрипт не устанавливает PostgreSQL: `LOCAL_PG_BIN` должен указывать на каталог, содержащий `initdb`, `pg_ctl` и `postgres`. По умолчанию используется `~/.local/share/marketplace-data-platform/postgresql-16/bin`. Сначала создайте `.env` из `.env.example` и задайте собственный `POSTGRES_PASSWORD`, затем:

```sh
uv sync --locked
# При необходимости: export LOCAL_PG_BIN=/путь/к/postgresql/bin
.venv/bin/python scripts/local_macos.py start
```

Скрипт создаёт отдельную локальную базу в `~/.local/share/marketplace-data-platform`, запускает сервисы на localhost и выполняет ingestion с dbt. Тот же каталог содержит логи и историю Dagster. Повторный `start` не завершает чужие процессы; если нужный порт занят, работа останавливается с ошибкой. Для остановки только запущенных скриптом процессов:

```sh
.venv/bin/python scripts/local_macos.py stop
```

После перезагрузки Mac сервисы автоматически не запускаются: повторите `start`. Порт PostgreSQL берётся из `LOCAL_POSTGRES_PORT`, если он указан, иначе из `POSTGRES_PORT`; перед запуском Compose остановите локальный режим, если они используют одинаковые порты. Локальная база и том Compose — разные хранилища. Скрипт не использует `DATABASE_URL` и запускает Dagster из отдельной директории, чтобы `.env` не переопределял локальное подключение; Telegram в этом режиме принудительно выключен. Саму `.env` не отправляйте в Git.

## API и данные

Симулятор создаёт фиксированный набор с seed `20261029`: 100 товаров, 1000 заказов, по 3000 снимков остатков и рекламных записей. `GET /health` проверяет только процесс API. Эндпоинты `/api/v1/orders`, `/products`, `/stocks` и `/advertising` имеют общий префикс `/api/v1`, параметры `page` (от 1), `page_size` (1–100) и `updated_at` (включительная ISO 8601 граница с часовым поясом). Порядок: `(updated_at, id)`. Ответ содержит `items`, `page`, `page_size`, `total`, `next_page`.

```sh
curl 'http://localhost:8000/api/v1/orders?page=1&page_size=10'
curl 'http://localhost:8000/api/v1/stocks?updated_at=2025-01-15T00%3A00%3A00Z'
curl -i 'http://localhost:8000/api/v1/orders?scenario=429'
```

В PowerShell используйте `curl.exe` вместо `curl`. Сценарии сбоев и восстановления описаны в [failure-scenarios.md](docs/failure-scenarios.md).

## Инкрементальная загрузка

`raw.orders`, `raw.products`, `raw.stocks`, `raw.advertising` содержат ID, исходный JSONB и `updated_at`. `raw.ingestion_state` хранит checkpoint каждого ресурса. Каждая страница пишется транзакционно; checkpoint записывается только вместе с последней страницей после проверки всей выборки. При повторном запуске граница включительная, поэтому одинаковые timestamps читаются повторно; upsert по ID не создаёт дубликаты. На ресурс берётся advisory lock. Для 429, 5xx и ошибок транспорта предусмотрены ограниченные повторы с exponential backoff и jitter.

**Граница гарантии:** симулятор возвращает неизменный набор со стабильной сортировкой; новые записи не появляются с `updated_at` меньше checkpoint. Для произвольно изменяющегося API с offset-пагинацией, поздними событиями, удалениями или неполным ответом возможна потеря данных. Перед интеграцией реального источника нужны согласованные snapshot/keyset-пагинация, правила задержки событий и стратегия обработки удалений; этот проект их не реализует.

Для локального запуска CLI настройте переменные окружения процесса; `.env` автоматически читает Compose, но не сам CLI. Значение `DATABASE_URL` должно соответствовать паролю и порту PostgreSQL; специальные символы в URL необходимо percent-encode.

```sh
export DATABASE_URL='postgresql://marketplace:YOUR_PASSWORD@localhost:5432/marketplace'
export API_BASE_URL='http://localhost:8000'
uv sync --locked
uv run marketplace-ingest --resource orders
```

В PowerShell вместо `export` используйте `$env:DATABASE_URL = '...'` и `$env:API_BASE_URL = 'http://localhost:8000'`. Можно опустить `--resource`, чтобы загрузить все ресурсы. Команды `make setup`, `up`, `down`, `test`, `lint` доступны при установленном Make.

## Модели и метрики

Staging-модели читают `raw`, а витрины агрегируют дневные продажи, результаты товара, рекламные записи и остатки. Суммы в исходных копейках переведены в RUB; даты заказов и снимков группируются по UTC. Дата рекламной записи принимается за UTC по соглашению симулятора.

- `gross_revenue_rub` — **прокси валовой стоимости всех заказов**, включая отменённые, а не признанная выручка. `orders_count` считает все ID, AOV — эта сумма / число заказов.
- `net_revenue_rub` — `NULL`: возвратов и правил признания/отмен в источнике нет. `NULL` не означает нулевые возвраты.
- Расходы на рекламу — суммы из источника; атрибуции заказов к кампаниям нет, поэтому `roas` и attributed revenue — `NULL`.
- Stock coverage = последние известные остатки / средние неотменённые заказанные единицы за 30 календарных дней. Это оценка при условии полной истории и постоянного спроса, а не прогноз. При нулевом спросе, отсутствии снимка или разных датах последних снимков складов coverage — `NULL`. Разные даты складов и неполнота окна требуют внимания; суммы остатков могут объединять снимки разных дат.

На dashboard период и товар фильтруют заказы и рекламные расходы; остатки — последние снимки выбранных товаров и не фильтруются по периоду. Подробнее — в dbt docs и [архитектуре](docs/architecture.md).

## Проверки и dbt

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

PostgreSQL-интеграционные тесты пропускаются без `TEST_DATABASE_URL`. Они **удаляют схемы `raw` и `analytics`** в указанной базе; используйте только отдельную тестовую базу. Для снижения риска имя базы должно содержать отдельный сегмент `test`, например `marketplace_test`. Проверка имени не заменяет изоляцию базы.

После загрузки данных для локального dbt задайте `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, при необходимости `DBT_HOST`, `DBT_PORT`, `DBT_SCHEMA` в окружении и выполните:

```sh
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
uv run dbt docs serve --project-dir dbt --profiles-dir dbt
```

GitHub Actions выполняет lint, pytest с отдельной PostgreSQL-базой, ingestion, dbt, Dagster и Streamlit; отдельный job проверяет Compose. Локальная команда `docker compose config --quiet` проверяет синтаксис и подстановку, но не сборку или запуск контейнеров.

## Локальный мониторинг и уведомления

Dashboard показывает недавние запуски из локального хранилища Dagster и возраст последней успешной загрузки по ресурсу. `FRESHNESS_MAX_HOURS` задаёт порог этого возраста, отдельно показывается исторический cursor источника. Расписания, внешнего сбора метрик, SLA и гарантированной доставки уведомлений нет.

`TELEGRAM_ENABLED=false` по умолчанию: запросы к Telegram не выполняются даже при наличии токена. Для включения после согласия получателя задайте `TELEGRAM_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` в `.env` и пересоздайте Dagster. Sensor отправляет уведомления best effort при ошибке `marketplace_job`; отсутствие настроек безопасно пропускается. Настоящие сообщения в проверках не отправляются.

## Резервное копирование PostgreSQL

Команды создают бинарный dump внутри контейнера и копируют его на хост без перенаправления PowerShell. Храните резервную копию отдельно и защищённо; `.dump` игнорируется Git.

```sh
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/marketplace-backup.dump'
docker compose cp postgres:/tmp/marketplace-backup.dump ./marketplace-backup.dump
docker compose exec -T postgres rm /tmp/marketplace-backup.dump
```

Восстановление для проверки в **новую** базу `marketplace_restore`:

```sh
docker compose cp ./marketplace-backup.dump postgres:/tmp/marketplace-restore.dump
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" marketplace_restore'
docker compose exec -T postgres sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d marketplace_restore /tmp/marketplace-restore.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d marketplace_restore -c "SELECT resource, completed_at FROM raw.ingestion_state ORDER BY resource;"'
docker compose exec -T postgres rm /tmp/marketplace-restore.dump
```

Проверьте восстановленные таблицы до переключения приложений. Dump не включает роли PostgreSQL и историю Dagster; для последней нужен отдельный согласованный backup тома `dagster_data` при остановленном Dagster. Этот сценарий требует отдельной проверки восстановления в вашей среде.

Документация: [архитектура](docs/architecture.md), [сценарии сбоев](docs/failure-scenarios.md), [AI-разработка](docs/ai-development.md), [интервью](docs/interview.md).
