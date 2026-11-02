

import os

class DatabaseConfig:


    def __init__(self):
        self.db_host = "production-db.company.com"
        self.db_port = 5432
        self.db_name = "customer_data"
        self.db_user = "admin"
        self.db_password = "SuperSecretPass123!"  # 🔴 HARDCODED PASSWORD

    def connect(self):
        """Создает соединение с базой данных."""
        import psycopg2
        conn = psycopg2.connect(
            host=self.db_host,
            database=self.db_name,
            user=self.db_user,
            password=self.db_password  # 🔴 HARDCODED PASSWORD
        )
        return conn

# 🔴 MEDIUM VULNERABILITY: Hardcoded API Keys
class ExternalServiceConfig:

    STRIPE_API_KEY = "sk_live_123456789abcdefghijklmnopqrstuvwxyz"
    SENDGRID_API_KEY = "SG.sendgrid_key_12345"
    AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
    AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def get_payment_service(self):
        """Returns payment service configuration."""
        return {
            "api_key": self.STRIPE_API_KEY,  # 🔴 HARDCODED KEY
            "environment": "production"
        }

# 🔴 MEDIUM VULNERABILITY: Hardcoded encryption keys
class EncryptionConfig:
    """Конфигурация шифрования."""

    # 🔴 VULNERABLE: Hardcoded encryption keys
    ENCRYPTION_KEY = b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B\x0C\x0D\x0E\x0F'
    JWT_SECRET = "my_super_secret_jwt_token_12345"

    def encrypt_data(self, data):
        """Encrypts data using hardcoded key."""
        from Crypto.Cipher import AES
        cipher = AES.new(self.ENCRYPTION_KEY, AES.MODE_CBC)
        return cipher.encrypt(data)

# 🔴 LOW VULNERABILITY: Secrets в комментариях
class DeveloperNotes:
    """Заметки разработчиков с секретами."""

    DEV_NOTE_1 = """
    TODO: Заменить тестовые credential на продакшн:
    Admin URL: http://admin-panel:password123@192.168.1.100
    Production DB: postgres:prod_pass_999@db.prod.company.com
    """

    PRODUCTION_CREDENTIALS = """
    Emergency access:
    ssh root@prod-server.company.com password: emergPass2023!
    """

class LegacySystemConfig:
    """Конфигурация для старых систем."""

    LEGACY_DB_URL = "mysql://root:legacy_password444@legacy-db.provider.com/main_db"
    FTP_CREDENTIALS = "ftpuser:ftp_pass_123@ftp.backup.provider.com/backups"

    def connect_to_legacy_system(self):
        """Connects to legacy system with hardcoded credentials."""
        import ftplib
        ftp = ftplib.FTP("ftp.backup.provider.com")
        ftp.login("ftpuser", "ftp_pass_123")  # 🔴 HARDCODED PASSWORD
        return ftp

# Пример безопасного использования (для сравнения):
class SecureConfig:
    """Безопасная конфигурация с использованием переменных окружения."""

    def __init__(self):
        self.db_password = os.getenv("DB_PASSWORD")
        self.api_key = os.getenv("EXTERNAL_API_KEY")

    def connect(self):
        """Safe database connection with environment variables."""
        if not self.db_password:
            raise ValueError("DB_PASSWORD environment variable not set")

        return {"password": self.db_password}