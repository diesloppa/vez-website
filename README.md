# Закрытый Видеоархив

Статический архив видео, рассчитанный на две отдельные сборки:

- `site/` — production-вариант для GitHub Pages с зашифрованными данными
- `site-local/` — локальный plaintext-вариант для быстрой проверки интерфейса

Код сайта может быть открытым, а данные о видео хранятся в репозитории только в зашифрованном виде:
- `vk_raw_data.enc.json` — рабочий кэш видео для инкрементальной синхронизации
- `site/data.enc.json` — зашифрованный payload для браузера

Для локальной разработки `build_data.py` дополнительно создаёт:
- `site-local/data.js`
- `site-local/data/db.json`

После открытия сайта пользователь вводит общий пароль, и браузер сам расшифровывает архив через Web Crypto API. Любой, кто знает пароль, получает доступ к каталогу, что и является целевой моделью доступа.

## Что в репозитории

```text
.
├── .github/workflows/update-site.yml
├── .gitignore
├── README.md
├── config.example.json
├── crypto_utils.py
├── vk_config.py
├── scrape_vk_api.py
├── scrape_vk_discussions.py
├── build_playlist_meta.py
├── build_data.py
├── playlist_meta.json
├── vk_raw_data.enc.json
├── site-local/
│   ├── index.html
│   └── .nojekyll
└── site/
    ├── index.html
    ├── data.enc.json
    └── .nojekyll
```

В git не должны попадать:
- `config.json`
- `vk_discussions.json`
- `vk_raw_data.json`
- `site/data.js`
- `site/data/db.json`
- `site-local/data.js`
- `site-local/data/db.json`

## Как это работает

### 1. Сбор данных из VK

- [`scrape_vk_discussions.py`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/scrape_vk_discussions.py) обновляет `vk_discussions.json`
- [`scrape_vk_api.py`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/scrape_vk_api.py) обновляет `vk_raw_data.enc.json`

`vk_raw_data.enc.json` зашифрован паролем `SITE_PASSWORD`. Скрипт перед новой выгрузкой умеет читать предыдущий зашифрованный кэш, поэтому инкрементальная логика сохраняется.
`vk_discussions.json` в репозиторий не коммитится: workflow получает его заново при каждом запуске и использует только как временный build-артефакт.

### 2. Построение метаданных

[`build_playlist_meta.py`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/build_playlist_meta.py) читает обсуждения и кэш видео, затем обновляет [`playlist_meta.json`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/playlist_meta.json).

### 3. Сборка сайта

[`build_data.py`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/build_data.py) собирает сразу два вывода:

- production: [`site/data.enc.json`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/site/data.enc.json)
- local: `site-local/data.js` и `site-local/data/db.json`

### 4. Открытие сайта

[`site/index.html`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/site/index.html):
- показывает форму ввода пароля
- скачивает `data.enc.json`
- расшифровывает архив в браузере
- запускает интерфейс только после успешной расшифровки

GitHub Pages в этой схеме нужен только как хостинг статики.

### 5. Локальная проверка интерфейса

[`site-local/index.html`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/site-local/index.html):
- работает без пароля
- грузит `data.js` напрямую
- нужен только для локального тестирования

## Локальный запуск

Создай локальный `config.json` по примеру [`config.example.json`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/config.example.json):

```json
{
  "vk_token": "vk1.a.xxx",
  "owner_id": -123456789,
  "community": "club123456789"
}
```

Установи зависимости:

```bash
python3 -m pip install requests cryptography
```

Задай пароль для шифрования:

```bash
export SITE_PASSWORD='your-shared-password'
```

Потом запусти:

```bash
python3 scrape_vk_discussions.py
python3 scrape_vk_api.py
python3 build_playlist_meta.py
python3 build_data.py
```

Чтобы проверить production-вариант локально:

```bash
cd site
python3 -m http.server 8123
```

Откроется страница ввода пароля. Используй тот же `SITE_PASSWORD`, который был задан на этапе сборки.

Чтобы проверить локальный plaintext-вариант:

```bash
cd site-local
python3 -m http.server 8124
```

Этот вариант использует `site-local/data.js` и не требует ввода пароля.

## GitHub Actions

Workflow [`.github/workflows/update-site.yml`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/.github/workflows/update-site.yml) делает всё автоматически:

1. тянет новые данные из VK
2. обновляет `playlist_meta.json`
3. пересобирает `site/data.enc.json`
4. параллельно создаёт локальные plaintext-файлы в `site-local/` для разработки
5. коммитит обратно только `playlist_meta.json`, `vk_raw_data.enc.json` и `site/data.enc.json`
6. деплоит папку `site/` в GitHub Pages

### Нужные GitHub Secrets

В `Settings -> Secrets and variables -> Actions`:

- `VK_TOKEN`
- `VK_OWNER_ID`
- `VK_COMMUNITY` — опционально
- `SITE_PASSWORD`

`SITE_PASSWORD` используется сразу в двух местах:
- для шифрования `vk_raw_data.enc.json`
- для шифрования `site/data.enc.json`

## Модель безопасности

Что закрыто:
- данные о видео не лежат в репозитории в открытом виде
- без пароля `data.enc.json` и `vk_raw_data.enc.json` бесполезны

Что не закрыто:
- любой, кто знает пароль, сможет расшифровать архив
- шифротекст доступен всем, если репозиторий или сайт публичны

Поэтому пароль должен быть длинным и неочевидным. Эта схема подходит для "каталог доступен своим, код можно хранить на GitHub", но не для жёсткого DRM.

## Замечания

- [`vk_raw_data.enc.json`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/vk_raw_data.enc.json) обновляется только если реальные данные поменялись.
- [`site/data.enc.json`](/home/coffecat46/Desktop/Folder/vezaksWebsite%20(gemini)/site/data.enc.json) тоже не перешифровывается без необходимости, чтобы workflow не коммитил шум.
- `site-local/` в GitHub Pages не деплоится и нужен только тебе для локальной проверки.
