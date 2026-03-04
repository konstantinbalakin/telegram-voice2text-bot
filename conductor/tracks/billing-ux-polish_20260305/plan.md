# Implementation Plan: Billing UX Polish — Unified Screens, Descriptions & Bot Menu

**Track ID:** billing-ux-polish_20260305
**Spec:** [spec.md](./spec.md)
**Created:** 2026-03-05
**Status:** [ ] Not Started

## Overview

Реализация в 4 фазы: (1) Расширение моделей БД и миграция, (2) Единый экран баланса с навигацией, (3) Редизайн каталогов и экраны описания опций, (4) Меню бота через set_my_commands. Каждая фаза независимо верифицируема.

## Phase 1: Модели БД и миграция

Добавление поля `description` в модели SubscriptionPrice и MinutePackage, создание Alembic миграции.

### Tasks

- [ ] Task 1.1: Написать тесты для новых полей description в SubscriptionPrice и MinutePackage
- [ ] Task 1.2: Добавить поле `description: Mapped[str | None] = mapped_column(String(500), nullable=True)` в модель `SubscriptionPrice` (`src/storage/models.py`)
- [ ] Task 1.3: Добавить поле `description: Mapped[str | None] = mapped_column(String(500), nullable=True)` в модель `MinutePackage` (`src/storage/models.py`)
- [ ] Task 1.4: Создать Alembic миграцию: `uv run alembic revision --autogenerate -m "add description to subscription_prices and minute_packages"`
- [ ] Task 1.5: Применить миграцию: `uv run alembic upgrade head`
- [ ] Task 1.6: Обновить seed-данные (если есть) — добавить описания для существующих подписок и пакетов

### Verification

- [ ] Тесты моделей проходят
- [ ] Миграция применяется без ошибок
- [ ] Поля description доступны через ORM

## Phase 2: Единый экран баланса и навигация

Объединение /balance и /buy в единый экран. Удаление /subscribe. Создание навигации с инлайн-кнопками.

### Tasks

- [ ] Task 2.1: Написать тесты для единого экрана баланса (balance_command показывает кнопки «Купить подписку» / «Купить пакеты минут»)
- [ ] Task 2.2: Написать тесты для callback handlers навигации (billing:subscriptions, billing:packages, billing:back_main)
- [ ] Task 2.3: Переработать `balance_command()` в `billing_commands.py` — добавить инлайн-кнопки «Купить подписку» и «Купить пакеты минут» под информацией о балансе
- [ ] Task 2.4: Сделать `buy_command()` алиасом `balance_command()` — оба показывают единый экран
- [ ] Task 2.5: Удалить `subscribe_command()` и связанные методы (`_build_subscribe_text_and_markup`, `back_to_subscribe_callback`)
- [ ] Task 2.6: Реализовать callback handler `billing:subscriptions` — показать каталог подписок (edit message)
- [ ] Task 2.7: Реализовать callback handler `billing:packages` — показать каталог пакетов (edit message)
- [ ] Task 2.8: Реализовать callback handler `billing:back_main` — вернуться на экран баланса (edit message)
- [ ] Task 2.9: Обновить `main.py` — удалить handler /subscribe, зарегистрировать новые callback handlers

### Verification

- [ ] Тесты проходят
- [ ] /balance и /buy показывают одинаковый экран
- [ ] Кнопки навигации работают (подписки → назад → пакеты → назад)
- [ ] /subscribe больше не существует

## Phase 3: Редизайн каталогов и экраны описания

Каталоги в один столбец с ценами в рублях и скидками. Отдельный экран описания для каждой опции с двумя кнопками оплаты.

### Tasks

- [ ] Task 3.1: Написать тесты для каталога подписок (один столбец, цены в рублях, скидки)
- [ ] Task 3.2: Написать тесты для каталога пакетов (один столбец, цены в рублях, скидки)
- [ ] Task 3.3: Написать тесты для экрана описания подписки (billing:sub_detail:{tier_id}:{period})
- [ ] Task 3.4: Написать тесты для экрана описания пакета (billing:pkg_detail:{package_id})
- [ ] Task 3.5: Переработать формирование каталога подписок — один столбец, цена ₽, скидка
- [ ] Task 3.6: Переработать формирование каталога пакетов — один столбец, цена ₽, скидка
- [ ] Task 3.7: Реализовать callback handler `billing:sub_detail:{tier_id}:{period}` — экран описания подписки с описанием из БД + кнопки «🇷🇺 💳 Карта РФ - {цена}₽» и «🌟 Telegram Stars - {цена}⭐» + кнопка «Назад»
- [ ] Task 3.8: Реализовать callback handler `billing:pkg_detail:{package_id}` — экран описания пакета с описанием из БД + кнопки оплаты + кнопка «Назад»
- [ ] Task 3.9: Передавать description из БД в title/description параметры Telegram Payments invoice (в payment_callbacks.py)
- [ ] Task 3.10: Зарегистрировать новые callback handlers в main.py

### Verification

- [ ] Тесты проходят
- [ ] Каталоги отображаются в один столбец
- [ ] Экраны описания показывают description из БД
- [ ] Кнопки оплаты инициируют платёж через соответствующего провайдера
- [ ] Description передаётся в Telegram Payments invoice

## Phase 4: Меню бота (set_my_commands)

Регистрация команд через Telegram Bot API для отображения в кнопке «Меню».

### Tasks

- [ ] Task 4.1: Написать тест для функции регистрации команд бота
- [ ] Task 4.2: Реализовать функцию `setup_bot_commands()` — регистрирует все команды через `bot.set_my_commands()` с русскими названиями и эмодзи
- [ ] Task 4.3: Вызвать `setup_bot_commands()` в `post_init` callback при старте бота в `main.py`
- [ ] Task 4.4: Определить список команд для меню: /help (❓ Помощь), /balance (💰 Баланс), /buy (🛒 Купить минуты) + другие активные команды
- [ ] Task 4.5: Условно включать billing-команды в меню только при `billing_enabled`

### Verification

- [ ] Тесты проходят
- [ ] Кнопка «Меню» в Telegram показывает список команд с русскими названиями и эмодзи
- [ ] При отключённом биллинге billing-команды не отображаются в меню

## Final Verification

- [ ] Все acceptance criteria из spec.md выполнены
- [ ] Все тесты проходят: `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v`
- [ ] Линтеры чистые: `uv run ruff check src/ && uv run black --check src/ tests/`
- [ ] Типы верные: `uv run mypy src/`
- [ ] Ручное тестирование полного пользовательского flow
- [ ] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
