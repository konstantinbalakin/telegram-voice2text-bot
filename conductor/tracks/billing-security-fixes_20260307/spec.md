# Specification: Исправление критических проблем безопасности и надёжности биллинга

**Track ID:** billing-security-fixes_20260307
**Type:** Bug/Fix
**Created:** 2026-03-07
**Status:** Draft

## Summary

Комплексное исправление 27 проблем безопасности, надёжности и качества кода в платёжной системе, выявленных при PR review ветки `feature/billing-system`. Включает критические уязвимости платежей, race conditions, fail-open→fail-closed переход, тестовое покрытие и type design.

## Context

PR `feature/billing-system` добавляет полноценную систему биллинга (~14,800 строк): подписки, пакеты минут, оплата через YooKassa и Telegram Stars, лимиты дневного использования. Комплексное ревью выявило критические проблемы безопасности в платёжной логике, которые необходимо исправить до мерджа в main.

## Problem Description

### CRITICAL (7 проблем — блокируют мердж)

1. **Pre-checkout query всегда `ok=True`** (`payment_callbacks.py:388-394`) — нет валидации payload и суммы перед списанием денег
2. **IDOR: user_id из payload не верифицируется** (`payment_callbacks.py:411-428`) — минуты могут зачислиться чужому пользователю через публичную invoice ссылку
3. **Period не передаётся в payload подписки** (`payment_service.py:145`) — все подписки активируются как месячные вместо оплаченного периода
4. **Race condition при списании минут** (`billing_service.py:197-294`, `billing_repositories.py:519-528`) — read-modify-write без блокировки → двойное использование
5. **Fail-open при сбоях биллинга** (`handlers.py:433-465`, `orchestrator.py:785-840`, `main.py:200-250`) — бесплатный доступ при ошибках БД → переход на fail-closed
6. **Оплата прошла, зачисление упало** (`payment_service.py:196-215`) — ValueError при отсутствии пакета, Purchase вечно PENDING, деньги потеряны
7. **Отсутствие идемпотентности** (`payment_service.py:144-194`) — повторная доставка successful_payment → двойное начисление

### IMPORTANT (10 проблем)

8. **Утечка деталей ошибок** (`yookassa_provider.py:85-90`) — `str(e)` может содержать токены/URL
9. **Списание ПОСЛЕ отправки результата** (`orchestrator.py:778-840`) — при крэше бесплатная транскрипция
10. **Purchase не маркируется FAILED** (`payment_service.py:144-194`) — нет данных для аудита ошибок
11. **5 callback'ов глотают ошибки** (`billing_commands.py:142,207,265,338,390`) — пользователь не видит фидбек
12. **`assert` в production** (`payment_service.py:221`, `billing_service.py:86-90`) — отключается с `-O`
13. **`rollback()` в `get_or_create`** (`billing_repositories.py:581`) — может откатить чужие операции, нужен savepoint
14. **Float для денег** (`models.py`) — ошибки округления в финансовых расчётах
15. **Дублирование кода** — `_period_label` (2 копии), `parse_payload` (3 копии)
16. **Приватный метод вызывается снаружи** (`_build_balance_text_and_markup` из 2 модулей)
17. **Shortfall тихо логируется** (`billing_service.py:260-264`) — warning без последствий

### Test Coverage Gaps (5 проблем)

18. `successful_payment_handler` с невалидным payload — критичность 9/10
19. Конвертация RUB amount в `create_payment` (копейки→рубли) — критичность 9/10
20. `handle_successful_payment` когда purchase не найден — критичность 8/10
21. Невалидный формат callback_data (`"pkg_stars:abc"`) — критичность 8/10
22. `/start` с welcome bonus + ошибка в `grant_welcome_bonus` — критичность 7/10

### Type Design (5 проблем)

23. Float→Integer для денежных сумм (копейки) + миграция
24. Добавить CHECK constraints (`minutes >= 0`, `amount > 0`, `started_at < expires_at`)
25. UserBalance — вычисляемые `@property` вместо дублирования + `frozen=True`
26. Очистить мёртвый код (`PaymentStatus`, `Currency` enum, `_get_user_db_id`)
27. Partial unique index на active подписку (1 active на user)

## Acceptance Criteria

- [ ] Pre-checkout query валидирует payload и проверяет сумму
- [ ] User ID из payload сверяется с effective_user при обработке платежа
- [ ] Period подписки передаётся в payload и корректно активируется
- [ ] Повторная обработка платежа не создаёт дубликатов (идемпотентность по transaction_id)
- [ ] Race condition при списании решён (asyncio.Lock по user_id для SQLite)
- [ ] Fail-closed: ошибка биллинга блокирует транскрипцию с сообщением пользователю
- [ ] Ошибка инициализации биллинга = fatal (бот не стартует)
- [ ] Ошибка зачисления после оплаты → Purchase маркируется FAILED + лог CRITICAL
- [ ] Все error messages пользователю generic (без внутренних деталей)
- [ ] Денежные суммы хранятся как Integer (копейки) с миграцией
- [ ] CHECK constraints на неотрицательность финансовых полей
- [ ] 5 недостающих тестов добавлены
- [ ] Все CI проверки проходят (ruff, black, mypy, pytest)

## Dependencies

- Текущая ветка `feature/billing-system` — все исправления в этой же ветке
- Alembic миграции для Float→Integer и CHECK constraints

## Out of Scope

- Переход на PostgreSQL (планируется отдельным треком)
- `SELECT FOR UPDATE` (не поддерживается SQLite, решаем через asyncio.Lock)
- Рефакторинг DI (множественные сессии в одном запросе — отдельный трек)
- Dashboard мониторинга и алертинга (отдельный трек)
- Тесты для `billing_broadcast.py` (одноразовая утилита)

## Technical Notes

- Для race condition в SQLite: `asyncio.Lock` по user_id в `deduct_minutes` (не `FOR UPDATE`)
- Float→Integer миграция: `op.alter_column` с `server_default`, batch mode для SQLite
- Идемпотентность: проверка `provider_transaction_id` в таблице Purchase перед начислением
- Fail-closed: убрать try/except в handlers.py, пробрасывать ошибку биллинга наверх

---

_Generated by Conductor. Review and edit as needed._
