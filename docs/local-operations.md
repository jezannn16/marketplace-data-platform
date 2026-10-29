# Локальная эксплуатация

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

Документация: [архитектура](architecture.md), [сценарии сбоев](failure-scenarios.md), [AI-разработка](ai-development.md), [интервью](interview.md).
