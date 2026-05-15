<div align="center">

<img src="assets/readme/hero.png" alt="Mnemora hero" width="720">

# Mnemora — Telegram Business Save Mode & AI Assistant

**Персональный Telegram Business ассистент с локальной памятью, SAVE MODE, AI-выжимками и безопасными черновиками ответов.**

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![Telethon](https://img.shields.io/badge/Telethon-legacy-0088CC?style=for-the-badge&logo=telegram&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite%20%2B%20FTS5-local-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![LLM](https://img.shields.io/badge/Claude%20%7C%20OpenAI%20%7C%20Gemini-supported-111827?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

</div>

## 📌 Быстрая Сводка

| Раздел | Описание |
| --- | --- |
| Основной режим | Telegram Business automation bot через Bot API |
| SAVE MODE | Сохраняет удалённые сообщения, правки и доступные медиа |
| AI Assistant | Поиск, summary, catchup, задачи, напоминания, дайджесты |
| Локальная память | SQLite + FTS5, без внешнего векторного сервиса по умолчанию |
| Legacy mode | Telethon userbot остаётся как optional backend для отдельных legacy-сценариев |

## ✨ Основные Возможности

| Возможность | Что делает |
| --- | --- |
| Telegram Business mode | Бот подключается в Telegram: `Настройки -> Telegram Business -> Чат-боты` |
| Удалённые сообщения | Помечает сообщения удалёнными и присылает владельцу сохранённую копию |
| История правок | Сохраняет старый и новый текст, показывает аккуратное уведомление |
| Медиа | Скачивает фото, видео, документы, стикеры и другие доступные Bot API файлы |
| Истекающие медиа | Пытается сохранить сразу, если Telegram Bot API отдаёт файл обычным способом |
| Скрытые voice/audio | Обычные voice/audio не сохраняются; одноразовые сохраняются только reply-действием владельца |
| Поиск | `/search текст` ищет по локальной базе через SQLite FTS5 |
| AI | Поддерживает Anthropic Claude, OpenAI и Gemini через единый LLM router |
| Черновики ответов | Любая отправка от имени Business-аккаунта идёт через inline-подтверждение |
| Dot commands | `.mute`, `.info`, `.repeat`, `.type`, `.love` работают в Business mode в том же чате |

## 🧩 Telegram Business Mode

Это основной режим Mnemora. Он работает как обычный Telegram-бот, подключённый к твоему Business-аккаунту.

### Как подключить

1. Открой Telegram.
2. Перейди в `Настройки`.
3. Открой `Telegram Business`.
4. Выбери `Чат-боты` или `Автоматизация чатов`.
5. Выбери своего бота.
6. Дай права на управление сообщениями и доступ к нужным личным чатам.
7. Вернись в Mnemora и отправь `/business_status`.

Mnemora принимает business updates:

| Update | Назначение |
| --- | --- |
| `business_connection` | Сохраняет подключение, права и статус |
| `business_message` | Сохраняет новые сообщения и доступные медиа |
| `edited_business_message` | Сохраняет историю правок |
| `deleted_business_messages` | Помечает сообщения удалёнными и уведомляет владельца |

## 🗑 SAVE MODE

SAVE MODE работает только с тем, что Telegram реально отдаёт боту через Bot API или Telethon.

| Событие | Поведение |
| --- | --- |
| Удаление | Присылает владельцу текст, автора, чат, время и сохранённое медиа, если оно есть |
| Правка | Показывает `Было` и `Стало`, без лишних рекламных строк |
| Фото/видео | Отправляет как вложение с подписью, а не отдельным файлом-документом |
| Обычные voice/audio | Не сохраняются, чтобы не засорять архив |
| Одноразовые voice/audio | Сохраняются только когда владелец отвечает на скрытое сообщение, и Bot API даёт файл |
| Недоступное медиа | Сохраняется metadata: chat_id, message_id, media type, status/error |

Mnemora не обходит protected content, view-once, DRM или приватные ограничения Telegram. Если API не отдаёт файл, проект сохраняет только metadata.

## 🤖 AI Assistant

AI-функции работают по локально сохранённым business messages и не отправляют всю историю в LLM.

| Команда | Назначение |
| --- | --- |
| `/summary чат` | Краткая выжимка последних сообщений |
| `/catchup чат` | Где остановились и что важно помнить |
| `/todos` | Задачи, обещания и дедлайны |
| `/remind фраза` | Напоминание из обычного текста |
| `/digest now` | Дайджест по важным чатам |
| `/autoreply on/off` | Автоответчик, выключен по умолчанию |

LLM router поддерживает:

- `anthropic` / Claude через `ANTHROPIC_API_KEY`
- `openai` через `OPENAI_API_KEY`
- `gemini` через `GEMINI_API_KEY`

## ⚡ Dot Commands

Dot-команды в основном режиме `TELEGRAM_MODE=business` выполняются через Telegram Business Bot API и `business_connection_id` прямо в том же чате, где ты их вызвал.  
Control-бот в ЛС используется для настроек, логов и уведомлений SAVE MODE.

| Команда | Описание |
| --- | --- |
| `.mute` | Hard mute текущего чата: входящие сообщения сохраняются в Mnemora и удаляются из переписки, если Telegram позволит |
| `.unmute` | Выключает hard mute для текущего чата |
| `.info` | Показывает доступную Telegram API информацию о пользователе. Использовать reply на сообщение |
| `.type текст` | Показывает typing и отправляет текст |
| `.repeat n текст` | Ограниченный повтор текста в текущий чат с плавающей задержкой |
| `.spam n текст` | Alias для `.repeat`, не массовая рассылка |
| `.spam_stop` | Остановить активный repeat/spam в текущем чате |
| `.love` | Короткая безопасная анимация до 5 сообщений |

Важно:

- `.mute` hard mode в business режиме пытается удалить сообщение через `deleteBusinessMessages`; итог зависит от прав Telegram Business.
- Удаление “для всех” может не сработать из-за ограничений Telegram.
- `.info` не показывает дату регистрации: официально она недоступна через Telegram API.
- `.spam` не делает массовую рассылку, не ходит по спискам чатов и ограничен текущим диалогом.
- Для repeat используется плавающая задержка `REPEAT_DELAY_MIN_SECONDS..REPEAT_DELAY_MAX_SECONDS`.

## 🛠 Установка

```bash
git clone https://github.com/22Warm-XD/natursavebot.git
cd natursavebot
cp .env.example .env
```

Сгенерируй ключ шифрования:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Вставь результат в `ENCRYPTION_KEY`.

## ⚙️ Настройка `.env`

Минимальный набор:

```env
BOT_TOKEN=
OWNER_TELEGRAM_ID=
ENCRYPTION_KEY=

TELEGRAM_MODE=business
DATABASE_URL=sqlite+aiosqlite:///data/app.db
MEDIA_DIR=data/media

SAVE_MODE_ENABLED=true
SAVE_MEDIA_ENABLED=true
MAX_MEDIA_SIZE_MB=50

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

Полный список параметров лежит в `.env.example`.

## 🐳 Запуск Через Docker

```bash
docker compose up -d --build
docker compose logs -f mnemora
```

Остановить:

```bash
docker compose down
```

## 💻 Локальный Запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.main
```

Для Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

## 📋 Команды

### Business / SAVE MODE

| Команда | Описание |
| --- | --- |
| `/start` | Onboarding и краткая инструкция подключения |
| `/business_status` | Статус Telegram Business подключения |
| `/savemode on` | Включить SAVE MODE |
| `/savemode off` | Выключить SAVE MODE |
| `/savemode_settings` | Inline-настройки SAVE MODE |
| `/deleted` | Последние удалённые сообщения |
| `/edits` | Последние правки |
| `/media` | Последние сохранённые медиа |
| `/search текст` | Поиск по локальной базе |
| `/chat имя/id` | Карточка чата |
| `/health` | Проверка БД, медиа-папки, LLM и Business connection |

### AI

| Команда | Описание |
| --- | --- |
| `/summary чат` | Выжимка последних сообщений |
| `/catchup чат` | Где остановились |
| `/todos` | Задачи и обещания |
| `/remind фраза` | Создать напоминание |
| `/digest now/on/off/at HH:MM` | Дайджесты |
| `/autoreply on/off` | Автоответчик |
| `/reply имя | текст` | Черновик ответа с inline-подтверждением |

### Dot Commands

| Команда | Описание |
| --- | --- |
| `.mute` | Hard mute текущего чата |
| `.unmute` | Выключить hard mute |
| `.info` | Информация о пользователе через reply |
| `.type текст` | Typing + отправка текста |
| `.spam n текст` | Ограниченный повтор, alias |
| `.repeat n текст` | Ограниченный повтор, рекомендуемое имя |
| `.spam_stop` | Остановить активный repeat |
| `.love` | Короткая анимация |

## ⚠️ Ограничения Telegram API

- Mnemora не восстанавливает сообщения, отправленные до подключения бота.
- Бот видит только чаты, к которым владелец дал доступ в Telegram Business.
- Protected/view-once/self-destruct медиа сохраняются только если Telegram API отдаёт файл обычным способом.
- Обычные voice/audio не архивируются; одноразовые voice/audio сохраняются через reply-сценарий владельца.
- Дата регистрации пользователя недоступна через официальный Telegram API.
- Удаление “для всех” в hard mute может быть запрещено Telegram.

## 🧱 Структура Проекта

```text
src/
  main.py
  config.py
  db/
    models.py
    repositories/
  bot/
    handlers/
  business_bot/
    handlers.py
    media_downloader.py
    notifications.py
    sender.py
  userbot/
    commands.py
    events.py
    media.py
  services/
    llm/
    hard_mute.py
    save_mode_business.py
tests/
legacy/
assets/
data/
```

## 🖼 Скриншоты

Скриншоты будут добавлены после первого стабильного production-запуска без личных данных и секретов.

## 🧪 Проверка

```bash
python -m compileall src tests
python -m pytest
```

Если установлен Docker:

```bash
docker compose config
```

---

<div align="center">

**Mnemora сохраняет память Telegram аккуратно: без обходов, без лишней магии и без утечки секретов.**

</div>
