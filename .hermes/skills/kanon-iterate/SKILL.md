---
name: kanon-iterate
description: Use when a kanon feature has open fix iterations (iterations/it-NNN with status not resolved) — feedback/bugfix loop inside the feature, fix → re-verify → resolve.
---

# kanon-iterate — цикл фиксов (R8)

Цель: закрыть открытые итерации фичи. Итерации живут ВНУТРИ папки фичи
(`iterations/it-NNN/`), нумерация с `it-001`, без пропусков.

## Формат итерации

`iterations/it-NNN/iteration.md`:

```markdown
---
status: open          # open → resolved
source: e2e|operator  # кто нашёл
scenario: <какой сценарий/фидбек>
---

# it-NNN: <суть>

## Что нашли
<факт + сырой лог/цитата>

## Что решили
<решение оператора/агента>

## Что поправили
- <изменения, коммиты>
```

## Цикл

1. Открытая итерация (`kanon status` покажет) → понять причину по
   сырым логам (не по пересказу).
2. Фикс → коммит `feature <fid>: it-NNN fix`.
3. Повторный verify только упавшего сценария (kanon-verify).
4. Pass → `status: resolved` в iteration.md + коммит.
5. Оператор дал фидбек словами, не через сценарий → заведи итерацию
   с `source: operator` и тем же циклом.

## Правила

- Одна итерация = один дефект; несколько дефектов → несколько итераций.
- Не закрывай итерацию без повторного прогона.
- Все итерации resolved и чек-лист зелёный → released (через kanon-verify).
