# Архитектура Marketplace Data Platform

```text
Seller API (synthetic) → Dagster marketplace_raw → PostgreSQL raw + checkpoint
                                                        ↓
                                       Dagster marketplace_dbt (dbt build)
                                                        ↓
                                         PostgreSQL staging views + marts
                                                        ↓
                                        Streamlit (filters and diagnostics)
Dagster failure sensor → Telegram only when explicitly enabled and configured
```

`marketplace_job` сначала материализует `marketplace_raw`: он вызывает существующий ingestion с retry и транзакционным checkpoint; затем `marketplace_dbt` выполняет `dbt build`. При ошибке ingestion downstream asset не запускается. dbt ошибка или неуспешный тест делает asset и job неуспешными. Запуски, логи, активность sensor и метаданные Dagster хранятся локально в `dagster_data` (по умолчанию SQLite). Compose не настраивает отдельную отказоустойчивую инсталляцию Dagster.

Dashboard берёт фильтруемые показатели из staging и витрин: UTC-дата и товар фильтруют заказы и расходы; таблица остатков показывает последние снимки выбранных товаров и не фильтруется по периоду. Gross и AOV — прокси стоимости заказов, а не признанная выручка. Возвратов и рекламной атрибуции нет, поэтому net revenue и ROAS недоступны. Детали — в README и dbt docs.

Локальная диагностика: dashboard показывает историю Dagster из общего хранилища и время `raw.ingestion_state.completed_at` для каждого ресурса. `FRESHNESS_MAX_HOURS` (24 по умолчанию) определяет статус fresh/stale для последнего завершённого ingestion. Отдельно выводится source cursor: это исторический `updated_at`, а не дата выполнения. Нет проверок отсутствия расписания, SLA, непрерывного мониторинга инфраструктуры или доставки уведомлений; при недоступности базы, Dagster или sensor данные о состоянии могут отсутствовать.

Sensor отслеживает сбои `marketplace_job`. По умолчанию `TELEGRAM_ENABLED=false`; даже при наличии токена уведомления не отправляются. `true` вместе с токеном и chat ID включает отправку через Telegram API; пустая настройка безопасно пропускается. Ошибки отправки логируются без токена и не маскируют исходный сбой job. Уведомления — best effort: гарантии доставки, дедупликации и повторов нет. Не включайте отправку без подтверждения владельца чата.

`postgres_data` хранит только данные PostgreSQL. `dagster_data` хранит локальную историю Dagster; `pg_dump` её не включает. Контейнеры и папки проекта не являются резервными копиями. Инструкции восстановления PostgreSQL приведены в README.
