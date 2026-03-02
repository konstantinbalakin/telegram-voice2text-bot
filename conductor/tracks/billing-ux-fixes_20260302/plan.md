# Implementation Plan: Billing UX Fixes

**Track ID:** billing-ux-fixes_20260302
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-02
**Status:** [ ] Not Started

## Overview

Исправление трёх багов в пользовательском интерфейсе биллинга:
1. Некорректное сообщение о дневном лимите ("почти исчерпан" вместо "исчерпан")
2. Отображение использованных минут сверх лимита
3. Отсутствие inline кнопок оплаты в командах `/subscribe` и `/buy`

Решение включает добавление метода `get_limit_status()` в `BillingService`, создание `PaymentCallbackHandlers`, обновление команд `/subscribe` и `/buy`, регистрацию провайдера Telegram Stars и обработчиков платежей в `main.py`.

---

## Phase 1: Fix Daily Limit Notification Logic ✅ Complete

Исправление логики уведомлений о дневном лимите (проблемы 1 и 2).

### Tasks

- [x] Task 1.1: Написать тесты для метода `BillingService.get_limit_status()`:
  - Тест "ok" — когда `daily_used/daily_limit < 0.8`
  - Тест "warning" — когда `0.8 <= daily_used/daily_limit < 1.0`
  - Тест "exhausted" — когда `daily_used >= daily_limit`
- [x] Task 1.2: Реализовать метод `BillingService.get_limit_status(user_id)` в `src/services/billing_service.py`
- [x] Task 1.3: Написать тесты для уведомления в `TranscriptionOrchestrator.process_transcription()`:
  - Проверить что при status="exhausted" показывается сообщение "Дневной лимит исчерпан!"
  - Проверить что при status="warning" показывается сообщение "Дневной лимит почти исчерпан!"
  - Проверить что отображение использует `min(daily_used, daily_limit)`
- [x] Task 1.4: Обновить логику уведомления в `src/services/transcription_orchestrator.py`:
  - Заменить `should_warn_limit()` на `get_limit_status()`
  - Добавить условие для статусов "exhausted" и "warning"
  - Использовать `min(balance.daily_used, balance.daily_limit)` в уведомлении

### Verification

- [x] Тесты для `get_limit_status()` проходят
- [x] Тесты для уведомления проходят
- [x] При `daily_used >= daily_limit` показывается "Дневной лимит исчерпан!"
- [x] При `0.8 <= daily_used/daily_limit < 1.0` показывается "Дневной лимит почти исчерпан!"
- [x] В уведомлении отображается `min(daily_used, daily_limit)`

---

## Phase 2: Create Payment Callback Handlers

Создание обработчиков callback-кнопок для оплаты.

### Tasks

- [x] Task 2.1: Написать тесты для `PaymentCallbackHandlers`:
  - Тест `buy_package_stars_callback()` — создаёт invoice через PaymentService
  - Тест `buy_subscription_stars_callback()` — создаёт invoice через PaymentService
  - Тест `buy_package_card_callback()` — показывает заглушку
  - Тест `buy_subscription_card_callback()` — показывает заглушку
- [x] Task 2.2: Реализовать `PaymentCallbackHandlers` в новом файле `src/bot/payment_callbacks.py`:
  - `buy_package_stars_callback()` — обрабатывает `pkg_stars:{id}`
  - `buy_subscription_stars_callback()` — обрабатывает `sub_stars:{id}:{period}`
  - `buy_package_card_callback()` — обрабатывает `pkg_card:{id}` (заглушка)
  - `buy_subscription_card_callback()` — обрабатывает `sub_card:{id}:{period}` (заглушка)
- [x] Task 2.3: Написать тесты для обработчиков Telegram Stars платежей:
  - Тест `pre_checkout_query_handler()` — подтверждает pre-checkout
  - Тест `successful_payment_handler()` — парсит payload и вызывает `handle_successful_payment()`
- [x] Task 2.4: Реализовать обработчики Telegram Stars платежей в `src/bot/payment_callbacks.py`:
  - `pre_checkout_query_handler()` — всегда возвращает `ok=True`
  - `successful_payment_handler()` — парсит payload, вызывает `PaymentService.handle_successful_payment()`, отправляет подтверждение

### Verification

- [x] Тесты для `PaymentCallbackHandlers` проходят
- [x] Тесты для обработчиков платежей проходят
- [x] Callback-обработчики корректно формируют ответные сообщения

---

## Phase 3: Add Inline Buttons to /subscribe and /buy Commands

Добавление inline кнопок оплаты в команды `/subscribe` и `/buy`.

### Tasks

- [ ] Task 3.1: Написать тесты для обновлённой команды `/subscribe`:
  - Проверить что команда возвращает `InlineKeyboardMarkup`
  - Проверить что кнопки имеют правильный callback_data формат
- [ ] Task 3.2: Обновить метод `BillingCommands.subscribe_command()` в `src/bot/billing_commands.py`:
  - Добавить импорт `InlineKeyboardButton`, `InlineKeyboardMarkup`
  - Создавать кнопки для каждого тарифа с ценой в Stars
  - Формировать InlineKeyboardMarkup с кнопками
- [ ] Task 3.3: Написать тесты для обновлённой команды `/buy`:
  - Проверить что команда возвращает `InlineKeyboardMarkup`
  - Проверить что кнопки имеют правильный callback_data формат
- [ ] Task 3.4: Обновить метод `BillingCommands.buy_command()` в `src/bot/billing_commands.py`:
  - Создавать кнопки для каждого пакета с ценой в Stars
  - Формировать InlineKeyboardMarkup с кнопками

### Verification

- [ ] Тесты для `/subscribe` проходят
- [ ] Тесты для `/buy` проходят
- [ ] Команда `/subscribe` показывает inline кнопки для подписок
- [ ] Команда `/buy` показывает inline кнопки для пакетов
- [ ] Callback data кнопок имеет правильный формат

---

## Phase 4: Register Telegram Stars Provider and Handlers in main.py

Регистрация провайдера Telegram Stars и обработчиков платежей в main.py.

### Tasks

- [ ] Task 4.1: Добавить импорты в `src/main.py`:
  - `TelegramStarsProvider` из `src.services.payments.telegram_stars`
  - `PaymentCallbackHandlers`, `pre_checkout_query_handler`, `successful_payment_handler` из `src.bot.payment_callbacks`
- [ ] Task 4.2: Зарегистрировать TelegramStarsProvider:
  - Создать экземпляр `TelegramStarsProvider(bot=application.bot)`
  - Вызвать `payment_service.register_provider(telegram_stars_provider)`
- [ ] Task 4.3: Создать PaymentCallbackHandlers:
  - Создать экземпляр `PaymentCallbackHandlers(payment_service=payment_service)`
- [ ] Task 4.4: Зарегистрировать callback-обработчики:
  - `CallbackQueryHandler(buy_package_stars_callback, pattern=r"^pkg_stars:\d+$")`
  - `CallbackQueryHandler(buy_subscription_stars_callback, pattern=r"^sub_stars:\d+:(week|month|year)$")`
  - `CallbackQueryHandler(buy_package_card_callback, pattern=r"^pkg_card:\d+$")`
  - `CallbackQueryHandler(buy_subscription_card_callback, pattern=r"^sub_card:\d+:(week|month|year)$")`
- [ ] Task 4.5: Зарегистрировать обработчики Telegram Stars платежей:
  - `PreCheckoutQueryHandler(pre_checkout_query_handler)`
  - `MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler)`
- [ ] Task 4.6: Сохранить PaymentService в application_data:
  - `application.application_data["payment_service"] = payment_service`

### Verification

- [ ] TelegramStarsProvider зарегистрирован в PaymentService
- [ ] Callback-обработчики зарегистрированы
- [ ] Обработчики платежей Telegram Stars зарегистрированы
- [ ] PaymentService доступен через `application.application_data`
- [ ] Бот запускается без ошибок

---

## Phase 5: Final Verification

Финальная проверка всех изменений.

### Tasks

- [ ] Task 5.1: Запустить все тесты: `uv run pytest tests/unit/ -v`
- [ ] Task 5.2: Проверить линтеры: `uv run ruff check src/`
- [ ] Task 5.3: Проверить форматирование: `uv run black --check src/`
- [ ] Task 5.4: Проверить типы: `uv run mypy src/`
- [ ] Task 5.5: Ручное тестирование:
  - Проверить уведомление при 80%+ использования
  - Проверить уведомление при 100%+ использования
  - Проверить что отображение ограничено до лимита
  - Проверить команду `/subscribe` с кнопками
  - Проверить команду `/buy` с кнопками
  - Проверить работу кнопки Stars (если есть тестовый токен)

### Verification

- [ ] Все тесты проходят
- [ ] Линтеры не выдают ошибок
- [ ] mypy проходит без ошибок
- [ ] При 80%+ показывается "почти исчерпан"
- [ ] При 100%+ показывается "исчерпан"
- [ ] Отображение ограничено до лимита
- [ ] Команды `/subscribe` и `/buy` показывают кнопки
- [ ] Кнопки Stars работают (создают invoice)
- [ ] Кнопки YooKassa показывают заглушку

---

## Final Verification

- [ ] All acceptance criteria met
- [ ] Tests passing (`uv run pytest tests/unit/ -v`)
- [ ] Linters passing (`uv run ruff check src/`, `uv run black --check src/`)
- [ ] Type checking passing (`uv run mypy src/`)
- [ ] Manual testing completed
- [ ] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
