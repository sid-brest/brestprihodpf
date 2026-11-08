# prihodpfbrest.by

Одностраничный статический сайт прихода храма свв. Петра и Февронии Муромских в Бресте.

## Структура

| Путь | Назначение |
|---|---|
| `index.html` | единственная страница (расписание обновляется скриптом из `schedule/`) |
| `scss/` | исходники стилей → `css/style.min.css` |
| `css/vendor/`, `js/vendor/` | исходники сторонних библиотек → `css/vendor.min.css`, `js/vendor.min.js` |
| `js/custom.js` | собственный JS → `js/custom.min.js` |
| `fonts/` | `Miama Nueva` (OFL, self-hosted subset) и `icomoon` (3 глифа) |
| `schedule/` | локальные скрипты обновления расписания (не деплоятся) |
| `update.sh` | деплой на сервере: `git pull` + rsync только нужных файлов |

## Сборка

```bash
npm install
npm run build        # css + vendor css/js + custom js
npm run watch:css    # пересборка scss при изменениях
```

В браузер попадают только: `index.html`, `robots.txt`, `sitemap.xml`, `css/*.min.css`, `js/*.min.js`, `img/`, `fonts/**/*.woff2`.

## Автор

Dzmitry Struneuski · https://t.me/DmitryStrunewsky · https://www.linkedin.com/in/dzmitry-struneuski
