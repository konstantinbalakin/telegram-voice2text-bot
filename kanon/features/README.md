# features

Папки доработок: `YYYYMMDD-<category>-<slug>`.

Категории: `epic`, `story`, `bug`, `fix`, `docs`, `chore`.

Структура папки доработки:

- `feature.md` — спека; frontmatter: `id` (= имя папки), `status`, `title`
- `plan.md` — обязателен со статуса `planned`
- `iterations/it-NNN/` — итерации фиксов (стадия `verify`), нумерация с `it-001`
- `whatsnew.md` — обязателен для статуса `released`
- `status-log.json` — история статусов: `[{"date": "YYYY-MM-DD", "status": "..."}]`,
  последний элемент обязан совпадать со статусом в frontmatter

Статусная модель: `draft → approved → planned → in-progress → verify → released`.
Переход статуса — отдельным коммитом (гейт оператора: `draft→approved`).
