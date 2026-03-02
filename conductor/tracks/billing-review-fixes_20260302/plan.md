# Implementation Plan: Billing System PR Review Fixes

**Track ID:** billing-review-fixes_20260302
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-02
**Status:** [~] In Progress

## Overview

Исправление находок PR-ревью в 6 фазах: критические баги -> error handling -> безопасность -> типизация -> комментарии/логика -> тесты. Каждая фаза независимо верифицируема. Работаем на ветке feature/billing-system.

## Phase 1: Critical Fixes — Session, ID Mapping, Async, Email

Исправление 4 критических проблем, блокирующих работоспособность billing system.

### Tasks

- [x] Task 1.1: Переделать DI биллинга на per-request сессии — сервисы принимают session_factory вместо готовых репозиториев (`src/main.py`, `src/services/billing_service.py`, `src/services/subscription_service.py`, `src/services/payments/payment_service.py`)
- [x] Task 1.2: Написать тесты на per-request сессии — проверить, что каждый вызов сервиса создаёт новую сессию
- [x] Task 1.3: Исправить маппинг Telegram ID -> DB ID в `handlers.py` и `transcription_orchestrator.py` — использовать `UserRepository.get_by_telegram_id()`
- [x] Task 1.4: Написать тесты на корректный маппинг ID
- [x] Task 1.5: Обернуть синхронные вызовы YooKassa SDK в `asyncio.to_thread()` (`yookassa_provider.py`)
- [x] Task 1.6: Написать тесты на async-обёртку YooKassa
- [x] Task 1.7: Заменить hardcoded `customer@example.com` — добавить параметр email в PaymentRequest или убрать receipt при отсутствии email

### Verification

- [x] Все существующие тесты проходят
- [x] Новые тесты на session/ID/async проходят
- [x] `uv run mypy src/` без ошибок

## Phase 2: Error Handling & Resilience

Добавление try-except, fail-open стратегии, и правильной обработки ошибок.

### Tasks

- [x] Task 2.1: Обернуть `deduct_minutes` в try-except в `transcription_orchestrator.py` — ошибка биллинга не должна ронять pipeline
- [x] Task 2.2: Добавить try-except в `check_can_transcribe` в `handlers.py` — fail-open при ошибке биллинга
- [x] Task 2.3: Добавить try-except во все команды `billing_commands.py` (`/balance`, `/subscribe`, `/buy`, `/start`, `/help`) — понятное сообщение пользователю при ошибке
- [x] Task 2.4: Добавить проверку `remaining > 0` после цикла списания в `deduct_minutes` — логировать дефицит
- [x] Task 2.5: Исправить `_credit_package` — бросать исключение вместо `return False` при отсутствии пакета
- [x] Task 2.6: Обернуть `grant_welcome_bonus` в try-except в `billing_commands.py`
- [x] Task 2.7: Заменить `except Exception: pass` на `logger.debug()` в orchestrator (4 места)
- [x] Task 2.8: Написать тесты на error handling — ошибки БД, сетевые ошибки, edge cases

### Verification

- [x] Тесты на error handling проходят
- [x] Ошибка биллинга не прерывает транскрипцию (тест)

## Phase 3: Security & Payment Logic

Исправление проблем безопасности и логики платежей.

### Tasks

- [x] Task 3.1: Добавить верификацию webhook YooKassa — проверка через `Payment.find_one(payment_id)` после callback
- [x] Task 3.2: Добавить вызов `mark_completed` для Purchase после успешной оплаты в `handle_successful_payment`
- [x] Task 3.3: Исправить `cancel_subscription` — `auto_renew=False` без смены статуса, чтобы подписка работала до `expires_at`
- [x] Task 3.4: Убрать hardcoded `period="month"` из `_activate_subscription` — передавать period из данных платежа
- [x] Task 3.5: Добавить `ORDER BY` в `get_active_balances` для гарантии порядка bonus -> package
- [x] Task 3.6: Исправить seed-миграцию: `welcome_bonus_days` = NULL вместо пустой строки, `tier_id` через подзапрос, `now` внутри `upgrade()`
- [x] Task 3.7: Добавить логирование в `parse_payload` и `parse_metadata` — WARNING при ошибке парсинга; убрать дефолтные `0`
- [x] Task 3.8: Написать тесты на все исправления фазы 3

### Verification

- [x] Webhook верификация тест проходит
- [x] Purchase корректно переходит в completed (тест)
- [x] Отмена подписки сохраняет лимит до expires_at (тест)

## Phase 4: Type Design & Enums

Улучшение типизации — enum вместо строковых литералов, typed dataclasses.

### Tasks

- [ ] Task 4.1: Создать enum'ы: `SubscriptionStatus`, `SubscriptionPeriod`, `BalanceType`, `DeductionSource`, `PurchaseStatus`, `Currency` (расширить existing `PaymentType`, `PaymentStatus`)
- [ ] Task 4.2: Применить enum'ы в SQLAlchemy моделях (`storage/models.py`) и миграциях
- [ ] Task 4.3: Обновить репозитории и сервисы для работы с enum вместо строк
- [ ] Task 4.4: Заменить `dict` на `UserBalance` dataclass в `get_user_balance`
- [ ] Task 4.5: Добавить `__post_init__` валидацию в `PaymentResult` — `success=True` несовместим с `error_message`
- [ ] Task 4.6: Заменить `PERIOD_DAYS.get(period, 30)` на explicit error при невалидном периоде
- [ ] Task 4.7: Устранить нарушение encapsulation — добавить методы-обёртки в сервисы вместо прямого доступа к `subscription_repo` из commands
- [ ] Task 4.8: Обновить тесты для работы с enum'ами и новыми типами

### Verification

- [ ] `uv run mypy src/` без ошибок
- [ ] Все тесты проходят с enum'ами
- [ ] Нет строковых литералов для статусов/типов в коде

## Phase 5: Comments & Documentation

Исправление неточных комментариев и docstring'ов.

### Tasks

- [ ] Task 5.1: Исправить docstring `cancel_subscription` — отразить новое поведение (после Phase 3.3)
- [ ] Task 5.2: Исправить модуль docstring YooKassa — убрать "mock mode", описать реальное поведение
- [ ] Task 5.3: Обновить docstring `handle_callback` в TelegramStars — пояснить, что callback обрабатывается через Telegram API
- [ ] Task 5.4: Добавить документацию к `deduct_minutes` — порядок списания и округление
- [ ] Task 5.5: Документировать `warning_threshold`, hardcoded значения и бизнес-логику
- [ ] Task 5.6: Убрать тривиальные docstring'ы (`"Payment type."`, `"Payment status."`) или расширить

### Verification

- [ ] Все docstring'ы точно отражают поведение кода

## Phase 6: Test Quality & Coverage Gaps

Улучшение тестов — пробелы покрытия, дублирование, качество.

### Tasks

- [ ] Task 6.1: Добавить тест на недосписание минут (deduction shortfall) — `remaining > 0` после обхода всех источников
- [ ] Task 6.2: Добавить тест на исключение провайдера при `create_payment` — Purchase должен быть marked_failed
- [ ] Task 6.3: Усилить тест `check_expired_subscriptions` — проверить auto_renew логику, заменить `assert count >= 0` на точное значение
- [ ] Task 6.4: Добавить тест `get_user_daily_limit` при отсутствующем tier
- [ ] Task 6.5: Добавить тесты на граничные значения: `deduct_minutes(0.0)`, `deduct_minutes(-1.0)`, `daily_limit=0`
- [ ] Task 6.6: Вынести `_make_billing_service` в `conftest.py` — убрать дублирование из 3 файлов
- [ ] Task 6.7: Переименовать `test_billing_e2e.py` в `test_billing_scenarios.py` — название точнее отражает содержание

### Verification

- [ ] Все тесты проходят: `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v`
- [ ] Покрытие новых edge cases подтверждено

## Final Verification

- [ ] Все acceptance criteria выполнены
- [ ] `uv run ruff check src/`
- [ ] `uv run black --check src/ tests/`
- [ ] `uv run mypy src/`
- [ ] `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v`
- [ ] Все тесты проходят (ожидается 918+)
- [ ] PR готов к мержу

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
