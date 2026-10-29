# Demo: от API до dashboard

Сценарий использует только синтетические данные и локальные сервисы. Перед началом выполните [Quickstart](../README.md#quickstart), заменив пароль в `.env`. Команды запускайте из корня проекта; в PowerShell используйте `curl.exe`.

## 1. Проверить источник

```sh
curl http://localhost:8000/health
curl 'http://localhost:8000/api/v1/orders?page=1&page_size=2'
```

Первый ответ — `{"status":"ok"}`. Второй содержит `items`, `page`, `page_size`, `total` и `next_page`. В наборе симулятора 1 000 заказов, 100 товаров, 3 000 снимков остатков и 3 000 рекламных записей. Интерактивные схемы и параметры находятся в [API docs](http://localhost:8000/docs).

## 2. Загрузить данные и построить витрины

Откройте [Dagster](http://localhost:3000), выберите и запустите `marketplace_job`. После успешного выполнения загрузки и dbt build статус запуска — `SUCCESS`. Либо выполните:

```sh
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false dagster dagster job execute -m operations.definitions -j marketplace_job
```

В логах успешного выполнения видны `Ingestion completed` и результат `dbt build`. Откройте [dashboard](http://localhost:8501): карточки, графики продаж и расходов, топ товаров и оценка запаса в днях появятся после построения моделей. Фильтры периода и товара применяются к продажам и рекламе; период не меняет последние снимки остатков. Данные в demo не являются реальными заказами или расходами.

## 3. Повторить загрузку

Повторите команду из предыдущего шага. Upsert не должен создавать дубликаты. Проверить количество уникальных заказов:

```sh
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) AS rows, count(DISTINCT id) AS unique_ids FROM raw.orders;"'
```

Для неизменённого набора оба значения — 1 000. Интеграционный тест проверяет все четыре ресурса, а также совпадение checkpoint до и после повтора.

## 4. Сымитировать ошибку и восстановление

```sh
curl -i 'http://localhost:8000/api/v1/orders?scenario=429'
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=500 dagster dagster job execute -m operations.definitions -j marketplace_job
docker compose run --rm --no-deps -e TELEGRAM_ENABLED=false -e SELLER_API_SCENARIO=normal dagster dagster job execute -m operations.definitions -j marketplace_job
```

Первый запрос отвечает HTTP 429. Второй job должен завершиться ошибкой после ограниченных retry, без dbt; последний должен завершиться успешно. Подробности, включая timeout и ограничения симуляции пустого ответа, — в [сценариях сбоев](failure-scenarios.md). Показанный сценарий не имитирует принудительное завершение процесса.

## 5. Понимать показатели

Стоимость заказов включает отмены и не равна признанной выручке. Net revenue отсутствует без возвратов, ROAS — без атрибуции. Запас в днях — оценка по среднему спросу за 30 дней, не прогноз. Области применения и ограничения приведены в [архитектуре](architecture.md).
