# План: 20261021-fix-emudhra-certifi-bump

Живой чек-лист исполнения (тикается с SHA): `tasks/2026-10-21-emudhra-certifi-bump/0.4_tasks.md`.
Дизайн: `tasks/2026-10-21-emudhra-certifi-bump/0.3_design.md` (утверждён К.).

## Волна 1 — закрытие доверия eMudhra в образе (задачи 1–4 из 0.4)

Однородная по риску волна, один исполнитель (executor), приёмка оркестратором.
Три кодовые правки + локальная сборка/тест-контейнер на kosfi:

1. `requirements.txt`: certifi==2026.1.4 → certifi==2026.10.19 (отд. коммит)
2. `Dockerfile`: `ca-certificates` в apt-get install (отд. коммит)
3. `Dockerfile`: шаг вырезания emSign ECC Root CA - G3 из бандла,
   ДО `COPY requirements*` (отд. коммит)
4. Сборка образа из ветки + тест-контейнер (коммит с логом в 0.4)

CI-паритет волны: ruff/black/mypy/pytest не затронуты (нет правок src/),
прогон test-runner'ом по матрице ниже.

## Матрица ожидаемых исходов (тест-контейнер)

| Проверка | cafile | Ожидание |
|---|---|---|
| https://dv-g3b-emudhra.we-have-a-problem.com | certifi.where() | ssl.SSLCertVerificationError |
| https://dv-g3b-emudhra.we-have-a-problem.com | /etc/ssl/certs/ca-certificates.crt | ssl.SSLCertVerificationError |
| https://api.telegram.org | certifi.where() | 200 или 302 |
| https://api.telegram.org | /etc/ssl/certs/ca-certificates.crt | 200 или 302 |
| certifi.__version__ в образе | — | 2026.10.19 |

Любой «OK» на dv-g3b-хосте = красное, волна не закрыта.

## Вне волны

- Задачи 5–6 из 0.4 (PR, постдеплой) — после приёмки волны, стадия verify.
