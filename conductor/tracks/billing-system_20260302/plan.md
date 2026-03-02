# Implementation Plan: Billing System (Tarification)

**Track ID:** billing-system_20260302
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-02
**Status:** [x] Complete

## Overview

Реализация системы тарификации в 10 фазах: от моделей БД до интеграции платёжных провайдеров. Каждая фаза независимо верифицируема. TDD-подход: тесты перед реализацией.

---

## Phase 1: Database Models & Migrations

Создание новых таблиц для системы тарификации и расширение существующей модели User.

### Tasks

- [x] Task 1.1: Написать тесты для новых моделей БД (billing_conditions, subscription_tiers, subscription_prices, user_subscriptions, minute_packages, user_minute_balances, daily_usage, purchases, deduction_log)
- [x] Task 1.2: Создать SQLAlchemy-модели в `src/storage/models.py`:
  - `BillingCondition` — общие и индивидуальные условия (key, value, user_id nullable, valid_from, valid_to)
  - `SubscriptionTier` — уровни подписки (name, daily_limit_minutes, description, display_order, is_active)
  - `SubscriptionPrice` — цены (tier_id, period: week/month/year, amount_rub, amount_stars, is_active)
  - `UserSubscription` — подписки пользователей (user_id, tier_id, period, started_at, expires_at, auto_renew, payment_provider, next_subscription_tier_id, status)
  - `MinutePackage` — каталог пакетов (name, minutes, price_rub, price_stars, display_order, is_active)
  - `UserMinuteBalance` — балансы (user_id, balance_type: bonus/package, minutes_remaining, expires_at nullable, source_description)
  - `DailyUsage` — дневное использование (user_id, date, minutes_used, minutes_from_daily, minutes_from_bonus, minutes_from_package)
  - `Purchase` — история покупок (user_id, purchase_type: package/subscription, item_id, amount, currency, payment_provider, provider_transaction_id, status, created_at, completed_at)
  - `DeductionLog` — лог списания (user_id, usage_id, source_type, source_id, minutes_deducted, created_at)
- [x] Task 1.3: Создать Alembic-миграцию для новых таблиц
- [x] Task 1.4: Добавить `BILLING_ENABLED` в `src/config.py`, `.env.example`, `.env.example.short`, `.github/workflows/deploy.yml`
- [x] Task 1.5: Добавить `BILLING_LIMIT_WARNING_THRESHOLD` (default=0.8) в config

### Verification

- [x] Все тесты моделей проходят
- [x] Миграция применяется и откатывается без ошибок
- [x] mypy проходит без ошибок

---

## Phase 2: Billing Repositories

Создание репозиториев для доступа к новым таблицам.

### Tasks

- [x] Task 2.1: Написать тесты для `BillingConditionRepository` (CRUD, получение условий с приоритетом индивидуальных, фильтрация по valid_from/valid_to)
- [x] Task 2.2: Написать тесты для `SubscriptionRepository` (CRUD тиров, цен, подписок пользователей, проверка активной подписки)
- [x] Task 2.3: Написать тесты для `MinutePackageRepository` (CRUD, каталог активных пакетов)
- [x] Task 2.4: Написать тесты для `UserMinuteBalanceRepository` (CRUD, списание минут по приоритету, проверка баланса)
- [x] Task 2.5: Написать тесты для `DailyUsageRepository` и `DeductionLogRepository`
- [x] Task 2.6: Написать тесты для `PurchaseRepository`
- [x] Task 2.7: Реализовать `BillingConditionRepository` в `src/storage/repositories.py` (или отдельный файл `src/storage/billing_repositories.py`)
- [x] Task 2.8: Реализовать `SubscriptionRepository`
- [x] Task 2.9: Реализовать `MinutePackageRepository`
- [x] Task 2.10: Реализовать `UserMinuteBalanceRepository`
- [x] Task 2.11: Реализовать `DailyUsageRepository`, `DeductionLogRepository`, `PurchaseRepository`

### Verification

- [x] Все тесты репозиториев проходят
- [x] mypy проходит без ошибок

---

## Phase 3: Billing Service Core

Ядро биллинга: проверка лимитов, списание минут, получение балансов.

### Tasks

- [x] Task 3.1: Написать тесты для `BillingService`:
  - `get_user_daily_limit(user_id)` — возвращает дневной лимит (индивидуальный или общий, с учётом подписки)
  - `get_user_balance(user_id)` — возвращает полный баланс (дневной остаток, бонусные, пакетные)
  - `check_can_transcribe(user_id, duration_minutes)` — проверка достаточности минут
  - `deduct_minutes(user_id, usage_id, duration_minutes)` — списание с размазыванием по источникам
  - `get_daily_usage(user_id, date)` — получение дневного использования
  - `reset_daily_usage(user_id)` — сброс дневного использования (00:00 MSK)
- [x] Task 3.2: Написать тесты для округления до десятых долей минуты
- [x] Task 3.3: Написать тесты для размазывания минут между источниками (дневной → бонус → пакет)
- [x] Task 3.4: Написать тесты для сценариев: подписка заменяет (не суммирует) дневной лимит
- [x] Task 3.5: Реализовать `BillingService` в `src/services/billing_service.py`
- [x] Task 3.6: Написать тесты для уведомлений о приближении к лимиту (80%+ порог)
- [x] Task 3.7: Реализовать логику уведомлений в `BillingService`

### Verification

- [x] Все тесты BillingService проходят
- [x] Корректное размазывание минут между источниками
- [x] Корректная работа с подпиской (замена, а не суммирование дневного лимита)
- [x] mypy проходит без ошибок

---

## Phase 4: Subscription Service

Управление подписками: создание, продление, отмена, upgrade/downgrade.

### Tasks

- [x] Task 4.1: Написать тесты для `SubscriptionService`:
  - `get_available_tiers()` — каталог доступных уровней подписки
  - `get_tier_prices(tier_id)` — цены для конкретного уровня
  - `create_subscription(user_id, tier_id, period, payment_provider)` — создание подписки
  - `cancel_subscription(user_id)` — отмена (действует до конца периода)
  - `renew_subscription(subscription_id)` — продление
  - `check_expired_subscriptions()` — проверка истёкших подписок
  - `handle_upgrade(user_id, new_tier_id, new_period)` — немедленный upgrade
  - `handle_downgrade(user_id, new_tier_id)` — downgrade при следующем продлении
- [x] Task 4.2: Написать тесты для логики next_subscription_tier_id
- [x] Task 4.3: Написать тесты для напоминания об истечении (за 3 дня для Telegram Stars)
- [x] Task 4.4: Реализовать `SubscriptionService` в `src/services/subscription_service.py`

### Verification

- [x] Все тесты SubscriptionService проходят
- [x] Upgrade применяется немедленно
- [x] Downgrade сохраняется в next_subscription_tier_id
- [x] Отмена: подписка действует до конца периода
- [x] mypy проходит без ошибок

---

## Phase 5: Welcome Bonus & Grace Period

Механизм welcome-бонуса для новых пользователей и грейс-периода для существующих.

### Tasks

- [x] Task 5.1: Написать тесты для начисления welcome-бонуса при `/start`
- [x] Task 5.2: Написать тесты для настраиваемого срока действия бонуса (7 дней / бессрочно / другой)
- [x] Task 5.3: Написать тесты для грейс-периода (60 бессрочных минут для существующих пользователей)
- [x] Task 5.4: Реализовать начисление welcome-бонуса в `BillingService`
- [x] Task 5.5: Создать Alembic-миграционный скрипт для начисления грейс-периода существующим пользователям
- [x] Task 5.6: Реализовать отправку broadcast-уведомления при запуске монетизации (утилита/скрипт)

### Verification

- [x] Welcome-бонус начисляется при первом `/start`
- [x] Бонус тратится только после исчерпания дневного лимита
- [x] Миграция грейс-периода работает корректно
- [x] mypy проходит без ошибок

---

## Phase 6: Transcription Pipeline Integration

Интеграция проверки лимитов в существующий пайплайн транскрипции.

### Tasks

- [x] Task 6.1: Написать тесты для проверки лимита перед транскрипцией в `TranscriptionOrchestrator`
- [x] Task 6.2: Написать тесты для последовательного списания через Queue Manager
- [x] Task 6.3: Написать тесты для сценария «минут достаточно» (бесшовная транскрипция + уведомление)
- [x] Task 6.4: Написать тесты для сценария «минут недостаточно» (блокировка + кнопки покупки)
- [x] Task 6.5: Написать тесты для уведомления при 80%+ использования дневного лимита
- [x] Task 6.6: Интегрировать `BillingService` в `TranscriptionOrchestrator.process_transcription()`
- [x] Task 6.7: Обновить `BotHandlers` — добавить проверку лимита перед постановкой в очередь
- [x] Task 6.8: Обновить `QueueManager` — последовательная проверка лимита и списание
- [x] Task 6.9: Добавить инлайн-кнопки покупки пакетов при недостатке минут

### Verification

- [x] При BILLING_ENABLED=false — бот работает как раньше (без изменений)
- [x] При BILLING_ENABLED=true — проверка лимита перед каждой транскрипцией
- [x] Корректное списание из нескольких источников
- [x] Уведомления работают корректно
- [x] mypy проходит без ошибок

---

## Phase 7: Payment Service Abstraction

Абстрактный слой для платёжных провайдеров.

### Tasks

- [x] Task 7.1: Написать тесты для абстрактного `PaymentProvider` (protocol/ABC)
- [x] Task 7.2: Написать тесты для `PaymentService` (маршрутизация к провайдеру, обработка callback)
- [x] Task 7.3: Реализовать `PaymentProvider` protocol в `src/services/payments/base.py`
- [x] Task 7.4: Реализовать `PaymentService` в `src/services/payments/payment_service.py`

### Verification

- [x] Абстракция позволяет подключать произвольные провайдеры
- [x] Тесты проходят
- [x] mypy проходит без ошибок

---

## Phase 8: Telegram Stars Integration

Интеграция с Telegram Bot Payments API (Stars).

### Tasks

- [x] Task 8.1: Написать тесты для `TelegramStarsProvider`
- [x] Task 8.2: Реализовать `TelegramStarsProvider` в `src/services/payments/telegram_stars.py`:
  - Создание invoice (sendInvoice)
  - Обработка pre_checkout_query
  - Обработка successful_payment
  - Создание Purchase-записи
  - Начисление минут/подписки
- [x] Task 8.3: Зарегистрировать хэндлеры pre_checkout_query и successful_payment в `main.py`
- [x] Task 8.4: Написать тесты для напоминания о продлении подписки (за 3 дня)
- [x] Task 8.5: Реализовать логику напоминаний для Telegram Stars подписок

### Verification

- [x] Invoice создаётся корректно
- [x] Pre-checkout query обрабатывается
- [x] Successful payment начисляет минуты/подписку
- [x] Напоминание отправляется за 3 дня до истечения
- [x] mypy проходит без ошибок

---

## Phase 9: ЮKassa Integration

Интеграция с ЮKassa (карты РФ, СБП, рекуррентные платежи, чеки 54-ФЗ).

### Tasks

- [x] Task 9.1: Добавить зависимость `yookassa` в `pyproject.toml`
- [x] Task 9.2: Написать тесты для `YooKassaProvider`
- [x] Task 9.3: Реализовать `YooKassaProvider` в `src/services/payments/yookassa_provider.py`:
  - Создание платежа (Payment.create)
  - Обработка webhook (notification)
  - Рекуррентные платежи (сохранение payment_method, auto_payment)
  - Формирование чеков 54-ФЗ (receipt object)
  - Создание Purchase-записи
  - Начисление минут/подписки
- [x] Task 9.4: Добавить ENV-переменные для ЮKassa (shop_id, secret_key) в config, .env.example, deploy.yml
- [x] Task 9.5: Зарегистрировать webhook-хэндлер для ЮKassa (или polling)

### Verification

- [x] Платёж создаётся корректно
- [x] Webhook обрабатывает успешный и неуспешный платёж
- [x] Рекуррентные платежи работают
- [x] Чеки 54-ФЗ формируются
- [x] mypy проходит без ошибок

---

## Phase 10: Bot Commands & UI

Новые команды и обновлённый пользовательский интерфейс.

### Tasks

- [x] Task 10.1: Написать тесты для команды `/balance`
- [x] Task 10.2: Написать тесты для команды `/subscribe`
- [x] Task 10.3: Написать тесты для команды `/buy`
- [x] Task 10.4: Написать тесты для обновлённого `/start` (приветствие с условиями + welcome-бонус)
- [x] Task 10.5: Написать тесты для обновлённого `/help` (финансовые условия)
- [x] Task 10.6: Реализовать команду `/balance` — остаток дневного лимита, бонусные, пакетные минуты, статус подписки
- [x] Task 10.7: Реализовать команду `/subscribe` — каталог подписок с ценами, скидками и кнопками оплаты (Stars / ЮKassa)
- [x] Task 10.8: Реализовать команду `/buy` — каталог пакетов с ценами, скидками и кнопками покупки
- [x] Task 10.9: Обновить `/start` — приветственное сообщение с условиями (10 мин/день + 60 бонусных)
- [x] Task 10.10: Обновить `/help` — условия использования, включая финансовые
- [x] Task 10.11: Зарегистрировать новые CommandHandler'ы в `main.py`
- [x] Task 10.12: Добавить DI для BillingService, SubscriptionService, PaymentService в `main.py`

### Verification

- [x] Все команды работают корректно
- [x] /balance показывает актуальные данные
- [x] /subscribe и /buy показывают каталоги с кнопками оплаты
- [x] /start обновлён для новых пользователей
- [x] mypy проходит без ошибок

---

## Phase 11: Analytics Extension

Расширение аналитического скрипта монетизационными метриками.

### Tasks

- [x] Task 11.1: Расширить `docs/research/analytics/generate_excel_report.py` новыми листами:
  - Conversion Metrics: % превысивших лимит, Free-to-Paid CR, повторные покупки, ARPU
  - Retention Metrics: Churn, DAU/MAU Ratio
  - Financial Metrics: Gross Margin, расходы на Free-сегмент, LTV, расходы/MAU
  - Operational Metrics: использование дневного лимита, время до первой покупки, использование welcome-бонуса
- [x] Task 11.2: Добавить SQL-запросы для расчёта метрик из новых таблиц

### Verification

- [x] Скрипт генерирует Excel-отчёт с новыми листами
- [x] Метрики рассчитываются корректно на тестовых данных

---

## Phase 12: Seed Data & Final Integration

Заполнение БД начальными данными тарифов и финальная интеграция.

### Tasks

- [x] Task 12.1: Создать Alembic data-migration с начальными данными:
  - Общие billing_conditions (daily_free_minutes=10, welcome_bonus_minutes=60, welcome_bonus_days=null)
  - SubscriptionTier Pro (daily_limit_minutes=30)
  - SubscriptionPrices для Pro (week/month/year)
  - MinutePackages (50/100/500/5000 мин)
- [x] Task 12.2: Написать end-to-end тесты полного цикла: отправка аудио → проверка лимита → списание → уведомление
- [x] Task 12.3: Написать end-to-end тесты: покупка пакета → начисление → использование
- [x] Task 12.4: Обновить `.env.example` и `.env.example.short` и `.github/workflows/deploy.yml` со всеми новыми переменными
- [x] Task 12.5: Обновить `docs/` с документацией по системе тарификации

### Verification

- [x] Seed data корректно заполняет БД
- [x] End-to-end тесты проходят
- [x] Документация обновлена

---

## Final Verification

- [x] All acceptance criteria met
- [x] Tests passing (`uv run pytest tests/unit/ -v`) — 918 tests
- [x] Linters passing (`uv run ruff check src/`, `uv run black --check src/ tests/`)
- [x] Type checking passing (`uv run mypy src/`)
- [x] BILLING_ENABLED=false — бот работает как раньше (backward compatibility)
- [x] BILLING_ENABLED=true — полный цикл тарификации работает
- [x] Documentation updated
- [x] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
