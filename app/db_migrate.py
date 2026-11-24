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
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS ix_users_last_active_at ON users(last_active_at)",
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
    security_settings_sql = """
    CREATE TABLE IF NOT EXISTS security_settings (
      id SERIAL PRIMARY KEY,
      max_failed_logins INTEGER DEFAULT 6,
      lockout_minutes INTEGER DEFAULT 30,
      session_timeout_minutes INTEGER DEFAULT 480,
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    project_documents_sql = """
    CREATE TABLE IF NOT EXISTS project_documents (
      id SERIAL PRIMARY KEY,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      kind VARCHAR(20) DEFAULT 'file',
      original_name VARCHAR(255) NOT NULL,
      stored_name VARCHAR(255),
      external_url VARCHAR(2000),
      content_type VARCHAR(120) DEFAULT 'application/octet-stream',
      size_bytes INTEGER DEFAULT 0,
      uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_project_documents_project_id ON project_documents(project_id);
    ALTER TABLE project_documents ADD COLUMN IF NOT EXISTS kind VARCHAR(20) DEFAULT 'file';
    ALTER TABLE project_documents ADD COLUMN IF NOT EXISTS external_url VARCHAR(2000);
    ALTER TABLE project_documents ALTER COLUMN stored_name DROP NOT NULL;
    UPDATE project_documents SET kind = 'file' WHERE kind IS NULL OR kind = '';
    """
    tickets_sql = """
    DO $$ BEGIN
      CREATE TYPE ticket_record_type AS ENUM (
        'ticket_kendala', 'catatan_evaluasi', 'meeting_notes'
      );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    DO $$ BEGIN
      CREATE TYPE ticket_priority AS ENUM ('low', 'medium', 'high', 'critical');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    DO $$ BEGIN
      CREATE TYPE ticket_environment AS ENUM (
        'development', 'sit', 'uat', 'production', 'other'
      );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    DO $$ BEGIN
      CREATE TYPE ticket_status AS ENUM ('open', 'in_progress', 'done', 'closed');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    CREATE TABLE IF NOT EXISTS tickets (
      id SERIAL PRIMARY KEY,
      ticket_number VARCHAR(40),
      record_type ticket_record_type DEFAULT 'ticket_kendala',
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      module_name VARCHAR(200) DEFAULT '',
      title VARCHAR(220) NOT NULL,
      description TEXT,
      priority ticket_priority DEFAULT 'medium',
      environment ticket_environment DEFAULT 'development',
      follow_up_target DATE,
      status ticket_status DEFAULT 'open',
      created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ticket_number VARCHAR(40);
    UPDATE tickets
      SET ticket_number = 'TKT-' || TO_CHAR(COALESCE(created_at, NOW()), 'YYYY') || '-' || LPAD(id::text, 5, '0')
      WHERE ticket_number IS NULL OR ticket_number = '';
    CREATE UNIQUE INDEX IF NOT EXISTS uq_tickets_ticket_number ON tickets(ticket_number);
    CREATE INDEX IF NOT EXISTS ix_tickets_ticket_number ON tickets(ticket_number);
    CREATE INDEX IF NOT EXISTS ix_tickets_project_id ON tickets(project_id);
    CREATE INDEX IF NOT EXISTS ix_tickets_record_type ON tickets(record_type);
    CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status);

    CREATE TABLE IF NOT EXISTS ticket_pics (
      id SERIAL PRIMARY KEY,
      ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      CONSTRAINT uq_ticket_pics_ticket_user UNIQUE (ticket_id, user_id)
    );
    CREATE INDEX IF NOT EXISTS ix_ticket_pics_ticket_id ON ticket_pics(ticket_id);
    CREATE INDEX IF NOT EXISTS ix_ticket_pics_user_id ON ticket_pics(user_id);

    CREATE TABLE IF NOT EXISTS ticket_attachments (
      id SERIAL PRIMARY KEY,
      ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
      original_name VARCHAR(255) NOT NULL,
      stored_name VARCHAR(255) NOT NULL,
      content_type VARCHAR(120) DEFAULT 'application/octet-stream',
      size_bytes INTEGER DEFAULT 0,
      uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_ticket_attachments_ticket_id ON ticket_attachments(ticket_id);
    """
    organization_sql = """
    CREATE TABLE IF NOT EXISTS divisions (
      id SERIAL PRIMARY KEY,
      code VARCHAR(40) NOT NULL UNIQUE,
      name VARCHAR(160) NOT NULL,
      description VARCHAR(500) DEFAULT '',
      is_active BOOLEAN DEFAULT TRUE,
      leader_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_divisions_leader_user_id ON divisions(leader_user_id);
    CREATE INDEX IF NOT EXISTS ix_divisions_is_active ON divisions(is_active);

    CREATE TABLE IF NOT EXISTS bidangs (
      id SERIAL PRIMARY KEY,
      division_id INTEGER NOT NULL REFERENCES divisions(id) ON DELETE RESTRICT,
      code VARCHAR(40) NOT NULL,
      name VARCHAR(160) NOT NULL,
      description VARCHAR(500) DEFAULT '',
      is_active BOOLEAN DEFAULT TRUE,
      leader_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW(),
      CONSTRAINT uq_bidangs_division_code UNIQUE (division_id, code)
    );
    CREATE INDEX IF NOT EXISTS ix_bidangs_division_id ON bidangs(division_id);
    CREATE INDEX IF NOT EXISTS ix_bidangs_leader_user_id ON bidangs(leader_user_id);
    CREATE INDEX IF NOT EXISTS ix_bidangs_is_active ON bidangs(is_active);
    """
    # Phase 2 — primary Bidang placement on users + immutable placement history.
    # Division is derived from bidangs.division_id (single source of truth).
    # Leadership (leader_user_id) remains independent of placement.
    user_placement_sql = """
    ALTER TABLE users ADD COLUMN IF NOT EXISTS primary_bidang_id INTEGER;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS placement_version INTEGER DEFAULT 0;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS placement_updated_at TIMESTAMPTZ;
    UPDATE users SET placement_version = 0 WHERE placement_version IS NULL;
    DO $$ BEGIN
      ALTER TABLE users
        ADD CONSTRAINT fk_users_primary_bidang
        FOREIGN KEY (primary_bidang_id) REFERENCES bidangs(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    CREATE INDEX IF NOT EXISTS ix_users_primary_bidang_id ON users(primary_bidang_id);

    CREATE TABLE IF NOT EXISTS user_placement_history (
      id SERIAL PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      action VARCHAR(40) NOT NULL,
      from_bidang_id INTEGER REFERENCES bidangs(id) ON DELETE SET NULL,
      to_bidang_id INTEGER REFERENCES bidangs(id) ON DELETE SET NULL,
      from_division_id INTEGER REFERENCES divisions(id) ON DELETE SET NULL,
      to_division_id INTEGER REFERENCES divisions(id) ON DELETE SET NULL,
      from_bidang_code VARCHAR(40) DEFAULT '',
      from_bidang_name VARCHAR(160) DEFAULT '',
      from_division_code VARCHAR(40) DEFAULT '',
      from_division_name VARCHAR(160) DEFAULT '',
      to_bidang_code VARCHAR(40) DEFAULT '',
      to_bidang_name VARCHAR(160) DEFAULT '',
      to_division_code VARCHAR(40) DEFAULT '',
      to_division_name VARCHAR(160) DEFAULT '',
      reason VARCHAR(500) DEFAULT '',
      actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      placement_version INTEGER DEFAULT 0,
      leadership_conflict_acknowledged BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_user_placement_history_user_id ON user_placement_history(user_id);
    CREATE INDEX IF NOT EXISTS ix_user_placement_history_action ON user_placement_history(action);
    CREATE INDEX IF NOT EXISTS ix_user_placement_history_created_at ON user_placement_history(created_at);
    CREATE INDEX IF NOT EXISTS ix_user_placement_history_actor_user_id ON user_placement_history(actor_user_id);
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
        conn.execute(text(security_settings_sql))
        conn.execute(text(project_documents_sql))
        conn.execute(text(tickets_sql))
        conn.execute(text(organization_sql))
        conn.execute(text(user_placement_sql))
        # Phase 4 — Project organizational ownership (additive; legacy rows remain unassigned).
        conn.execute(
            text(
                """
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_type VARCHAR(20) DEFAULT 'unassigned';
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_division_id INTEGER;
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_bidang_id INTEGER;
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS ownership_classified_at TIMESTAMPTZ;
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS ownership_classified_by_id INTEGER;
    UPDATE projects SET owner_type = 'unassigned' WHERE owner_type IS NULL OR owner_type = '';
    DO $$ BEGIN
      ALTER TABLE projects
        ADD CONSTRAINT fk_projects_owner_division
        FOREIGN KEY (owner_division_id) REFERENCES divisions(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    DO $$ BEGIN
      ALTER TABLE projects
        ADD CONSTRAINT fk_projects_owner_bidang
        FOREIGN KEY (owner_bidang_id) REFERENCES bidangs(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    DO $$ BEGIN
      ALTER TABLE projects
        ADD CONSTRAINT fk_projects_ownership_classified_by
        FOREIGN KEY (ownership_classified_by_id) REFERENCES users(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    CREATE INDEX IF NOT EXISTS ix_projects_owner_type ON projects(owner_type);
    CREATE INDEX IF NOT EXISTS ix_projects_owner_division_id ON projects(owner_division_id);
    CREATE INDEX IF NOT EXISTS ix_projects_owner_bidang_id ON projects(owner_bidang_id);
                """
            )
        )
        conn.execute(
            text(
                """
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS developed_by VARCHAR(40);
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS budget BIGINT;
    CREATE INDEX IF NOT EXISTS ix_projects_developed_by ON projects(developed_by);
                """
            )
        )
        conn.execute(
            text(
                """
    CREATE TABLE IF NOT EXISTS project_discussion_messages (
      id SERIAL PRIMARY KEY,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      body TEXT DEFAULT '',
      parent_id INTEGER REFERENCES project_discussion_messages(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW(),
      deleted_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS ix_project_discussion_messages_project_id
      ON project_discussion_messages(project_id);
    CREATE INDEX IF NOT EXISTS ix_project_discussion_messages_author_id
      ON project_discussion_messages(author_id);
    CREATE INDEX IF NOT EXISTS ix_project_discussion_messages_parent_id
      ON project_discussion_messages(parent_id);
    CREATE INDEX IF NOT EXISTS ix_project_discussion_messages_created_at
      ON project_discussion_messages(created_at);

    CREATE TABLE IF NOT EXISTS project_discussion_attachments (
      id SERIAL PRIMARY KEY,
      message_id INTEGER NOT NULL REFERENCES project_discussion_messages(id) ON DELETE CASCADE,
      kind VARCHAR(20) DEFAULT 'file',
      original_name VARCHAR(255) NOT NULL,
      stored_name VARCHAR(255) NOT NULL,
      content_type VARCHAR(120) DEFAULT 'application/octet-stream',
      size_bytes INTEGER DEFAULT 0,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_project_discussion_attachments_message_id
      ON project_discussion_attachments(message_id);

    CREATE TABLE IF NOT EXISTS project_discussion_reactions (
      id SERIAL PRIMARY KEY,
      message_id INTEGER NOT NULL REFERENCES project_discussion_messages(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      emoji VARCHAR(16) NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      CONSTRAINT uq_discussion_reaction UNIQUE (message_id, user_id, emoji)
    );
    CREATE INDEX IF NOT EXISTS ix_project_discussion_reactions_message_id
      ON project_discussion_reactions(message_id);
    CREATE INDEX IF NOT EXISTS ix_project_discussion_reactions_user_id
      ON project_discussion_reactions(user_id);

    CREATE TABLE IF NOT EXISTS project_discussion_mentions (
      id SERIAL PRIMARY KEY,
      message_id INTEGER NOT NULL REFERENCES project_discussion_messages(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      read_at TIMESTAMPTZ,
      CONSTRAINT uq_discussion_mention UNIQUE (message_id, user_id)
    );
    CREATE INDEX IF NOT EXISTS ix_project_discussion_mentions_message_id
      ON project_discussion_mentions(message_id);
    CREATE INDEX IF NOT EXISTS ix_project_discussion_mentions_user_id
      ON project_discussion_mentions(user_id);
    ALTER TABLE project_discussion_mentions
      ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
    ALTER TABLE project_discussion_mentions
      ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;
    CREATE INDEX IF NOT EXISTS ix_project_discussion_mentions_created_at
      ON project_discussion_mentions(created_at);
    CREATE INDEX IF NOT EXISTS ix_project_discussion_mentions_read_at
      ON project_discussion_mentions(read_at);
                """
            )
        )
