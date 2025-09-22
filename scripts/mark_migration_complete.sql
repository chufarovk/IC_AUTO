-- SQL скрипт для отметки merge-миграции как выполненной
-- Поскольку merge-миграция содержит только pass, мы просто отмечаем её как выполненную

-- Вставляем запись о выполненной миграции в таблицу alembic_version
INSERT INTO alembic_version (version_num)
VALUES ('20250922120000')
ON CONFLICT (version_num) DO NOTHING;

-- Проверяем результат
SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 5;