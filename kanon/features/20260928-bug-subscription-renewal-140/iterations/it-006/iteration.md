---
status: open
source: operator
scenario: полигон — юзер с активной подпиской Basic (daily_limit_minutes=15) видит в /balance «Дневной лимит: 10 мин»; подписка при этом показана верно (Basic до 16.11)
---

# it-006: /balance показывает лимит 10 вместо тира 15 при активной подписке

## Что нашли

Слои рассинхронизированы по ленивой активации очереди (#140, волна 3):

- `SubscriptionService.get_active_subscription` умеет лениво активировать
  due-queued строку (и гасит stale-active, it-005).
- `BillingService._get_daily_limit_with_repos` ходит в репо напрямую
  (`get_active_subscription_with_tier`) — ленивой активации там нет.
- В `build_balance_text_and_markup` порядок вызовов: СНАЧАЛА
  `get_user_balance` (лимит по conditions/дефолту 10), ПОТОМ
  `get_active_subscription` (активирует очередь и рисует «⭐ Подписка: Basic»).

Результат: пока крон не активировал очередь, лимит считается по
`daily_free_minutes` (10), а подписка в тексте уже видна. Воспроизведено
репро на in-memory SQLite (stale-active + due-queued): до ленивой активации
`balance.daily_limit = 10.0`, после — `15.0`.

Предсуществовало: да — в `origin/main` тот же порядок вызовов в
billing_commands (баланс раньше подписки); на ветке #140 рассинхрон
усугубился появлением очереди и ленивой активации. Сам расчёт лимита в
billing_service с main не менялся.

## Что решили

Минимальная правка без дублирования бизнес-логики: в
`build_balance_text_and_markup` запрашивать активную подписку ДО расчёта
баланса — ленивая активация успевает поднять due-queued строку, и
`get_user_balance` видит уже активную подписку и берёт лимит тира
(Basic = 15, Pro = 30). Попутно убран двойной вызов
`get_active_subscription`. `subscription_service.py`, `payment_callbacks.py`,
очереди/крон не тронуты.

## Что поправили

- `src/bot/billing_commands.py::build_balance_text_and_markup`:
  `get_active_subscription` перенесён выше `get_user_balance`, старый
  повторный вызов удалён.
- `tests/unit/test_billing_limit_sub_140.py` (новый):
  - сервисный уровень: active Basic → `get_user_balance().daily_limit == 15`;
    Pro → 30; без подписки → conditions (10) / дефолт 10;
  - бот-уровень: `get_active_subscription` вызывается строго раньше
    `get_user_balance`; без подписки — прежний текст с лимитом 10;
    `get_active_subscription` вызывается ровно один раз.
