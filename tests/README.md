# Проверка Recall модели воркера

Скрипт берёт `OAPI_MODELS_URL` и `OAPI_API_KEY` так же, как
`services/audit-worker/audit/config.py`, и вызывает модель `zai-org/GLM-4.7`.
Каждый файл из `services/owasp-seeder/tests/fixtures/vulnerable_code/` уходит
в тот же промпт, что и шаг анализа воркера. Находки сравниваются с эталоном
`tests/fixtures/vulnerable_code_ground_truth.yaml`.

Совпадение — цитата `vulnerable_line` попадает в строку эталона (±2 строки).
Recall = доля записей эталона, которые модель так процитировала. Порог — 50%.

Ключ лежит в `tests/.env`:

```bash
OAPI_API_KEY=...
```

```bash
python tests/test_vulnerability_detection.py
```

Адрес по умолчанию — `https://foundation-models.api.cloud.ru/v1`.
Отчёт пишется в `tests/vulnerability_detection_report.txt` и
`tests/vulnerability_detection_metrics.json`.
