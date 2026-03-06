# Implementation Plan: Database Schema Optimization & Price Versioning

**Track ID:** db-optimization_20260306
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-06
**Status:** [~] In Progress

## Overview

Пофазная оптимизация схемы БД: сначала критические constraint'ы и PRAGMA, затем составные индексы, версионирование цен, N+1 оптимизация, и обновление документации. Каждая фаза — отдельная Alembic-миграция (где затрагивается схема).

## Phase 1: Critical Constraints & PRAGMA

Устранение критических проблем целостности данных и включение проверки FK.

### Tasks

- [x] Task 1.1: Добавить UNIQUE constraint на daily_usage(user_id, date) в модели (UniqueConstraint в __table_args__)
- [x] Task 1.2: Обновить DailyUsageRepository.get_or_create — обработка IntegrityError при race condition (try/except с повторным SELECT)
- [x] Task 1.3: Добавить PRAGMA foreign_keys=ON в init_db() (выполняется при каждом подключении)
- [x] Task 1.4: Добавить SQLite PRAGMA оптимизации в init_db(): synchronous=NORMAL, cache_size=-64000, mmap_size=268435456, temp_store=MEMORY
- [x] Task 1.5: Добавить CHECK constraint на purchases.purchase_type IN ('package', 'subscription') в модели
- [x] Task 1.6: Создать Alembic-миграцию для Phase 1 (UNIQUE, CHECK — через batch_alter_table)
- [x] Task 1.7: Написать тесты: UNIQUE constraint на daily_usage (дубликат → IntegrityError), get_or_create race condition handling

### Verification

- [ ] `uv run alembic upgrade head` проходит без ошибок
- [ ] `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v` — все тесты зелёные
- [ ] `uv run mypy src/` — без ошибок

## Phase 2: Composite Indexes

Добавление составных индексов для оптимизации частых запросов.

### Tasks

- [x] Task 2.1: Добавить Index("ix_user_subscriptions_user_status_expires", "user_id", "status", "expires_at") в UserSubscription.__table_args__
- [x] Task 2.2: Добавить Index("ix_billing_conditions_key_user_valid", "key", "user_id", "valid_from") в BillingCondition.__table_args__
- [x] Task 2.3: Добавить Index("ix_purchases_user_type_item_status", "user_id", "purchase_type", "item_id", "status") в Purchase.__table_args__
- [x] Task 2.4: Добавить Index("ix_deduction_log_created", "created_at") в DeductionLog.__table_args__
- [x] Task 2.5: Удалить дублирующиеся одиночные индексы, покрытые новыми составными (daily_usage.user_id — покрыт UNIQUE)
- [x] Task 2.6: Создать Alembic-миграцию для Phase 2

### Verification

- [ ] `uv run alembic upgrade head` проходит
- [ ] Все тесты зелёные
- [ ] SQLite schema dump показывает новые индексы

## Phase 3: Price Versioning (subscription_prices & minute_packages)

Добавление полей valid_from, valid_to, user_id для версионирования цен и персональных скидок.

### Tasks

- [ ] Task 3.1: Добавить поля в модель SubscriptionPrice: valid_from (DateTime, NOT NULL, default=now), valid_to (DateTime, nullable), user_id (Integer, FK users, nullable, indexed)
- [ ] Task 3.2: Добавить поля в модель MinutePackage: valid_from (DateTime, NOT NULL, default=now), valid_to (DateTime, nullable), user_id (Integer, FK users, nullable, indexed)
- [ ] Task 3.3: Создать Alembic-миграцию: добавить колонки, заполнить valid_from из created_at для существующих записей, user_id=NULL
- [ ] Task 3.4: Добавить SubscriptionRepository.get_effective_prices(tier_id, user_id=None) — получение актуальных цен с учётом valid_from/valid_to и приоритетом user_id > global
- [ ] Task 3.5: Добавить MinutePackageRepository.get_effective_packages(user_id=None) — аналогичная логика для пакетов
- [ ] Task 3.6: Обновить SubscriptionRepository.get_tier_prices — использовать get_effective_prices
- [ ] Task 3.7: Обновить MinutePackageRepository.get_active_packages — использовать get_effective_packages
- [ ] Task 3.8: Написать тесты: версионирование цен (текущая/будущая/истекшая цена), персональная цена для user_id, приоритет individual > global

### Verification

- [ ] Миграция проходит, существующие данные корректны (valid_from = created_at, valid_to = NULL, user_id = NULL)
- [ ] Все тесты зелёные
- [ ] mypy без ошибок

## Phase 4: N+1 Query Optimization

Устранение N+1 запросов при загрузке subscription + tier.

### Tasks

- [ ] Task 4.1: Добавить SubscriptionRepository.get_active_subscription_with_tier(user_id) — joinedload(UserSubscription.tier)
- [ ] Task 4.2: Обновить BillingService._get_daily_limit_with_repos — использовать get_active_subscription_with_tier вместо отдельных get_active_subscription + get_tier_by_id
- [ ] Task 4.3: Обновить SubscriptionService.get_active_subscription — опциональный параметр eager_load_tier=False
- [ ] Task 4.4: Написать тест: verify joinedload не делает дополнительный SELECT для tier

### Verification

- [ ] Все тесты зелёные
- [ ] mypy без ошибок

## Phase 5: Documentation & SQL Updates

Обновление документации под изменения схемы.

### Tasks

- [ ] Task 5.1: Обновить docs/sql/queries.sql — отразить новые поля (valid_from/valid_to/user_id) в subscription_prices и minute_packages, новые индексы
- [ ] Task 5.2: Обновить docs/research/analytics/generate_excel_report.py — учесть изменения в схеме
- [ ] Task 5.3: Проверить что все существующие SQL-запросы в queries.sql корректны для новой схемы

### Verification

- [ ] queries.sql содержит актуальные запросы для новой схемы
- [ ] generate_excel_report.py работает с новой схемой

## Final Verification

- [ ] All acceptance criteria met
- [ ] `uv run ruff check src/` — без ошибок
- [ ] `uv run black --check src/ tests/` — без ошибок
- [ ] `uv run mypy src/` — без ошибок
- [ ] `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v` — все тесты зелёные
- [ ] `uv run alembic upgrade head` на чистой БД — все миграции проходят
- [ ] Ручное тестирование: бот стартует, /balance и /buy работают
- [ ] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
