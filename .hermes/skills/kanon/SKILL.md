---
name: kanon
description: Use when the user mentions kanon, a kanon feature ID, "продолжай доработку", "что делать дальше" in a kanon-managed repo, or asks to start/continue work on any feature. Single entry router: reads kanon/STATUS.md + machine state and routes to the right stage skill.
---

# kanon — вход-роутер (R13)

Ты работаешь в репо под управлением kanon. НЕ выбирай сам стадию —
определи её по артефактам на диске.

## Шаг 1. Собери состояние

1. Прочитай `kanon/STATUS.md` (якорь) и секцию «kanon» в `AGENTS.md`.
2. Если CLI доступен: `python -m kanon status --json` (из папки `cli/`
   канон-репо, или установленный `kanon status`).
3. Если CLI нет — деградационный режим, руками:
   - статусы: frontmatter `status:` в `kanon/features/*/feature.md`
   - прогресс: чекбоксы в `kanon/features/*/plan.md`
   - итерации: `kanon/features/*/iterations/it-NNN/` со статусом ≠ resolved

## Шаг 2. Промашируй

| Ситуация | Действие |
|---|---|
| репо не под kanon, пользователь хочет подключить | `kanon init` (умный режим) или скилл установки |
| есть фича в `draft` | покажи сторис оператору → гейт approval |
| `approved` без плана | скилл `kanon-plan` |
| `planned` / `in-progress` | скилл `kanon-execute` (ближайшая незакрытая задача плана) |
| `verify` или открытые итерации | скилл `kanon-iterate` |
| всё `released` + новая задача от оператора | скилл `kanon-interview` (новая фича) |

Несколько активных фич — покажи список с «что дальше» и спроси оператора,
какую вести (или веди ту, что оператор назвал последней).

## Обновление канона в репо-потребителе

Манифест/эталоны/exit-коды — см. `kanon/features/20261018-epic-update-propagation/spike-manifest.md`.
`kanon check`: 0 — всё matching; 1 — stale/differing/missing; 2 — нет манифеста (pre-C+).
`kanon update`: 0 — ok/no-op/apply; 1 — dry-run, есть изменения; 2 — pre-C+ или битые маркеры; 3 — apply отклонён (дрейф без `--force`). Dry-run — по умолчанию, изменения только через `--apply`.

1. `kanon check` → запомни rc (0 / 1 / 2).
2. rc=2 → первичная миграция: `kanon init --force` с тем же пресетом
   (`kanon/config.toml`), затем повторный `kanon check` → дальше по циклу.
3. rc=1 → `kanon update` (dry-run) → покажи дифф ОПЕРАТОРУ до любых изменений.
4. Apply: `kanon update --apply`; локальный дрейф managed-контента —
   только после решения оператора (`--apply --force`), сам не решай.
5. `kanon check` → rc=0.
6. Коммит с осмысленным сообщением (один коммит на обновление).

Never-touched (update их не пишет и агент не трогает руками): `features/`,
STATUS-строки, WHATSNEW-история. Контент AGENTS.md вне маркеров
`<!-- kanon:begin ... -->` / `<!-- kanon:end -->` не трогается НИКОГДА.

## Правила

- Переход статуса — отдельным коммитом; `draft→approved` — только оператор.
- Новая папка фичи: `kanon/features/YYYYMMDD-<category>-<slug>/`,
  категории: epic|story|bug|fix|docs|chore.
- После каждой стадии: обнови frontmatter + `status-log.json` + `kanon/STATUS.md`.
- Перед коммитом фичи: `kanon check` (или ручная проверка по features/README.md).
