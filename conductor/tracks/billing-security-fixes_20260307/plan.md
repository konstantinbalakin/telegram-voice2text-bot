# Implementation Plan: Исправление критических проблем безопасности и надёжности биллинга

**Track ID:** billing-security-fixes_20260307
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-07
**Status:** [~] In Progress

## Overview

Исправления сгруппированы в 7 фаз по логическим зависимостям. Порядок: сначала безопасность платежей (блокеры мерджа), затем надёжность, потом type design и тесты.

---

## Phase 1: Безопасность платёжного payload

Исправления CRITICAL 1-3: валидация pre-checkout, верификация user_id, period в payload.

### Tasks

- [x] Task 1.1: Тесты — pre_checkout_query отклоняет невалидный payload и неверную сумму
- [x] Task 1.2: Тесты — successful_payment_handler сверяет user_id из payload с effective_user
- [x] Task 1.3: Тесты — period подписки корректно передаётся в payload и активируется
- [x] Task 1.4: Расширить payload формат до `{type}:{item_id}:{user_id}:{period}` (period опционален для пакетов)
- [x] Task 1.5: Вынести `_parse_payment_payload` в `src/services/payments/base.py` как единую реализацию (fix дублирования #15)
- [x] Task 1.6: Реализовать валидацию в `pre_checkout_query_handler` — парсинг payload, проверка существования товара, сверка суммы
- [x] Task 1.7: В `successful_payment_handler` — сверить `effective_user.id` с user_id из payload через DB lookup
- [x] Task 1.8: Передать `period` из payload в `handle_successful_payment` для подписок

### Verification

- [x] Тесты Phase 1 проходят
- [x] mypy, ruff, black чистые

---

## Phase 2: Идемпотентность и атомарность платежей

Исправления CRITICAL 6-7, IMPORTANT 10: идемпотентность, ошибка зачисления, Purchase FAILED.

### Tasks

- [x] Task 2.1: Тесты — повторный successful_payment с тем же transaction_id не создаёт дубликат
- [x] Task 2.2: Тесты — ошибка в `_credit_package`/`_activate_subscription` → Purchase маркируется FAILED
- [x] Task 2.3: Тесты — `handle_successful_payment` когда purchase не найден (test gap #20)
- [x] Task 2.4: Добавить проверку `provider_transaction_id` в `handle_successful_payment` перед начислением
- [x] Task 2.5: Обернуть `_credit_package`/`_activate_subscription` в try/except → маркировать Purchase как FAILED при ошибке
- [x] Task 2.6: Логировать на уровне CRITICAL при ошибке зачисления после оплаты с transaction_id

### Verification

- [x] Тесты Phase 2 проходят
- [x] Идемпотентность: повторный вызов с тем же transaction_id → no-op

---

## Phase 3: Fail-closed и порядок операций

Исправления CRITICAL 5, IMPORTANT 9: fail-open→fail-closed, порядок списания.

### Tasks

- [x] Task 3.1: Тесты — ошибка биллинга блокирует транскрипцию (а не пропускает)
- [x] Task 3.2: Тесты — списание минут происходит ДО отправки результата
- [x] Task 3.3: `handlers.py` — убрать try/except fail-open, пробрасывать ошибку биллинга → отправка "Сервис временно недоступен"
- [x] Task 3.4: `transcription_orchestrator.py` — переместить `deduct_minutes` ДО `_send_result_and_update_state`
- [x] Task 3.5: `main.py` — сделать ошибку инициализации биллинга фатальной (если `billing_enabled=True`)
- [x] Task 3.6: Обновить fail-open тест в `test_billing_error_handling.py` → fail-closed поведение

### Verification

- [x] Тесты Phase 3 проходят
- [x] При ошибке БД транскрипция не выполняется

---

## Phase 4: Race condition и атомарность списания

Исправления CRITICAL 4, IMPORTANT 13, 17: race condition, rollback, shortfall.

### Tasks

- [x] Task 4.1: Тесты — параллельные запросы одного пользователя не приводят к overspend
- [x] Task 4.2: Добавить `asyncio.Lock` по user_id в `BillingService.deduct_minutes` для сериализации списаний
- [x] Task 4.3: Заменить `rollback()` на `begin_nested()` (savepoint) в `DailyUsageRepository.get_or_create`
- [x] Task 4.4: `deduct_minutes` — возвращать shortfall как часть результата (вместо тихого warning)
- [x] Task 4.5: Переместить `deduct_minutes` в orchestrator ДО отправки результата (если не сделано в Phase 3)

### Verification

- [x] Тесты Phase 4 проходят
- [x] Stress-тест: 2 параллельных вызова → корректный баланс

---

## Phase 5: Качество кода и error handling

Исправления IMPORTANT 8, 11, 12, 15, 16: утечка ошибок, callback фидбек, assert, дублирование, приватные методы.

### Tasks

- [x] Task 5.1: Тесты — error messages пользователю не содержат внутренних деталей
- [x] Task 5.2: Заменить `str(e)` на generic сообщения в `yookassa_provider.py` и `telegram_stars.py`
- [x] Task 5.3: Добавить `await query.edit_message_text(ERROR_MSG)` в 5 callback except-блоков `billing_commands.py`
- [x] Task 5.4: Заменить `assert` на `if ... is None: raise RuntimeError(...)` в `payment_service.py` и `billing_service.py`
- [x] Task 5.5: Вынести `_period_label` в `src/services/payments/base.py`, удалить дубликаты
- [x] Task 5.6: Переименовать `_build_balance_text_and_markup` → `build_balance_text_and_markup` (убрать `_`)
- [x] Task 5.7: Удалить мёртвый код: `_get_user_db_id` (module-level), `PaymentStatus` enum (если не используется)
- [x] Task 5.8: Добавить `exc_info=True` во все `logger.error` в платёжных провайдерах

### Verification

- [x] Тесты Phase 5 проходят
- [x] ruff, black, mypy чистые
- [x] Нет `assert` в src/services/payments/ и src/services/billing_service.py

---

## Phase 6: Type design и миграции

Исправления Type Design 23-27: Float→Integer, CHECK constraints, UserBalance, unique index.

### Tasks

- [x] Task 6.1: Тесты — денежные поля хранят Integer (копейки), minutes как Float с round
- [x] Task 6.2: Тесты — CHECK constraints отклоняют отрицательные значения
- [x] Task 6.3: Тесты — UserBalance.daily_remaining и total_available = computed properties
- [x] Task 6.4: Alembic миграция: `amount_rub`, `price_rub`, `Purchase.amount` → Integer (копейки)
- [x] Task 6.5: Обновить все сервисы для работы с копейками вместо рублей
- [x] Task 6.6: Alembic миграция: добавить CHECK constraints (`minutes_remaining >= 0`, `amount >= 0`, `daily_limit_minutes > 0`)
- [x] Task 6.7: Рефакторинг UserBalance — `daily_remaining` и `total_available` как `@property`, `frozen=True`, `__post_init__` валидация
- [x] Task 6.8: Alembic миграция: partial unique index на `UserSubscription(user_id)` WHERE `status = 'active'`
- [x] Task 6.9: Удалить/использовать `Currency` enum в `PaymentRequest.currency` и `Purchase.currency`

### Verification

- [x] Тесты Phase 6 проходят
- [x] Миграции обратимы (`upgrade` + `downgrade`)
- [x] Все суммы в БД хранятся как Integer

---

## Phase 7: Тестовое покрытие

Исправления Test Gaps 18-22: недостающие тесты для критических путей.

### Tasks

- [x] Task 7.1: Тест `successful_payment_handler` с невалидным payload → reply "Ошибка" (gap #18)
- [x] Task 7.2: Тест конвертации RUB amount в `create_payment` — проверка args в `purchase_repo.create` (gap #19)
- [x] Task 7.3: Тест невалидного callback_data формата `"pkg_stars:abc"` → ValueError handled (gap #21)
- [x] Task 7.4: Тест `/start` → `grant_welcome_bonus` вызывается; ошибка в bonus не ломает /start (gap #22)
- [x] Task 7.5: Тест `successful_payment_handler` с невалидным payment_type → ошибка
- [x] Task 7.6: Тест `PaymentResult.__post_init__` — success=True + error_message → ValueError

### Verification

- [x] Все тесты проходят
- [x] Нет пропущенных критических путей

---

## Final Verification

- [ ] Все acceptance criteria met
- [ ] `uv run pytest tests/unit/ -v` — зелёный
- [ ] `uv run ruff check src/` — чистый
- [ ] `uv run black --check src/ tests/` — чистый
- [ ] `uv run mypy src/` — чистый
- [ ] Ручное тестирование: платёж через Stars, проверка баланса, отклонение при нехватке минут
- [ ] PR готов к мерджу

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
