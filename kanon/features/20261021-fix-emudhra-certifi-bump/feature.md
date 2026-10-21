---
id: 20261021-fix-emudhra-certifi-bump
status: approved
title: eMudhra: образ бота не должен доверять emSign ECC Root CA - G3
---

# eMudhra: образ бота не должен доверять emSign ECC Root CA - G3

## Зачем
Октябрь 2026: скомпрометированы 8 промежуточных CA eMudhra, цепочки
якорятся на emSign ECC Root CA - G3. Прод-образ v0.0.79 доверяет этому
корню по обоим TLS-путям рантайма: certifi 2026.1.4 (requirements.txt)
и системный стор контейнера /etc/ssl/certs/ca-certificates.crt
(REQUESTS_CA_BUNDLE/SSL_CERT_FILE). Горячий фикс certifi в контейнере
живёт до пересоздания.

## Что будет
- requirements.txt: certifi==2026.1.4 → certifi==2026.10.19
- Dockerfile: `ca-certificates` в apt-get install (свежий пакет из
  bookworm-security на момент сборки)
- Dockerfile: шаг вырезания emSign ECC Root CA - G3 из
  /etc/ssl/certs/ca-certificates.crt при сборке (до COPY requirements*)
- Локальная сборка + тест-контейнер: оба TLS-пути reject на
  dv-g3b-emudhra.we-have-a-problem.com, api.telegram.org ok

## Не входит
- CI-страховка свежести certifi (В4 отклонена К.)
- Постдеплойные проверки прода (задача 6 из 0.4, после мержа PR)

## Допущения
- Пересборка обновит и прочие apt-пакеты базового образа — принятый риск
  ребилда (дизайн 0.3, Риски)

## Источник
tasks/2026-10-21-emudhra-certifi-bump/ (0.1–0.4; дизайн утверждён К.
2026-10-21, старт исполнения разрешён К. 2026-10-21)
