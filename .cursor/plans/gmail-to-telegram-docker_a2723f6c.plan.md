---
name: gmail-to-telegram-docker
overview: Docker-контейнер с Python-сервисом, который каждую минуту проверяет Gmail по IMAP, скачивает вложения из новых писем и отправляет их в Telegram-канал с датой получения письма; состояние (UID) хранится в volume.
todos:
  - id: scaffold-python-service
    content: Создать минимальную структуру Python-сервиса (IMAP poller, Telegram sender, state).
    status: completed
  - id: add-deps-and-config
    content: Добавить requirements.txt, env-конфиг, обработку TZ и формата даты получения письма.
    status: completed
  - id: dockerize
    content: Добавить Dockerfile и docker-compose.yml с volume для state и безопасной передачей секретов.
    status: completed
  - id: docs
    content: Добавить README.md с инструкцией настройки Gmail App Password и добавления бота в канал.
    status: completed
  - id: github-ready
    content: Подготовить репозиторий к публикации в GitHub (.gitignore для .env, .env.example без секретов, краткая секция в README про secrets).
    status: completed
isProject: false
---

# План: Gmail вложения → Telegram (Docker, Python)

## Цель
- Сервис в контейнере **каждую минуту** подключается к Gmail по **IMAP**, находит **новые письма** (UNSEEN + защита по UID), скачивает **вложения** и отправляет их в **Telegram-канал** как документы с подписью вида: дата/время получения (локальная TZ) + (опционально) тема/отправитель.

## Предпосылки/ограничения
- **Gmail**: доступ по IMAP + **App Password** (2FA включена, IMAP разрешён).
- **Telegram**: бот добавлен в канал и имеет право публиковать (обычно достаточно сделать бота админом канала).
- Секреты и идентификаторы (**GMAIL_EMAIL**, **GMAIL_APP_PASSWORD**, **TELEGRAM_BOT_TOKEN**, **TELEGRAM_CHAT_ID**) **не** хардкодим и **не** кладём в репозиторий — только через переменные окружения (и/или Docker secrets).

## Файлы/структура (предлагаемая)
- `[app/main.py](app/main.py)`: основной цикл (poll каждую минуту)
- `[app/gmail_imap.py](app/gmail_imap.py)`: IMAP подключение, поиск писем, парсинг, скачивание вложений
- `[app/telegram.py](app/telegram.py)`: отправка документов в канал (Bot API)
- `[app/state.py](app/state.py)`: хранение `last_uid` + обработанные message-id/uid
- `[requirements.txt](requirements.txt)`: зависимости (например `python-telegram-bot` или `requests`)
- `[Dockerfile](Dockerfile)`: slim-образ, non-root, healthcheck (опционально)
- `[docker-compose.yml](docker-compose.yml)`: сервис + volume для state
- `[README.md](README.md)`: как запустить, какие env нужны
- `[.gitignore](.gitignore)`: игнорировать `.env`, локальные артефакты (`__pycache__/`, `.venv/`, `data/`)
- `[.env.example](.env.example)`: список переменных **без значений секретов** (шаблон)

## Конфигурация (env)
- **GMAIL_IMAP_HOST**=`imap.gmail.com`
- **GMAIL_IMAP_PORT**=`993`
- **GMAIL_EMAIL**=`...@gmail.com` (логин)
- **GMAIL_APP_PASSWORD**=`...` (пароль приложения Gmail)
- **MAILBOX**=`INBOX`
- **POLL_SECONDS**=`60`
- **TELEGRAM_BOT_TOKEN**=`...`
- **TELEGRAM_CHAT_ID**=`@your_channel` или числовой id (id канала/чата)
- **TZ**=`Europe/Moscow` (или ваша)
- **STATE_PATH**=`/data/state.json`

## Логика обработки писем
- Подключиться по IMAP SSL.
- Получить список `UNSEEN` сообщений.
- Для каждого сообщения:
  - Вытащить UID, `Message-ID`, дату `Date` (RFC 2822) и тему/отправителя.
  - Проверить, не меньше ли UID чем `last_uid` в state (двойная защита от дублей).
  - Скачать **все вложения** (пропустить inline-картинки без filename, по настройке).
  - Для каждого вложения:
    - Отправить в Telegram как `sendDocument` (multipart upload) с подписью: `YYYY-MM-DD HH:mm (TZ) — <subject>`.
  - При успешной отправке всех вложений:
    - Пометить письмо как `\Seen`.
    - Обновить state (`last_uid = max(last_uid, uid)` + опционально set обработанных IDs).

## Надёжность
- Ретраи при временных ошибках (IMAP reconnect, Telegram 429/5xx) с backoff.
- Ограничение размера: если файл слишком большой для Telegram Bot API (лимит зависит от API/версии), логируем и пропускаем/режем поведение по настройке.
- Идемпотентность: state в volume, чтобы после рестарта не пересылать старые вложения.

## Docker/Compose
- `Dockerfile`: `python:3.12-slim`, установка зависимостей, копирование кода, запуск `python -m app.main`.
- `docker-compose.yml`:
  - монтируем volume `data:/data`
  - env через `.env` (в `.gitignore`)

## Публикация в GitHub (безопасно)
- **Да, можно**: код, `Dockerfile`, `docker-compose.yml`, `README.md`, `requirements.txt` — обычно коммитятся.
- **Не коммитить**: `.env`, `state.json`/volume-данные, любые экспортированные логи с секретами.
- **Шаблон для других**: `.env.example` только с именами переменных и комментариями, без реальных токенов/паролей.
- Если позже понадобится CI/CD: секреты хранить в **GitHub Actions Secrets** / **Dependabot** не трогать `.env` в репозитории.

## Тест-план (ручной)
- Отправить себе письмо с 1 вложением → убедиться, что файл пришёл в канал с корректной датой.
- Отправить письмо без вложений → ничего не отправляется, письмо (опционально) помечается как прочитанное.
- Перезапуск контейнера → старые письма не переотправляются.

