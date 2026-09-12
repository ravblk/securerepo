"""
Database Migrations System for SecureRepo
Handles properly versioned database schema migrations with foreign key relationships
"""

import os
from datetime import datetime
import psycopg2
from psycopg2 import sql

POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://securerepo:securerepo_pass@postgres:5432/securerepo")

def get_db_connection():
    """Функция для создания подключения к PostgreSQL."""
    return psycopg2.connect(POSTGRES_URL)

def create_schema_migrations_table():
    """
    Migration 001: Создание таблицы для отслеживания версий миграций
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW(),
                description TEXT
            );
        """)
        conn.commit()
        print("✅ Migration 001: Created schema_migrations table")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 001 failed: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def create_audits_table():
    """
    Migration 002: Создание таблицы audits с правильной структурой
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Сначала проверяем, существует ли таблица
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'audits'
            );
        """)
        table_exists = cursor.fetchone()[0]

        if table_exists:
            # Проверяем наличие foreign key и обновляем структуру если нужно
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE constraint_type = 'PRIMARY KEY'
                AND table_name = 'audits'
            """)
            has_pk = cursor.fetchone()[0] > 0

            if not has_pk:
                cursor.execute("""
                    ALTER TABLE audits ADD PRIMARY KEY (id);
                """)

            # Обновляем NULL user_id перед установкой ограничения NOT NULL
            cursor.execute("""
                UPDATE audits SET user_id = 'migrated-user' WHERE user_id IS NULL OR user_id = '';
            """)

            # Обновляем структуру таблицы для соответствия схеме
            cursor.execute("""
                ALTER TABLE audits
                ALTER COLUMN user_id SET NOT NULL,
                ALTER COLUMN status SET DEFAULT 'pending',
                ALTER COLUMN created_at SET DEFAULT NOW(),
                ALTER COLUMN updated_at SET DEFAULT NOW();
            """)

            print("✅ Migration 002: Updated audits table structure")

            # Создаем индексы если их нет
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audits_status ON audits(status);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audits_created_at ON audits(created_at);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audits_user_id ON audits(user_id);
            """)
        else:
            # Создаем новую таблицу с правильной структурой
            cursor.execute("""
                CREATE TABLE audits (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    repo_url TEXT NOT NULL,
                    branch VARCHAR(255) DEFAULT 'main',
                    lang VARCHAR(50) DEFAULT 'python',
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Создаем индексы
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audits_status ON audits(status);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audits_created_at ON audits(created_at);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audits_user_id ON audits(user_id);
            """)

            print("✅ Migration 002: Created audits table with proper structure")

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 002 failed: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def create_audit_logs_table_with_fk():
    """
    Migration 003: Создание таблицы audit_logs с правильным foreign key
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Удаляем старую таблицу если она существует и создаем новую
        cursor.execute("""
            DROP TABLE IF EXISTS audit_logs CASCADE;
        """)

        cursor.execute("""
            CREATE TABLE audit_logs (
                id SERIAL PRIMARY KEY,
                audit_id VARCHAR(255) NOT NULL,
                action VARCHAR(100) NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (audit_id) REFERENCES audits(id) ON DELETE CASCADE
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_audit_id ON audit_logs(audit_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
        """)

        conn.commit()
        print("✅ Migration 003: Created audit_logs table with proper foreign key")
        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 003 failed: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def create_audit_results_table_with_fk():
    """
    Migration 004: Создание таблицы audit_results с правильным foreign key
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Удаляем старую таблицу если она существует и создаем новую
        cursor.execute("""
            DROP TABLE IF EXISTS audit_results CASCADE;
        """)

        cursor.execute("""
            CREATE TABLE audit_results (
                id SERIAL PRIMARY KEY,
                audit_id VARCHAR(255) NOT NULL,
                chunk_id VARCHAR(255) NOT NULL,
                file_path TEXT NOT NULL,
                findings JSONB NOT NULL,
                severity VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (audit_id) REFERENCES audits(id) ON DELETE CASCADE
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_results_audit_id ON audit_results(audit_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_results_severity ON audit_results(severity);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_results_created_at ON audit_results(created_at);
        """)

        # Создаем составной индекс для оптимизации запросов
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_results_audit_severity
            ON audit_results(audit_id, severity);
        """)

        conn.commit()
        print("✅ Migration 004: Created audit_results table with proper foreign key")
        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 004 failed: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def record_migration(migration_name: str, description: str):
    """Записываем выполненную миграцию"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO schema_migrations (migration_name, description, applied_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (migration_name) DO UPDATE SET
                description = EXCLUDED.description,
                applied_at = NOW();
        """, (migration_name, description))
        conn.commit()
        print(f"✅ Recorded migration: {migration_name}")
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed to record migration {migration_name}: {e}")
    finally:
        cursor.close()
        conn.close()

def rollback_migration(migration_name: str):
    """Удаляем запись о миграции для повторного запуска"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            DELETE FROM schema_migrations WHERE migration_name = %s;
        """, (migration_name,))
        conn.commit()
        print(f"✅ Rolled back migration record: {migration_name}")
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed to rollback migration {migration_name}: {e}")
    finally:
        cursor.close()
        conn.close()

def is_migration_applied(migration_name: str) -> bool:
    """Проверяем, применена ли миграция"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверяем, существует ли таблица schema_migrations
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'schema_migrations'
            );
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            return False

        cursor.execute("""
            SELECT COUNT(*) FROM schema_migrations WHERE migration_name = %s;
        """, (migration_name,))
        count = cursor.fetchone()[0]
        return count > 0
    finally:
        cursor.close()
        conn.close()

def run_migrations():
    """Запуск всех миграций в правильном порядке"""
    print("🚀 Starting database migrations...")
    print(f"📍 Database: {POSTGRES_URL}")

    migrations = [
        {
            "name": "001_create_schema_migrations_table",
            "description": "Create schema_migrations tracking table",
            "func": create_schema_migrations_table
        },
        {
            "name": "002_create_audits_table",
            "description": "Create/update audits table with proper structure",
            "func": create_audits_table
        },
        {
            "name": "003_create_audit_logs_table_with_fk",
            "description": "Create audit_logs table with foreign key to audits",
            "func": create_audit_logs_table_with_fk
        },
        {
            "name": "004_create_audit_results_table_with_fk",
            "description": "Create audit_results table with foreign key to audits",
            "func": create_audit_results_table_with_fk
        }
    ]

    applied_count = 0
    failed_count = 0

    for migration in migrations:
        if is_migration_applied(migration['name']):
            print(f"⏭️  Migration {migration['name']} already applied, skipping...")
            continue

        print(f"🔄 Applying migration: {migration['name']}...")
        if migration["func"]():
            record_migration(migration['name'], migration['description'])
            applied_count += 1
        else:
            failed_count += 1

    print(f"\n📊 Migration Summary:")
    print(f"✅ Applied: {applied_count} migrations")
    print(f"❌ Failed: {failed_count} migrations")
    print(f"⏭️  Skipped: {len(migrations) - applied_count - failed_count} migrations")

    if failed_count > 0:
        print("\n⚠️  Some migrations failed. Please check the errors above.")
        return False
    else:
        print("\n✅ All migrations completed successfully!")
        return True

def verify_relationships():
    """Проверка правильности установленных foreign key связей"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        print("\n🔍 Verifying database relationships...")

        # Проверяем foreign keys для audit_logs
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'audit_logs'
            AND tc.constraint_type = 'FOREIGN KEY'
            AND ccu.table_name = 'audits';
        """)
        audit_logs_fk_count = cursor.fetchone()[0]

        # Проверяем foreign keys для audit_results
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'audit_results'
            AND tc.constraint_type = 'FOREIGN KEY'
            AND ccu.table_name = 'audits';
        """)
        audit_results_fk_count = cursor.fetchone()[0]

        # Проверяем primary key для audits
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name = 'audits' AND constraint_type = 'PRIMARY KEY';
        """)
        audits_pk_count = cursor.fetchone()[0]

        print(f"✅ Audits table has PRIMARY KEY: {'YES' if audits_pk_count > 0 else 'NO'}")
        print(f"✅ Audit_logs → Audits FOREIGN KEY: {'YES' if audit_logs_fk_count > 0 else 'NO'}")
        print(f"✅ Audit_results → Audits FOREIGN KEY: {'YES' if audit_results_fk_count > 0 else 'NO'}")

        # Проверяем индексы
        cursor.execute("""
            SELECT indexname FROM pg_indexes WHERE schemaname = 'public'
            AND tablename IN ('audits', 'audit_logs', 'audit_results')
            ORDER BY tablename, indexname;
        """)
        indexes = cursor.fetchall()

        print(f"\n✅ Total indexes: {len(indexes)}")
        for index in indexes:
            print(f"   • {index[0]}")

        return audit_logs_fk_count > 0 and audit_results_fk_count > 0 and audits_pk_count > 0

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_migrations()
    verify_relationships()
