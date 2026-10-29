# Воспроизводимые сценарии сбоев

Сценарии используют только синтетические данные. Запустите `docker compose up --build -d`; команды выполняются из корня проекта в macOS/Linux или PowerShell. Для всех примеров явно отключён Telegram. Для первых двух сценариев команды ошибки должны завершиться с ненулевым кодом.

## Успех → HTTP 500 → восстановление

```sh
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=normal dagster dagster job execute -m operations.definitions -j marketplace_job
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=500 dagster dagster job execute -m operations.definitions -j marketplace_job
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=normal dagster dagster job execute -m operations.definitions -j marketplace_job
```

Второй запуск должен показать три `api_retry`, завершиться ошибкой после четырёх попыток и не выполнять dbt. Третий повторно читает включительную границу checkpoint и завершает dbt. Результаты запусков и материализации видны в Dagster UI, если сервис и общее хранилище доступны. Для отказа на второй странице и rollback последней страницы существуют отдельные PostgreSQL integration tests; это не то же самое, что процессный kill.

## Rate limit и timeout

```sh
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=429 dagster dagster job execute -m operations.definitions -j marketplace_job
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=timeout -e SELLER_API_TIMEOUT_SECONDS=1 dagster dagster job execute -m operations.definitions -j marketplace_job
```

429 возвращает `Retry-After: 1`; timeout задерживает ответ API на три секунды, а клиент ждёт одну. После ограниченных повторов job завершается ошибкой. Для восстановления выполните нормальную команду из первого сценария. Не используйте `scenario=empty` как доказательство успешности: симулятор специально возвращает пустой успешный ответ, и pipeline не может обнаружить ложную пустоту без дополнительного контракта источника.

## Проверка при недоступной БД и модели

При выключенном PostgreSQL ingestion завершится ошибкой подключения, а dashboard покажет сообщение вместо показателей. Не останавливайте БД с незавершёнными задачами, если данные нужны. При отсутствии построенных dbt-моделей dashboard предлагает сначала загрузить данные и выполнить job.

## Границы восстановления

Неизменность snapshot на протяжении offset-пагинации не гарантируется реальным API. Поздние записи ниже checkpoint или удаления из источника не восстановятся автоматически. Смотри [архитектуру](architecture.md). Backup/restore — отдельная процедура из README; прохождение команд следует проверить в целевой среде.
