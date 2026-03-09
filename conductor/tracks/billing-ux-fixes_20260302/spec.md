# Specification: Billing UX Fixes

**Track ID:** billing-ux-fixes_20260302
**Type:** Bug
**Created:** 2026-03-02
**Status:** Draft

## Summary

Исправление трёх проблем с пользовательским интерфейсом системы биллинга: некорректное сообщение о дневном лимите, отображение использованных минут сверх лимита, отсутствие inline кнопок оплаты в командах `/subscribe` и `/buy`.

## Context

Система биллинга (Track: billing-system_20260302) уже реализована и работает, но найдены баги в пользовательском интерфейсе:

1. Сообщение "Дневной лимит почти исчерпан!" показывается даже когда лимит ВЕСЬ исчерпан (100%+)
2. Отображение "Использовано: 20.9 из 10.0 мин" - число вылезло за пределы лимита
3. Команды `/subscribe` и `/buy` показывают только текст с ценами, без inline кнопок оплаты

Платёжная инфраструктура написана (TelegramStarsProvider, YooKassaProvider), но не подключена:
- Провайдеры не зарегистрированы в main.py
- Отсутствуют обработчики callback-кнопок
- Отсутствуют обработчики pre_checkout_query и successful_payment для Telegram Stars

## Problem Description

### Шаги воспроизведения:

1. **Проблема 1 и 2**:
   - Пользователь имеет дневной лимит 10.0 мин
   - Отправляет аудиофайл на ~20.5 мин
   - Получает сообщение:
     ```
     ⚠️ Дневной лимит почти исчерпан!

     Использовано: 20.9 из 10.0 мин
     Бонусные минуты: 49.1
     Пакетные минуты: 0.0

     Используйте /buy или /subscribe для пополнения.
     ```

2. **Проблема 3**:
   - Пользователь вводит `/subscribe`
   - Видит текст с ценами подписок, но нет кнопок оплаты
   - Пользователь вводит `/buy`
   - Видит текст с пакетами минут, но нет кнопок оплаты

### Ожидаемое поведение:

**Проблема 1**:
- Если `daily_used >= daily_limit` → сообщение "⛔ Дневной лимит исчерпан!"
- Если `0.8 <= daily_used/daily_limit < 1.0` → сообщение "⚠️ Дневной лимит почти исчерпан!"

**Проблема 2**:
- Отображение "Использовано: 10.0 из 10.0 мин" (используется `min(daily_used, daily_limit)`)

**Проблема 3**:
- Команды `/subscribe` и `/buy` показывают inline кнопки оплаты
- Для Telegram Stars — рабочие кнопки (создают invoice)
- Для YooKassa — заглушка "💳 Оплата картой скоро будет доступна"

### Фактическое поведение:

**Проблема 1**:
- Сообщение "⚠️ Дневной лимит почти исчерпан!" показывается даже при 100%+ использования

**Проблема 2**:
- Отображение "Использовано: 20.9 из 10.0 мин" (число превышает лимит)

**Проблема 3**:
- Команды показывают только текст без кнопок оплаты

## Affected Areas

- `src/services/billing_service.py` — логика определения статуса лимита
- `src/services/transcription_orchestrator.py` — формирование уведомления о лимите
- `src/bot/billing_commands.py` — команды `/subscribe` и `/buy` без кнопок
- `src/main.py` — отсутствует регистрация провайдера платежей и обработчиков
- Новый файл: `src/bot/payment_callbacks.py` — обработчики callback-кнопок

## Root Cause Hypothesis

1. `should_warn_limit()` проверяет только порог (80%), но не учитывает случай `daily_used >= daily_limit`
2. Уведомление использует `balance.daily_used` напрямую без ограничения до `daily_limit`
3. TelegramStarsProvider не зарегистрирован в main.py и отсутствуют обработчики callback-кнопок

## Acceptance Criteria

- [ ] При `daily_used >= daily_limit` показывается сообщение "Дневной лимит исчерпан!"
- [ ] При `0.8 <= daily_used/daily_limit < 1.0` показывается сообщение "Дневной лимит почти исчерпан!"
- [ ] В уведомлении о лимите отображается `min(daily_used, daily_limit)` вместо `daily_used`
- [ ] Команда `/subscribe` показывает inline кнопки оплаты для всех подписок
- [ ] Команда `/buy` показывает inline кнопки оплаты для всех пакетов
- [ ] Кнопки Telegram Stars создают invoice и перенаправляют на страницу оплаты
- [ ] Кнопки YooKassa показывают заглушку "Оплата картой скоро будет доступна"
- [ ] TelegramStarsProvider зарегистрирован в main.py
- [ ] Обработчики pre_checkout_query и successful_payment зарегистрированы для Telegram Stars
- [ ] Все тесты проходят
- [ ] mypy проходит без ошибок

## Dependencies

- Track: `billing-system_20260302` — существующая система биллинга
- Существующий код: `BillingService`, `SubscriptionService`, `PaymentService`
- Существующие провайдеры: `TelegramStarsProvider`, `YooKassaProvider`

## Out of Scope

- Полноценная интеграция YooKassa (только заглушка для UI)
- Реферальная программа
- Промокоды и акции
- Админ-панель для управления тарифами

## Technical Notes

### Решение проблемы 1 и 2:

**BillingService** — добавить метод `get_limit_status(user_id)`:
- Возвращает `"exhausted"` если `daily_used >= daily_limit`
- Возвращает `"warning"` если `0.8 <= daily_used/daily_limit < 1.0`
- Возвращает `"ok"` если `daily_used/daily_limit < 0.8`

**TranscriptionOrchestrator** — обновить логику уведомления:
- Использовать `get_limit_status()` вместо `should_warn_limit()`
- Показывать `min(balance.daily_used, balance.daily_limit)` в уведомлении

### Решение проблемы 3:

**PaymentCallbackHandlers** — новый файл `src/bot/payment_callbacks.py`:
- `buy_package_stars_callback()` — создаёт платёж через Telegram Stars
- `buy_subscription_stars_callback()` — создаёт платёж через Telegram Stars
- `buy_package_card_callback()` — показывает заглушку для YooKassa
- `buy_subscription_card_callback()` — показывает заглушку для YooKassa
- `pre_checkout_query_handler()` — подтверждает pre-checkout query для Telegram Stars
- `successful_payment_handler()` — обрабатывает успешный платёж

**BillingCommands** — обновить команды `/subscribe` и `/buy`:
- Добавить inline кнопки с `InlineKeyboardMarkup`
- Callback data формат: `pkg_stars:{id}`, `sub_stars:{id}:{period}`, `pkg_card:{id}`, `sub_card:{id}:{period}`

**main.py** — зарегистрировать компоненты:
- Импортировать `TelegramStarsProvider`, `PaymentCallbackHandlers`
- Создать и зарегистрировать `telegram_stars_provider` через `payment_service.register_provider()`
- Создать `payment_callback_handlers`
- Зарегистрировать `CallbackQueryHandler` для кнопок оплаты
- Зарегистрировать `PreCheckoutQueryHandler` для pre-checkout
- Зарегистрировать `MessageHandler(filters.SUCCESSFUL_PAYMENT, ...)` для успешного платежа
- Сохранить `payment_service` в `application.application_data` для обработчиков

---

_Generated by Conductor. Review and edit as needed._
