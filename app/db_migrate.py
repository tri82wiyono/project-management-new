from sqlalchemy import text

from app.database import engine


def ensure_schema() -> None:
    """Lightweight schema patches for local development containers."""
    statements = [
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS pic VARCHAR(500) DEFAULT ''",
        "ALTER TABLE projects ALTER COLUMN pic TYPE VARCHAR(500)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_backup_codes JSONB",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ",
        """
        UPDATE projects SET pic = 'Farah Nabila'
        WHERE (pic IS NULL OR pic = '') AND name = 'Payment Platform'
        """,
        """
        UPDATE projects SET pic = 'Maya Anggraini'
        WHERE (pic IS NULL OR pic = '') AND name = 'Client Portal'
        """,
        """
        UPDATE projects SET pic = 'Hana Salsabila'
        WHERE (pic IS NULL OR pic = '') AND name = 'Compliance Upgrade'
        """,
        """
        UPDATE projects SET pic = 'Luthfi Hakim'
        WHERE (pic IS NULL OR pic = '') AND name = 'Mobile Banking App'
        """,
        """
        UPDATE projects SET pic = 'Project Manager'
        WHERE pic IS NULL OR pic = ''
        """,
    ]
    migrate_status_sql = """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'project_status' AND e.enumlabel = 'planning'
      ) THEN
        ALTER TABLE projects ALTER COLUMN status DROP DEFAULT;
        ALTER TABLE projects
          ALTER COLUMN status TYPE VARCHAR(40) USING status::text;
        UPDATE projects SET status = CASE status
          WHEN 'planning' THEN 'backlog'
          WHEN 'active' THEN 'dev'
          WHEN 'on_hold' THEN 'sit'
          WHEN 'completed' THEN 'release'
          ELSE status
        END;
        DROP TYPE project_status;
        CREATE TYPE project_status AS ENUM (
          'backlog', 'dev', 'sit', 'uat', 'to', 'izin', 'release'
        );
        ALTER TABLE projects
          ALTER COLUMN status TYPE project_status
          USING status::project_status;
        ALTER TABLE projects
          ALTER COLUMN status SET DEFAULT 'backlog'::project_status;
      END IF;
    END $$;
    """
    task_assignees_sql = """
    CREATE TABLE IF NOT EXISTS task_assignees (
      id SERIAL PRIMARY KEY,
      task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      CONSTRAINT uq_task_assignees_task_user UNIQUE (task_id, user_id)
    );
    """
    migrate_task_assignees_sql = """
    INSERT INTO task_assignees (task_id, user_id)
    SELECT t.id, t.assignee_id
    FROM tasks t
    WHERE t.assignee_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM task_assignees ta
        WHERE ta.task_id = t.id AND ta.user_id = t.assignee_id
      );
    """
    # Keep legacy assignee_id aligned with first multi-assignee row when missing.
    sync_primary_assignee_sql = """
    UPDATE tasks t
    SET assignee_id = sub.user_id
    FROM (
      SELECT DISTINCT ON (task_id) task_id, user_id
      FROM task_assignees
      ORDER BY task_id, id ASC
    ) AS sub
    WHERE t.id = sub.task_id
      AND t.assignee_id IS NULL;
    """
    user_devices_sql = """
    CREATE TABLE IF NOT EXISTS user_devices (
      id SERIAL PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      device_token_hash VARCHAR(64) NOT NULL UNIQUE,
      device_label VARCHAR(160) DEFAULT 'Browser',
      user_agent VARCHAR(500) DEFAULT '',
      browser_name VARCHAR(80) DEFAULT '',
      os_name VARCHAR(80) DEFAULT '',
      ip_address VARCHAR(64),
      is_trusted BOOLEAN DEFAULT FALSE,
      confirm_token_hash VARCHAR(64),
      confirm_expires_at TIMESTAMPTZ,
      last_seen_at TIMESTAMPTZ,
      trusted_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_user_devices_user_id ON user_devices(user_id);
    CREATE INDEX IF NOT EXISTS ix_user_devices_confirm_token_hash ON user_devices(confirm_token_hash);
    """
    task_notes_sql = """
    CREATE TABLE IF NOT EXISTS task_notes (
      id SERIAL PRIMARY KEY,
      task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
      body TEXT NOT NULL,
      kind VARCHAR(20) DEFAULT 'problem',
      author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_task_notes_task_id ON task_notes(task_id);
    """
    smtp_profiles_sql = """
    ALTER TABLE smtp_settings ADD COLUMN IF NOT EXISTS provider VARCHAR(40) DEFAULT 'zimbra';
    ALTER TABLE smtp_settings ADD COLUMN IF NOT EXISTS label VARCHAR(80) DEFAULT 'Zimbra';
    ALTER TABLE smtp_settings ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE;
    UPDATE smtp_settings
    SET provider = CASE
          WHEN lower(coalesce(host, '')) LIKE '%gmail%' THEN 'gmail'
          ELSE 'zimbra'
        END,
        label = CASE
          WHEN lower(coalesce(host, '')) LIKE '%gmail%' THEN 'Gmail'
          ELSE 'Zimbra'
        END
    WHERE provider IS NULL OR provider = '';
    UPDATE smtp_settings SET is_active = TRUE
    WHERE id = (SELECT id FROM smtp_settings ORDER BY id ASC LIMIT 1)
      AND NOT EXISTS (SELECT 1 FROM smtp_settings WHERE is_active = TRUE);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_smtp_settings_provider ON smtp_settings (provider);
    """
    audit_logs_sql = """
    CREATE TABLE IF NOT EXISTS audit_logs (
      id SERIAL PRIMARY KEY,
      action VARCHAR(60) NOT NULL,
      success BOOLEAN DEFAULT TRUE,
      actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      actor_name VARCHAR(120) DEFAULT '',
      actor_email VARCHAR(180) DEFAULT '',
      target_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      target_name VARCHAR(120) DEFAULT '',
      target_email VARCHAR(180) DEFAULT '',
      message VARCHAR(500) DEFAULT '',
      ip_address VARCHAR(64),
      user_agent VARCHAR(500) DEFAULT '',
      meta JSONB,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs(action);
    CREATE INDEX IF NOT EXISTS ix_audit_logs_success ON audit_logs(success);
    CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at);
    CREATE INDEX IF NOT EXISTS ix_audit_logs_target_email ON audit_logs(target_email);
    CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_user_id ON audit_logs(actor_user_id);
    CREATE INDEX IF NOT EXISTS ix_audit_logs_target_user_id ON audit_logs(target_user_id);
    """
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.execute(text(migrate_status_sql))
        conn.execute(text(task_assignees_sql))
        conn.execute(text(migrate_task_assignees_sql))
        conn.execute(text(sync_primary_assignee_sql))
        conn.execute(text(user_devices_sql))
        conn.execute(text(task_notes_sql))
        conn.execute(text(smtp_profiles_sql))
        conn.execute(text(audit_logs_sql))
