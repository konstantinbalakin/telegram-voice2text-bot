# Implementation Plan: Billing System (Tarification)

**Track ID:** billing-system_20260302
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-02
**Status:** [~] In Progress

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
- [~] Task 1.4: Добавить `BILLING_ENABLED` в `src/config.py`, `.env.example`, `.env.example.short`, `.github/workflows/deploy.yml`
- [~] Task 1.5: Добавить `BILLING_LIMIT_WARNING_THRESHOLD` (default=0.8) в config

### Verification

- [ ] Все тесты моделей проходят
- [ ] Миграция применяется и откатывается без ошибок
- [ ] mypy проходит без ошибок

---

## Phase 2: Billing Repositories

Создание репозиториев для доступа к новым таблицам.

### Tasks

- [ ] Task 2.1: Написать тесты для `BillingConditionRepository` (CRUD, получение условий с приоритетом индивидуальных, фильтрация по valid_from/valid_to)
- [ ] Task 2.2: Написать тесты для `SubscriptionRepository` (CRUD тиров, цен, подписок пользователей, проверка активной подписки)
- [ ] Task 2.3: Написать тесты для `MinutePackageRepository` (CRUD, каталог активных пакетов)
- [ ] Task 2.4: Написать тесты для `UserMinuteBalanceRepository` (CRUD, списание минут по приоритету, проверка баланса)
- [ ] Task 2.5: Написать тесты для `DailyUsageRepository` и `DeductionLogRepository`
- [ ] Task 2.6: Написать тесты для `PurchaseRepository`
- [ ] Task 2.7: Реализовать `BillingConditionRepository` в `src/storage/repositories.py` (или отдельный файл `src/storage/billing_repositories.py`)
- [ ] Task 2.8: Реализовать `SubscriptionRepository`
- [ ] Task 2.9: Реализовать `MinutePackageRepository`
- [ ] Task 2.10: Реализовать `UserMinuteBalanceRepository`
- [ ] Task 2.11: Реализовать `DailyUsageRepository`, `DeductionLogRepository`, `PurchaseRepository`

### Verification

- [ ] Все тесты репозиториев проходят
- [ ] mypy проходит без ошибок

---

## Phase 3: Billing Service Core

Ядро биллинга: проверка лимитов, списание минут, получение балансов.

### Tasks

- [ ] Task 3.1: Написать тесты для `BillingService`:
  - `get_user_daily_limit(user_id)` — возвращает дневной лимит (индивидуальный или общий, с учётом подписки)
  - `get_user_balance(user_id)` — возвращает полный баланс (дневной остаток, бонусные, пакетные)
  - `check_can_transcribe(user_id, duration_minutes)` — проверка достаточности минут
  - `deduct_minutes(user_id, usage_id, duration_minutes)` — списание с размазыванием по источникам
  - `get_daily_usage(user_id, date)` — получение дневного использования
  - `reset_daily_usage(user_id)` — сброс дневного использования (00:00 MSK)
- [ ] Task 3.2: Написать тесты для округления до десятых долей минуты
- [ ] Task 3.3: Написать тесты для размазывания минут между источниками (дневной → бонус → пакет)
- [ ] Task 3.4: Написать тесты для сценариев: подписка заменяет (не суммирует) дневной лимит
- [ ] Task 3.5: Реализовать `BillingService` в `src/services/billing_service.py`
- [ ] Task 3.6: Написать тесты для уведомлений о приближении к лимиту (80%+ порог)
- [ ] Task 3.7: Реализовать логику уведомлений в `BillingService`

### Verification

- [ ] Все тесты BillingService проходят
- [ ] Корректное размазывание минут между источниками
- [ ] Корректная работа с подпиской (замена, а не суммирование дневного лимита)
- [ ] mypy проходит без ошибок

---

## Phase 4: Subscription Service

Управление подписками: создание, продление, отмена, upgrade/downgrade.

### Tasks

- [ ] Task 4.1: Написать тесты для `SubscriptionService`:
  - `get_available_tiers()` — каталог доступных уровней подписки
  - `get_tier_prices(tier_id)` — цены для конкретного уровня
  - `create_subscription(user_id, tier_id, period, payment_provider)` — создание подписки
  - `cancel_subscription(user_id)` — отмена (действует до конца периода)
  - `renew_subscription(subscription_id)` — продление
  - `check_expired_subscriptions()` — проверка истёкших подписок
  - `handle_upgrade(user_id, new_tier_id, new_period)` — немедленный upgrade
  - `handle_downgrade(user_id, new_tier_id)` — downgrade при следующем продлении
- [ ] Task 4.2: Написать тесты для логики next_subscription_tier_id
- [ ] Task 4.3: Написать тесты для напоминания об истечении (за 3 дня для Telegram Stars)
- [ ] Task 4.4: Реализовать `SubscriptionService` в `src/services/subscription_service.py`

### Verification

- [ ] Все тесты SubscriptionService проходят
- [ ] Upgrade применяется немедленно
- [ ] Downgrade сохраняется в next_subscription_tier_id
- [ ] Отмена: подписка действует до конца периода
- [ ] mypy проходит без ошибок

---

## Phase 5: Welcome Bonus & Grace Period

Механизм welcome-бонуса для новых пользователей и грейс-периода для существующих.

### Tasks

- [ ] Task 5.1: Написать тесты для начисления welcome-бонуса при `/start`
- [ ] Task 5.2: Написать тесты для настраиваемого срока действия бонуса (7 дней / бессрочно / другой)
- [ ] Task 5.3: Написать тесты для грейс-периода (60 бессрочных минут для существующих пользователей)
- [ ] Task 5.4: Реализовать начисление welcome-бонуса в `BillingService`
- [ ] Task 5.5: Создать Alembic-миграционный скрипт для начисления грейс-периода существующим пользователям
- [ ] Task 5.6: Реализовать отправку broadcast-уведомления при запуске монетизации (утилита/скрипт)

### Verification

- [ ] Welcome-бонус начисляется при первом `/start`
- [ ] Бонус тратится только после исчерпания дневного лимита
- [ ] Миграция грейс-периода работает корректно
- [ ] mypy проходит без ошибок

---

## Phase 6: Transcription Pipeline Integration

Интеграция проверки лимитов в существующий пайплайн транскрипции.

### Tasks

- [ ] Task 6.1: Написать тесты для проверки лимита перед транскрипцией в `TranscriptionOrchestrator`
- [ ] Task 6.2: Написать тесты для последовательного списания через Queue Manager
- [ ] Task 6.3: Написать тесты для сценария «минут достаточно» (бесшовная транскрипция + уведомление)
- [ ] Task 6.4: Написать тесты для сценария «минут недостаточно» (блокировка + кнопки покупки)
- [ ] Task 6.5: Написать тесты для уведомления при 80%+ использования дневного лимита
- [ ] Task 6.6: Интегрировать `BillingService` в `TranscriptionOrchestrator.process_transcription()`
- [ ] Task 6.7: Обновить `BotHandlers` — добавить проверку лимита перед постановкой в очередь
- [ ] Task 6.8: Обновить `QueueManager` — последовательная проверка лимита и списание
- [ ] Task 6.9: Добавить инлайн-кнопки покупки пакетов при недостатке минут

### Verification

- [ ] При BILLING_ENABLED=false — бот работает как раньше (без изменений)
- [ ] При BILLING_ENABLED=true — проверка лимита перед каждой транскрипцией
- [ ] Корректное списание из нескольких источников
- [ ] Уведомления работают корректно
- [ ] mypy проходит без ошибок

---

## Phase 7: Payment Service Abstraction

Абстрактный слой для платёжных провайдеров.

### Tasks

- [ ] Task 7.1: Написать тесты для абстрактного `PaymentProvider` (protocol/ABC)
- [ ] Task 7.2: Написать тесты для `PaymentService` (маршрутизация к провайдеру, обработка callback)
- [ ] Task 7.3: Реализовать `PaymentProvider` protocol в `src/services/payments/base.py`
- [ ] Task 7.4: Реализовать `PaymentService` в `src/services/payments/payment_service.py`

### Verification

- [ ] Абстракция позволяет подключать произвольные провайдеры
- [ ] Тесты проходят
- [ ] mypy проходит без ошибок

---

## Phase 8: Telegram Stars Integration

Интеграция с Telegram Bot Payments API (Stars).

### Tasks

- [ ] Task 8.1: Написать тесты для `TelegramStarsProvider`
- [ ] Task 8.2: Реализовать `TelegramStarsProvider` в `src/services/payments/telegram_stars.py`:
  - Создание invoice (sendInvoice)
  - Обработка pre_checkout_query
  - Обработка successful_payment
  - Создание Purchase-записи
  - Начисление минут/подписки
- [ ] Task 8.3: Зарегистрировать хэндлеры pre_checkout_query и successful_payment в `main.py`
- [ ] Task 8.4: Написать тесты для напоминания о продлении подписки (за 3 дня)
- [ ] Task 8.5: Реализовать логику напоминаний для Telegram Stars подписок

### Verification

- [ ] Invoice создаётся корректно
- [ ] Pre-checkout query обрабатывается
- [ ] Successful payment начисляет минуты/подписку
- [ ] Напоминание отправляется за 3 дня до истечения
- [ ] mypy проходит без ошибок

---

## Phase 9: ЮKassa Integration

Интеграция с ЮKassa (карты РФ, СБП, рекуррентные платежи, чеки 54-ФЗ).

### Tasks

- [ ] Task 9.1: Добавить зависимость `yookassa` в `pyproject.toml`
- [ ] Task 9.2: Написать тесты для `YooKassaProvider`
- [ ] Task 9.3: Реализовать `YooKassaProvider` в `src/services/payments/yookassa_provider.py`:
  - Создание платежа (Payment.create)
  - Обработка webhook (notification)
  - Рекуррентные платежи (сохранение payment_method, auto_payment)
  - Формирование чеков 54-ФЗ (receipt object)
  - Создание Purchase-записи
  - Начисление минут/подписки
- [ ] Task 9.4: Добавить ENV-переменные для ЮKassa (shop_id, secret_key) в config, .env.example, deploy.yml
- [ ] Task 9.5: Зарегистрировать webhook-хэндлер для ЮKassa (или polling)

### Verification

- [ ] Платёж создаётся корректно
- [ ] Webhook обрабатывает успешный и неуспешный платёж
- [ ] Рекуррентные платежи работают
- [ ] Чеки 54-ФЗ формируются
- [ ] mypy проходит без ошибок

---

## Phase 10: Bot Commands & UI

Новые команды и обновлённый пользовательский интерфейс.

### Tasks

- [ ] Task 10.1: Написать тесты для команды `/balance`
- [ ] Task 10.2: Написать тесты для команды `/subscribe`
- [ ] Task 10.3: Написать тесты для команды `/buy`
- [ ] Task 10.4: Написать тесты для обновлённого `/start` (приветствие с условиями + welcome-бонус)
- [ ] Task 10.5: Написать тесты для обновлённого `/help` (финансовые условия)
- [ ] Task 10.6: Реализовать команду `/balance` — остаток дневного лимита, бонусные, пакетные минуты, статус подписки
- [ ] Task 10.7: Реализовать команду `/subscribe` — каталог подписок с ценами, скидками и кнопками оплаты (Stars / ЮKassa)
- [ ] Task 10.8: Реализовать команду `/buy` — каталог пакетов с ценами, скидками и кнопками покупки
- [ ] Task 10.9: Обновить `/start` — приветственное сообщение с условиями (10 мин/день + 60 бонусных)
- [ ] Task 10.10: Обновить `/help` — условия использования, включая финансовые
- [ ] Task 10.11: Зарегистрировать новые CommandHandler'ы в `main.py`
- [ ] Task 10.12: Добавить DI для BillingService, SubscriptionService, PaymentService в `main.py`

### Verification

- [ ] Все команды работают корректно
- [ ] /balance показывает актуальные данные
- [ ] /subscribe и /buy показывают каталоги с кнопками оплаты
- [ ] /start обновлён для новых пользователей
- [ ] mypy проходит без ошибок

---

## Phase 11: Analytics Extension

Расширение аналитического скрипта монетизационными метриками.

### Tasks

- [ ] Task 11.1: Расширить `docs/research/analytics/generate_excel_report.py` новыми листами:
  - Conversion Metrics: % превысивших лимит, Free-to-Paid CR, повторные покупки, ARPU
  - Retention Metrics: Churn, DAU/MAU Ratio
  - Financial Metrics: Gross Margin, расходы на Free-сегмент, LTV, расходы/MAU
  - Operational Metrics: использование дневного лимита, время до первой покупки, использование welcome-бонуса
- [ ] Task 11.2: Добавить SQL-запросы для расчёта метрик из новых таблиц

### Verification

- [ ] Скрипт генерирует Excel-отчёт с новыми листами
- [ ] Метрики рассчитываются корректно на тестовых данных

---

## Phase 12: Seed Data & Final Integration

Заполнение БД начальными данными тарифов и финальная интеграция.

### Tasks

- [ ] Task 12.1: Создать Alembic data-migration с начальными данными:
  - Общие billing_conditions (daily_free_minutes=10, welcome_bonus_minutes=60, welcome_bonus_days=null)
  - SubscriptionTier Pro (daily_limit_minutes=30)
  - SubscriptionPrices для Pro (week/month/year)
  - MinutePackages (50/100/500/5000 мин)
- [ ] Task 12.2: Написать end-to-end тесты полного цикла: отправка аудио → проверка лимита → списание → уведомление
- [ ] Task 12.3: Написать end-to-end тесты: покупка пакета → начисление → использование
- [ ] Task 12.4: Обновить `.env.example` и `.env.example.short` и `.github/workflows/deploy.yml` со всеми новыми переменными
- [ ] Task 12.5: Обновить `docs/` с документацией по системе тарификации

### Verification

- [ ] Seed data корректно заполняет БД
- [ ] End-to-end тесты проходят
- [ ] Документация обновлена

---

## Final Verification

- [ ] All acceptance criteria met
- [ ] Tests passing (`uv run pytest tests/unit/ -v`)
- [ ] Linters passing (`uv run ruff check src/`, `uv run black --check src/ tests/`)
- [ ] Type checking passing (`uv run mypy src/`)
- [ ] BILLING_ENABLED=false — бот работает как раньше (backward compatibility)
- [ ] BILLING_ENABLED=true — полный цикл тарификации работает
- [ ] Documentation updated
- [ ] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
