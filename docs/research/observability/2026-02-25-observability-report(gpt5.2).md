1

# Observability & Monitoring Report (Telegram Voice2Text Bot)

Дата: 2026-02-25

## Контекст
- Production Telegram Voice2Text Bot, запущен на VPS в Docker Compose.
- Ресурсы VPS: 2 CPU, 4 GB RAM, 30 GB disk.
- База данных: SQLite.
- Сейчас есть:
  - healthcheck (DB connectivity + Alembic HEAD) через `python -m src.health_check`
  - структурированные JSON-логи в файлы `./logs/app.log` и `./logs/errors.log` с ротацией.
- Сейчас нет: Grafana/Prometheus, централизованного поиска логов, алертинга, трейсинга.
- В БД уже сохраняются метаданные для бизнес-метрик (длительность аудио, время обработки, варианты кнопок и т.д.).

## Цели observability
### Технические (SRE)
1. Быстро понять: сервис жив/не жив, не в CrashLoop.
2. Контроль ресурсов: CPU/RAM/Disk/Network, рестарты контейнеров.
3. Производительность: время обработки пайплайна и его стадий.
4. Надёжность: error rate по ключевым операциям (Telegram API, STT, SQLite, ffmpeg).
5. Очередь: глубина, inflight, оценка времени ожидания.

### Бизнес
1. Активность: DAU/WAU, new users.
2. Объём: количество транскрибаций, суммарные минуты/секунды аудио.
3. Успешность: success/fail транскрибаций.
4. Фичи: использование интерактивных кнопок (variants/mode/levels/timestamps).
5. Расходы: cost/day (по тарифу STT), cost per transcription, cost per active user.

## Варианты стека (реалистично для одной VPS)

### Вариант A — Минимальный (быстрый ROI)
**Компоненты**
- Sentry (ошибки + базовый performance)
- Логи остаются файловыми (как сейчас)
- Внешний uptime check (Healthchecks.io/UptimeRobot) на healthcheck

**Плюсы**
- Почти нулевая нагрузка на VPS
- Очень быстрый запуск и высокая практическая ценность по ошибкам

**Минусы**
- Слабая видимость системных метрик/ресурсов и очереди
- Нет нормального поиска по логам/корреляции

**Когда подходит**
- Нужно «включить фары» за вечер без дополнительной инфраструктуры.

---

### Вариант B — Рекомендованный (баланс)
**Компоненты (Docker Compose на VPS)**
- Grafana (дашборды + алерты)
- Prometheus (метрики)
- Loki + promtail (централизованный поиск по JSON-логам)
- node_exporter (метрики хоста)
- cAdvisor (метрики контейнеров)
- Sentry (ошибки, как отдельный «канал тревоги»)

**Плюсы**
- Метрики + логи + алерты + дашборды закрывают 80–90% потребностей
- Максимально использует текущие сильные стороны проекта (JSON-логи и данные в SQLite)
- Реально удержать в 4 GB RAM при разумной ретенции

**Минусы**
- Несколько сервисов (нужно поддерживать и следить за диском)
- Нужно аккуратно задавать ретенцию Loki/Prometheus (диск 30 GB)

**Когда подходит**
- Нужна полноценная эксплуатационная панель и алертинг на одной VPS.

---

### Вариант C — Расширенный (полный observability, сложнее)
**Компоненты**
- Полный LGTM: Grafana + Prometheus + Loki + Tempo
- OpenTelemetry Collector как «хаб» (OTLP ingest + routing)

**Плюсы**
- Полная корреляция: метрики ↔ логи ↔ трейсы
- Лучший дебаг производительности по стадиям пайплайна

**Минусы**
- Больше операционной сложности
- На 2 CPU/4GB легко начать конкурировать с ботом за ресурсы

**Когда подходит**
- Когда уже есть стабильный мониторинг (вариант B) и хочется глубже понять latency/узкие места.

## Рекомендация
Рекомендуемый путь: **Вариант B (Grafana + Prometheus + Loki) + Sentry**.

- Sentry остаётся лучшим источником «ошибок разработчикам».
- Loki даёт быстрый выигрыш, потому что у проекта уже есть структурированные JSON-логи.
- Prometheus + exporters дадут контроль ресурсов и ключевые метрики очереди/latency.
- Трейсинг (Tempo/OTel) добавлять поэтапно после MVP метрик+логов.

## Что собирать (MVP набор)

### Метрики приложения (без высокой кардинальности)
**Очередь / нагрузка**
- `bot_updates_received_total`
- `bot_voice_received_total`
- `queue_depth` (gauge)
- `inflight` (gauge)

**Качество и скорость**
- `transcriptions_total{result="success|fail"}`
- `pipeline_duration_seconds` (histogram, end-to-end)
- `stt_duration_seconds` (histogram)

**Внешние зависимости**
- `telegram_api_errors_total`
- `openai_api_errors_total`

**SQLite**
- `db_errors_total{type="locked|other"}`
- `db_query_duration_seconds` (histogram; labels только `operation/table`, без SQL)

### Логи
- Продолжить писать JSON в файлы.
- Добавить (по возможности) поля корреляции: `request_id`/`usage_id` и далее `trace_id` (когда будет OTel).
- Выделить `event` (machine-friendly), например: `update_received`, `stt_started`, `stt_finished`, `db_locked`, `telegram_send_failed`.

### Алерты (MVP, чтобы не шумели)
- Disk free < 15% (или < 5 GB)
- Container restarts > 3 за 10 минут
- Error rate транскрибаций > 5% за 15 минут
- p95 `stt_duration_seconds` > 25–30s за 15 минут
- `queue_depth` > 10 за 10 минут (и растёт)

### Дашборды (MVP)
1. **Overview**: health, CPU/RAM/Disk, success rate, p95 STT, очередь.
2. **STT pipeline**: распределение latency (p50/p95), ошибки/ретраи.
3. **Logs**: последние ERROR + фильтры по `event`/`level`.

## Поэтапный план внедрения

### Этап 1 — Централизовать логи (быстрый эффект)
- Поднять Loki + promtail
- Настроить promtail на чтение `./logs/app.log` и `./logs/errors.log` (JSON parsing)
- Поднять Grafana, подключить Loki datasource

**Готово, если:** можно за 30 секунд найти любой инцидент по логам и понять причину.

### Этап 2 — Метрики и алертинг
- Поднять Prometheus + node_exporter + cAdvisor
- Добавить `/metrics` endpoint в приложение (Prometheus client) и базовые метрики очереди/latency/success
- В Grafana собрать Overview дашборд + алерты

**Готово, если:** видно деградацию latency/error rate/ресурсов до жалоб пользователей.

### Этап 3 — Трейсинг (опционально)
- Добавить OpenTelemetry instrumentation и корреляцию trace_id в логи
- Выбрать: Tempo (self-hosted) или tracing в Sentry

**Готово, если:** можно разложить latency на стадии (download → STT → DB → reply).

## Ограничения и правила (важно)
- 30GB диск: обязательно ограничить ретенцию Prometheus/Loki (например 7–14 дней) и лимиты логов.
- Не использовать `user_id/chat_id/message_id` как label в Prometheus (взорвёт кардинальность).
- SQLite: мониторить `database is locked` и общую latency DB — это частая причина деградаций.
