# Marketplace Data Platform

Фундамент платформы данных маркетплейсов: API на FastAPI и PostgreSQL в Docker Compose. На этом этапе API не подключён к базе: `/health` проверяет только доступность процесса API, а отдельный Docker healthcheck проверяет готовность PostgreSQL.

## Требования

- Python 3.12 и [uv](https://docs.astral.sh/uv/) для локальной разработки;
- Docker с Compose для запуска контейнеров;
- Make — необязателен; команды ниже можно запускать напрямую.

## Настройка и запуск

Скопируйте шаблон окружения и замените `POSTGRES_PASSWORD` в `.env` на собственный пароль. Файл `.env` игнорируется Git. Порты и имя базы можно изменить там же. Не помещайте реальные секреты в `.env.example`.

macOS/Linux:

```sh
cp .env.example .env
# Отредактируйте .env, затем:
uv sync --locked
docker compose up --build -d
curl http://localhost:8000/health
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
# Отредактируйте .env, затем:
uv sync --locked
docker compose up --build -d
Invoke-RestMethod http://localhost:8000/health
```

Ожидаемый ответ API: `{"status":"ok"}`. Документация API доступна на `http://localhost:8000/docs`. Проверить состояние контейнеров можно через `docker compose ps`, журналы — через `docker compose logs`.

Для запуска API без Docker после `uv sync`:

```sh
uv run uvicorn api.main:app --reload
```

## Проверки и остановка

Команды одинаковы для PowerShell и macOS/Linux:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
docker compose down
```

Альтернативно используйте `make setup`, `make up`, `make test`, `make lint` и `make down`. На Windows Make может потребовать отдельной установки.

Данные PostgreSQL сохраняются в именованном томе `postgres_data` после `docker compose down`. Изменение учётных данных в `.env` не перенастраивает уже инициализированную базу. Удаление тома через `docker compose down -v` необратимо удалит локальные данные базы.

Каталоги `src/common`, `scripts`, `docs` и `data` зарезервированы для будущей работы. Содержимое `data` игнорируется Git.

## Seller API simulator (этап 2A)

API возвращает только синтетические данные, не содержащие данных клиентов. Набор создаётся в памяти при запуске из фиксированного seed `20261029` и фиксированной начальной даты: 100 товаров, 1000 заказов, 3000 ежедневных снимков остатков и 3000 дневных записей рекламных расходов за 30 дней. Записи воспроизводимы при повторном запуске; PostgreSQL пока не используется симулятором. Цены и расходы указаны в копейках (`*_minor`), валюта — RUB.

Доступны `GET /api/v1/orders`, `/api/v1/products`, `/api/v1/stocks` и `/api/v1/advertising`. У каждого одинаковые параметры:

- `page`: номер страницы от 1, по умолчанию 1;
- `page_size`: от 1 до 100, по умолчанию 50;
- `updated_at`: включительная нижняя граница в формате ISO 8601 с часовым поясом;
- `scenario`: `normal` (по умолчанию), `429`, `500`, `timeout` или `empty`.

Фильтрация выполняется до пагинации. Порядок стабилен: `updated_at` по возрастанию, затем числовой `id`. Ответ содержит `items`, `page`, `page_size`, `total` (число записей после фильтрации) и `next_page` (`null` на последней странице). Страница за пределами набора пуста, при этом `total` остаётся числом подходящих записей. Для инкрементальной загрузки учитывайте, что несколько записей могут иметь одинаковый `updated_at`: граница включительная и такие записи нужно дедуплицировать по ID.

Примеры для macOS/Linux и Windows с установленным `curl` (`curl.exe` в PowerShell):

```sh
curl 'http://localhost:8000/api/v1/orders?page=2&page_size=20'
curl 'http://localhost:8000/api/v1/products?page_size=10'
curl 'http://localhost:8000/api/v1/stocks?updated_at=2025-01-15T00%3A00%3A00Z'
curl 'http://localhost:8000/api/v1/advertising?page_size=5'
curl -i 'http://localhost:8000/api/v1/orders?scenario=429'
curl -i 'http://localhost:8000/api/v1/orders?scenario=500'
curl 'http://localhost:8000/api/v1/orders?scenario=empty'
curl --max-time 1 'http://localhost:8000/api/v1/orders?scenario=timeout'
```

Сценарии задаются отдельно для каждого запроса и доступны на всех четырёх endpoints. `429` возвращает `Retry-After: 1`; `500` — ошибку сервера; `empty` возвращает пустую коллекцию с `total: 0`; `timeout` задерживает обычный ответ на 3 секунды. Последний пример завершится таймаутом клиента через секунду; клиент, ожидающий дольше, получит ответ 200. OpenAPI-схемы и параметры доступны в `/docs` и `/openapi.json`.

## Ingestion в PostgreSQL (этап 2B)

Загрузка реализована на Python, `httpx` и `psycopg`: для четырёх небольших ресурсов прямой контроль транзакций и checkpoint проще проверить, чем добавлять dlt и отдельно согласовывать его state с записью. dlt можно рассмотреть при появлении большего числа источников и требований к нормализации.

Запустите Compose по инструкции выше и задайте переменные в окружении **процесса CLI**. Compose читает `.env` сам, но CLI его автоматически не загружает. Значение `DATABASE_URL` должно соответствовать базе и паролю из `.env`; специальные символы в URL нужно percent-encode. Например, при указанном в шаблоне логине и порте замените `YOUR_PASSWORD` на URL-кодированный пароль:

macOS/Linux:

```sh
export DATABASE_URL='postgresql://marketplace:YOUR_PASSWORD@localhost:5432/marketplace'
export API_BASE_URL='http://localhost:8000'
uv sync --locked
uv run marketplace-ingest
# Можно загрузить только один или несколько ресурсов:
uv run marketplace-ingest --resource orders --resource products --page-size 50 --max-attempts 4 --timeout 5
```

Windows PowerShell:

```powershell
$env:DATABASE_URL = 'postgresql://marketplace:YOUR_PASSWORD@localhost:5432/marketplace'
$env:API_BASE_URL = 'http://localhost:8000'
uv sync --locked
uv run marketplace-ingest
uv run marketplace-ingest --resource orders --resource products --page-size 50 --max-attempts 4 --timeout 5
```

CLI возвращает ненулевой код при ошибке. В логах выводятся `run_id`, ресурс, количество прочитанных записей и длительность; количество включает повторно прочитанные строки и не является числом новых строк. Ошибки API 429 и 5xx, таймауты и ошибки соединения повторяются с ограниченным exponential backoff и jitter; `Retry-After` учитывается в пределах максимальной задержки 10 секунд. Для прочих HTTP-ошибок и некорректного контракта повторов нет.

Данные хранятся в `raw.orders`, `raw.products`, `raw.stocks`, `raw.advertising`: `id`, `updated_at`, исходный `payload` JSONB и время загрузки. Upsert по ID предотвращает дубликаты и не заменяет более новую версию старой. Состояние хранится в `raw.ingestion_state` отдельно для каждого ресурса. При старте используется включительная граница `updated_at`: все записи на границе считываются заново, даже если одинаковое время встречается на разных страницах. Страницы сохраняются транзакционно, но checkpoint продвигается только в одной транзакции с последней страницей после проверки всех страниц. После прерывания повторный запуск начинает с предыдущего checkpoint, повторно записывая уже сохранённые страницы. Для ресурса используется advisory lock, предотвращающий параллельные запуски.

Гарантия корректности основана на контракте симулятора: выборка неизменна во время обхода страниц, сортировка стабильна по `(updated_at, id)`, а источник не добавляет позже записи с timestamp меньше сохранённого checkpoint. API с изменяющимся набором и offset-пагинацией или запоздалыми событиями требует snapshot/keyset-пагинации и политики lookback; текущий код не гарантирует отсутствие пропусков в таком источнике. Проверки метаданных и порядка помогают обнаружить некоторые изменения, но не заменяют snapshot. Пустой успешный ответ не продвигает checkpoint.

### Интеграционные тесты PostgreSQL

Тесты **удаляют схему `raw`** в указанной базе. Используйте исключительно отдельную тестовую базу, никогда рабочую. Например, создайте отдельную базу в локальном экземпляре PostgreSQL, затем задайте `TEST_DATABASE_URL` и выполните `uv run pytest`. Без этой переменной тесты PostgreSQL пропускаются; в GitHub Actions им предоставляется отдельный сервис PostgreSQL. Проверки включают повторную загрузку всех ресурсов, сбой API после первой страницы, ошибку записи последней страницы и одинаковые timestamp на границе checkpoint.

## Аналитические модели dbt (этап 3)

Проект использует `dbt-core` и `dbt-postgres` из группы dev-зависимостей. Сначала запустите API и PostgreSQL и выполните ingestion из раздела выше: dbt читает таблицы `raw.*` и не заполняет их самостоятельно. Схема назначения по умолчанию — `analytics`; созданный пользователь PostgreSQL должен иметь право создавать в ней таблицы и представления.

macOS/Linux (пароль и имя базы должны совпадать с `.env`):

```sh
export POSTGRES_USER='marketplace'
export POSTGRES_PASSWORD='YOUR_PASSWORD'
export POSTGRES_DB='marketplace'
export DBT_HOST='localhost'
export DBT_PORT='5432'
uv sync --locked
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
uv run dbt docs serve --project-dir dbt --profiles-dir dbt
```

Windows PowerShell:

```powershell
$env:POSTGRES_USER = 'marketplace'
$env:POSTGRES_PASSWORD = 'YOUR_PASSWORD'
$env:POSTGRES_DB = 'marketplace'
$env:DBT_HOST = 'localhost'
$env:DBT_PORT = '5432'
uv sync --locked
uv run dbt build --project-dir dbt --profiles-dir dbt
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
uv run dbt docs serve --project-dir dbt --profiles-dir dbt
```

`DBT_SCHEMA` можно переопределить через окружение. Не храните настоящие пароли в коммитах; проектный `profiles.yml` получает их только из переменных. `dbt build` создаёт staging-представления и mart-таблицы и выполняет тесты. Команды `docs` создают и показывают каталог моделей и lineage.

### Метрики и ограничения

- Staging приводит суммы в копейках к RUB. Группировка заказов и снимков по дням использует UTC; дата рекламной записи не содержит часового пояса, поэтому для симулятора принята как отчётная дата UTC. Это допущение, не свойство сторонних API.
- `gross_revenue_rub` — **прокси валовой стоимости заказов**, сумма исходных totals всех заказов по дате создания, включая отменённые. Она не означает признанную бухгалтерскую выручку. `orders_count` считает все ID заказов, включая отменённые; `average_order_value_rub` — эта сумма, делённая на это количество. Источник хранит только последнюю версию заказа, а не историю изменений статуса.
- `net_revenue_rub` всегда `NULL`: источник не содержит возвратов и сумм возмещения, а правило признания выручки и обработки отмен не задано. Нельзя приравнивать его к gross или к сумме неотменённых заказов; для расчёта нужны события возврата/возмещения и согласованные правила их датировки, а также правила отмен. `NULL` не означает ноль возвратов.
- `advertising_spend_rub` — сумма расходов, указанная источником, без предположений о налогах или комиссиях. `attributed_revenue_rub` и `roas` — `NULL`: нет связи заказа с кампанией или правил атрибуции. Расходы продукта без записей в продуктовой витрине показаны как 0 записанного расхода, что не подтверждает полноту источника.
- `stock_coverage_days` — сумма последних известных остатков по складам / среднее число единиц в неотменённых заказах за 30 календарных дней, заканчивающихся на дате самого старого из выбранных снимков. Для этой оценки неотменённый заказ используется как прокси спроса; заказ ещё может быть не доставлен, возвраты не учтены, спрос считается постоянным. Если спрос равен нулю или нет снимка, результат `NULL`. Разные даты последних снимков складов видны в полях `coverage_anchor_date_utc` и `latest_snapshot_date_utc`; сумма может смешивать даты. Оценка предполагает полную историю за окно и не проверяет её полноту; при неполных данных она ненадёжна. Порог риска не задан.

Витрины имеют следующие уровни детализации: день заказа; товар за всю историю; день/товар/кампания; товар с последними снимками складов. Тесты dbt проверяют ключи, обязательные поля, связи, допустимые значения, бизнес-инварианты и сверку агрегатов с источником.

## Операционный слой (этап 4)

После заполнения `.env` запустите `docker compose up --build -d`. Сервисы: API `localhost:8000`, Dagster UI `localhost:3000`, Streamlit `localhost:8501`, PostgreSQL на порту из `.env`. Интерфейсы Dagster и Streamlit привязаны к localhost. В Dagster откройте job `marketplace_job` и запустите его: `marketplace_raw` загружает все ресурсы, затем `marketplace_dbt` выполняет `dbt build` и тесты. Первый запуск необходим до появления моделей на dashboard. История Dagster сохраняется в отдельном томе `dagster_data`.

Фильтры периода и товаров действуют на заказы и рекламные расходы. Остатки — последние известные снимки выбранных товаров; даты периода к ним не применяются. Нет данных по возвратам и атрибуции, поэтому net revenue и ROAS не подменяются нулями. Freshness отображает возраст **успешной загрузки** относительно `FRESHNESS_MAX_HOURS`; source cursor показывается отдельно. Это локальная диагностика, а не production monitoring. Подробнее см. [архитектуру](docs/architecture.md).

### Telegram

По умолчанию `TELEGRAM_ENABLED=false`, поэтому запросы к Telegram не выполняются, даже если токен указан. Уведомления об ошибках Dagster job работают только при `TELEGRAM_ENABLED=true`, заполненных `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` и работающем Dagster daemon/sensor. Перед включением получите явное подтверждение получателя; не коммитьте `.env`. Если переменные не заданы, уведомление пропускается и job не падает из-за этого. Отправка best effort, без гарантии доставки и повторов. Изменив `.env`, пересоздайте Dagster: `docker compose up -d --force-recreate dagster`.

### Демонстрация запуска, сбоя и восстановления

Команды работают из корня проекта в macOS/Linux и PowerShell. Во всех вызовах ниже уведомления принудительно выключены. После `docker compose up --build -d`:

```sh
# Успешный ingestion + dbt build; смотрите результат в Dagster UI и dashboard.
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=normal dagster dagster job execute -m operations.definitions -j marketplace_job
# Симулятор каждый раз возвращает 500: в логах будут ограниченные retry и ошибка job.
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=500 dagster dagster job execute -m operations.definitions -j marketplace_job
# Повторный успешный запуск использует сохранённый checkpoint и upsert.
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=normal dagster dagster job execute -m operations.definitions -j marketplace_job
```

Для `429` замените `500` на `429`; для timeout задайте `SELLER_API_SCENARIO=timeout` и дополнительно `-e SELLER_API_TIMEOUT_SECONDS=1`. Команды со сценарием ошибки возвращают ненулевой код. В Dagster UI доступны статусы и логи; повторы ingestion логируются как `api_retry`. Пример не отправляет реальные сообщения.

### Резервное копирование и восстановление PostgreSQL

Ниже создаётся custom-format dump в контейнере и копируется на хост; это одинаково работает в PowerShell и shell и избегает изменения бинарных данных перенаправлением PowerShell. Храните копию в защищённом месте; данные и пароль в Git не добавляются.

```sh
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/marketplace-backup.dump'
docker compose cp postgres:/tmp/marketplace-backup.dump ./marketplace-backup.dump
docker compose exec -T postgres rm /tmp/marketplace-backup.dump
```

Для проверки восстановления в **новую** базу `marketplace_restore` (команда создания завершится ошибкой, если она уже существует):

```sh
docker compose cp ./marketplace-backup.dump postgres:/tmp/marketplace-restore.dump
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" marketplace_restore'
docker compose exec -T postgres sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d marketplace_restore /tmp/marketplace-restore.dump'
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d marketplace_restore -c "SELECT resource, completed_at FROM raw.ingestion_state ORDER BY resource;"'
docker compose exec -T postgres rm /tmp/marketplace-restore.dump
```

Проверьте восстановленные таблицы и показатели перед переключением приложений на новую базу. Dump не включает роли PostgreSQL и историю Dagster; для неё нужен отдельный согласованный backup тома `dagster_data` при остановленном Dagster. `docker compose down -v` удаляет оба тома и все их данные.
