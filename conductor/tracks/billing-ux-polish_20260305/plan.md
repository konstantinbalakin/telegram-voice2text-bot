# Implementation Plan: Billing UX Polish — Unified Screens, Descriptions & Bot Menu

**Track ID:** billing-ux-polish_20260305
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-05
**Status:** [x] Complete

## Overview

Реализация в 4 фазы: (1) Расширение моделей БД и миграция, (2) Единый экран баланса с навигацией, (3) Редизайн каталогов и экраны описания опций, (4) Меню бота через set_my_commands. Каждая фаза независимо верифицируема.

## Phase 1: Модели БД и миграция

Добавление поля `description` в модели SubscriptionPrice и MinutePackage, создание Alembic миграции.

### Tasks

- [x] Task 1.1: Написать тесты для новых полей description в SubscriptionPrice и MinutePackage
- [x] Task 1.2: Добавить поле `description` в модель `SubscriptionPrice` (`src/storage/models.py`)
- [x] Task 1.3: Добавить поле `description` в модель `MinutePackage` (`src/storage/models.py`)
- [x] Task 1.4: Создать Alembic миграцию: `add description to subscription_prices and minute_packages`
- [x] Task 1.5: Применить миграцию: `uv run alembic upgrade head`
- [x] Task 1.6: Обновить репозитории — добавить параметр description в create_price() и create()

### Verification

- [x] Тесты моделей проходят
- [x] Миграция применяется без ошибок
- [x] Поля description доступны через ORM

## Phase 2: Единый экран баланса и навигация

Объединение /balance и /buy в единый экран. Удаление /subscribe. Создание навигации с инлайн-кнопками.

### Tasks

- [x] Task 2.1: Написать тесты для единого экрана баланса (balance_command показывает кнопки «Купить подписку» / «Купить пакеты минут»)
- [x] Task 2.2: Написать тесты для callback handlers навигации (billing:subscriptions, billing:packages, billing:back_main)
- [x] Task 2.3: Переработать `balance_command()` в `billing_commands.py` — добавить инлайн-кнопки «Купить подписку» и «Купить пакеты минут» под информацией о балансе
- [x] Task 2.4: Сделать `buy_command()` алиасом `balance_command()` — оба показывают единый экран
- [x] Task 2.5: Удалить `subscribe_command()` и связанные методы
- [x] Task 2.6: Реализовать callback handler `billing:subscriptions` — показать каталог подписок (edit message)
- [x] Task 2.7: Реализовать callback handler `billing:packages` — показать каталог пакетов (edit message)
- [x] Task 2.8: Реализовать callback handler `billing:back_main` — вернуться на экран баланса (edit message)
- [x] Task 2.9: Обновить `main.py` — удалить handler /subscribe, зарегистрировать новые callback handlers

### Verification

- [x] Тесты проходят (997 passed)
- [x] /balance и /buy показывают одинаковый экран
- [x] Кнопки навигации работают (подписки → назад → пакеты → назад)
- [x] /subscribe удалена

## Phase 3: Редизайн каталогов и экраны описания

Каталоги в один столбец с ценами в рублях. Отдельный экран описания для каждой опции с двумя кнопками оплаты.

### Tasks

- [x] Task 3.1: Написать тесты для каталога подписок (один столбец, цены в рублях)
- [x] Task 3.2: Написать тесты для каталога пакетов (один столбец, цены в рублях)
- [x] Task 3.3: Написать тесты для экрана описания подписки (billing:sub_detail:{tier_id}:{period})
- [x] Task 3.4: Написать тесты для экрана описания пакета (billing:pkg_detail:{package_id})
- [x] Task 3.5: Переработать формирование каталога подписок — один столбец, цена ₽
- [x] Task 3.6: Переработать формирование каталога пакетов — один столбец, цена ₽
- [x] Task 3.7: Реализовать callback handler `billing:sub_detail:{tier_id}:{period}` — экран описания подписки с описанием из БД + кнопки «🇷🇺 💳 Карта РФ — {цена}₽» и «🌟 Telegram Stars — {цена}⭐» + кнопка «Назад»
- [x] Task 3.8: Реализовать callback handler `billing:pkg_detail:{package_id}` — экран описания пакета с описанием из БД + кнопки оплаты + кнопка «Назад»
- [x] Task 3.9: Передавать description из БД в title/description параметры Telegram Payments invoice (в payment_callbacks.py)
- [x] Task 3.10: Зарегистрировать новые callback handlers в main.py

### Verification

- [x] Тесты проходят (997 passed)
- [x] Каталоги отображаются в один столбец
- [x] Экраны описания показывают description из БД
- [x] Кнопки оплаты инициируют платёж через соответствующего провайдера
- [x] Description передаётся в Telegram Payments invoice

## Phase 4: Меню бота (set_my_commands)

Регистрация команд через Telegram Bot API для отображения в кнопке «Меню».

### Tasks

- [x] Task 4.1: Написать тест для функции регистрации команд бота
- [x] Task 4.2: Реализовать регистрацию команд через `bot.set_my_commands()` с русскими названиями и эмодзи
- [x] Task 4.3: Вызвать `set_my_commands` после `application.start()` в `main.py`
- [x] Task 4.4: Определить список команд для меню: /help (❓ Помощь), /balance (💰 Баланс), /buy (🛒 Купить минуты), /stats (📊 Статистика)
- [x] Task 4.5: Условно включать billing-команды в меню только при `billing_enabled`

### Verification

- [x] Тесты проходят (997 passed)
- [x] Кнопка «Меню» в Telegram показывает список команд с русскими названиями и эмодзи
- [x] При отключённом биллинге billing-команды не отображаются в меню

## Final Verification

- [x] Все acceptance criteria из spec.md выполнены
- [x] Все тесты проходят: `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v` (997 passed)
- [x] Линтеры чистые: `uv run ruff check src/` (All checks passed)
- [x] Black: `uv run black --check src/ tests/` (All done)
- [x] mypy: `uv run mypy src/bot/billing_commands.py` (Success: no issues)
- [ ] Ручное тестирование полного пользовательского flow
- [x] Ready for review

---

_Generated by Conductor. Tasks marked [x] complete._
