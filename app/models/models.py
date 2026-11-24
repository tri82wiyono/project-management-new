from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    done = "done"


class ProjectStatus(str, enum.Enum):
    backlog = "backlog"
    dev = "dev"
    sit = "sit"
    uat = "uat"
    to = "to"
    izin = "izin"
    release = "release"


class SmtpSetting(Base):
    __tablename__ = "smtp_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # zimbra | gmail — masing-masing disimpan terpisah, tidak saling menimpa
    provider: Mapped[str] = mapped_column(String(40), unique=True, default="zimbra")
    label: Mapped[str] = mapped_column(String(80), default="Zimbra")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    host: Mapped[str] = mapped_column(String(180), default="mail.banksumut.co.id")
    port: Mapped[int] = mapped_column(Integer, default=587)
    encryption: Mapped[str] = mapped_column(String(20), default="starttls")  # none|starttls|ssl
    username: Mapped[str] = mapped_column(String(180), default="notification@banksumut.co.id")
    password: Mapped[str] = mapped_column(String(255), default="")
    from_email: Mapped[str] = mapped_column(String(180), default="notification@banksumut.co.id")
    from_name: Mapped[str] = mapped_column(String(120), default="Project Management System")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AppIdentity(Base):
    __tablename__ = "app_identity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(160), default="Project Management System")
    brand_name: Mapped[str] = mapped_column(String(80), default="PulseDesk")
    brand_mark: Mapped[str] = mapped_column(String(8), default="PM")
    brand_tagline: Mapped[str] = mapped_column(String(120), default="Project OS")
    workspace_label: Mapped[str] = mapped_column(String(80), default="Workspace")
    workspace_name: Mapped[str] = mapped_column(String(120), default="Fintech Delivery")
    organization_name: Mapped[str] = mapped_column(String(160), default="Bank Sumut")
    app_url: Mapped[str] = mapped_column(String(255), default="http://localhost:8891")
    footer_note: Mapped[str] = mapped_column(String(255), default="Built with FastAPI · PostgreSQL")
    support_email: Mapped[str] = mapped_column(String(180), default="notification@banksumut.co.id")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class SecuritySetting(Base):
    """Singleton security policy (lockout + session timeout) editable by admin."""

    __tablename__ = "security_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    max_failed_logins: Mapped[int] = mapped_column(Integer, default=6)
    lockout_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # Absolute session lifetime from login; client + AuthGuard enforce logout
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=480)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Division(Base):
    """Organizational Division (unit). Leadership is metadata only — not an RBAC role."""

    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    leader_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    leader: Mapped["User | None"] = relationship("User", foreign_keys=[leader_user_id])
    bidangs: Mapped[list["Bidang"]] = relationship(
        "Bidang",
        back_populates="division",
        cascade="all, delete-orphan",
        order_by="Bidang.name",
    )


class Bidang(Base):
    """Organizational Bidang under a Division. Codes are unique within a Division."""

    __tablename__ = "bidangs"
    __table_args__ = (UniqueConstraint("division_id", "code", name="uq_bidangs_division_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    division_id: Mapped[int] = mapped_column(
        ForeignKey("divisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    leader_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    division: Mapped[Division] = relationship("Division", back_populates="bidangs")
    leader: Mapped["User | None"] = relationship("User", foreign_keys=[leader_user_id])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(80), default="Member")  # stores Role.code
    avatar_url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_backup_codes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Phase 2 — primary org placement (Division derived from Bidang.parent). Leadership ≠ placement.
    primary_bidang_id: Mapped[int | None] = mapped_column(
        ForeignKey("bidangs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    placement_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    placement_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tasks: Mapped[list[Task]] = relationship(back_populates="assignee")
    task_links: Mapped[list["TaskAssignee"]] = relationship(back_populates="user")
    memberships: Mapped[list[TeamMember]] = relationship(back_populates="user")
    devices: Mapped[list["UserDevice"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    primary_bidang: Mapped["Bidang | None"] = relationship(
        "Bidang",
        foreign_keys=[primary_bidang_id],
    )
    placement_history: Mapped[list["UserPlacementHistory"]] = relationship(
        "UserPlacementHistory",
        back_populates="user",
        foreign_keys="UserPlacementHistory.user_id",
        cascade="all, delete-orphan",
        order_by="desc(UserPlacementHistory.created_at)",
    )


class UserPlacementHistory(Base):
    """Immutable history of organizational placement changes. Does not grant RBAC permissions."""

    __tablename__ = "user_placement_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # assign|transfer|clear
    from_bidang_id: Mapped[int | None] = mapped_column(
        ForeignKey("bidangs.id", ondelete="SET NULL"), nullable=True
    )
    to_bidang_id: Mapped[int | None] = mapped_column(
        ForeignKey("bidangs.id", ondelete="SET NULL"), nullable=True
    )
    from_division_id: Mapped[int | None] = mapped_column(
        ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True
    )
    to_division_id: Mapped[int | None] = mapped_column(
        ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshots so history remains readable if units are later renamed.
    from_bidang_code: Mapped[str] = mapped_column(String(40), default="")
    from_bidang_name: Mapped[str] = mapped_column(String(160), default="")
    from_division_code: Mapped[str] = mapped_column(String(40), default="")
    from_division_name: Mapped[str] = mapped_column(String(160), default="")
    to_bidang_code: Mapped[str] = mapped_column(String(40), default="")
    to_bidang_name: Mapped[str] = mapped_column(String(160), default="")
    to_division_code: Mapped[str] = mapped_column(String(40), default="")
    to_division_name: Mapped[str] = mapped_column(String(160), default="")
    reason: Mapped[str] = mapped_column(String(500), default="")
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    placement_version: Mapped[int] = mapped_column(Integer, default=0)
    leadership_conflict_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped[User] = relationship(
        "User",
        back_populates="placement_history",
        foreign_keys=[user_id],
    )
    actor: Mapped[User | None] = relationship("User", foreign_keys=[actor_user_id])


class UserDevice(Base):
    __tablename__ = "user_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_label: Mapped[str] = mapped_column(String(160), default="Browser")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    browser_name: Mapped[str] = mapped_column(String(80), default="")
    os_name: Mapped[str] = mapped_column(String(80), default="")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    confirm_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confirm_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trusted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="devices")


class ProjectOwnerType(str, enum.Enum):
    """Organizational ownership for a Project. unassigned = legacy/unclassified."""

    unassigned = "unassigned"
    division = "division"
    bidang = "bidang"


class ProjectDevelopedBy(str, enum.Enum):
    """Who develops the application."""

    internal = "internal"
    vendor = "vendor"
    blanket_mandays = "blanket_mandays"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    pic: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"),
        default=ProjectStatus.backlog,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    color: Mapped[str] = mapped_column(String(20), default="#4F7CFF")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    developed_by: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    budget: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Phase 4 — organizational ownership (Division XOR Bidang; unassigned for legacy).
    owner_type: Mapped[str] = mapped_column(String(20), default=ProjectOwnerType.unassigned.value, index=True)
    owner_division_id: Mapped[int | None] = mapped_column(
        ForeignKey("divisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_bidang_id: Mapped[int | None] = mapped_column(
        ForeignKey("bidangs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ownership_classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ownership_classified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")
    members: Mapped[list[TeamMember]] = relationship(back_populates="project", cascade="all, delete-orphan")
    documents: Mapped[list["ProjectDocument"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectDocument.created_at",
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="desc(Ticket.created_at)",
    )
    owner_division: Mapped["Division | None"] = relationship("Division", foreign_keys=[owner_division_id])
    owner_bidang: Mapped["Bidang | None"] = relationship("Bidang", foreign_keys=[owner_bidang_id])
    discussion_messages: Mapped[list["ProjectDiscussionMessage"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectDiscussionMessage.created_at",
    )


class ProjectDocument(Base):
    __tablename__ = "project_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # file = uploaded binary; url = Google Drive / OneDrive / shared link, etc.
    kind: Mapped[str] = mapped_column(String(20), default="file")
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="documents")
    uploaded_by: Mapped[User | None] = relationship()


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(80), default="Member")

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60), default="General")
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        default=TaskStatus.todo,
    )
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="tasks")
    assignee: Mapped[User | None] = relationship(back_populates="tasks")
    assignees: Mapped[list["TaskAssignee"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["TaskNote"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="desc(TaskNote.created_at)",
    )


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_assignees_task_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    task: Mapped[Task] = relationship(back_populates="assignees")
    user: Mapped[User] = relationship(back_populates="task_links")


class TaskNote(Base):
    __tablename__ = "task_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="problem")  # problem | note
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="notes")
    author: Mapped[User | None] = relationship()


class TicketRecordType(str, enum.Enum):
    ticket_kendala = "ticket_kendala"
    catatan_evaluasi = "catatan_evaluasi"
    meeting_notes = "meeting_notes"


class TicketPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TicketEnvironment(str, enum.Enum):
    development = "development"
    sit = "sit"
    uat = "uat"
    production = "production"
    other = "other"


class TicketStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    closed = "closed"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_number: Mapped[str | None] = mapped_column(String(40), unique=True, index=True, nullable=True)
    record_type: Mapped[TicketRecordType] = mapped_column(
        Enum(TicketRecordType, name="ticket_record_type"),
        default=TicketRecordType.ticket_kendala,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    module_name: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority, name="ticket_priority"),
        default=TicketPriority.medium,
    )
    environment: Mapped[TicketEnvironment] = mapped_column(
        Enum(TicketEnvironment, name="ticket_environment"),
        default=TicketEnvironment.development,
    )
    follow_up_target: Mapped[date | None] = mapped_column(Date)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"),
        default=TicketStatus.open,
        index=True,
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="tickets")
    created_by: Mapped[User | None] = relationship()
    pics: Mapped[list["TicketPic"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    attachments: Mapped[list["TicketAttachment"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketAttachment.created_at",
    )


class TicketPic(Base):
    __tablename__ = "ticket_pics"
    __table_args__ = (UniqueConstraint("ticket_id", "user_id", name="uq_ticket_pics_ticket_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    ticket: Mapped[Ticket] = relationship(back_populates="pics")
    user: Mapped[User] = relationship()


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="attachments")
    uploaded_by: Mapped[User | None] = relationship()


class ProjectDiscussionMessage(Base):
    """Collaborative discussion thread for a project workspace."""

    __tablename__ = "project_discussion_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_discussion_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="discussion_messages")
    author: Mapped[User] = relationship("User", foreign_keys=[author_id])
    parent: Mapped["ProjectDiscussionMessage | None"] = relationship(
        "ProjectDiscussionMessage",
        remote_side="ProjectDiscussionMessage.id",
        foreign_keys=[parent_id],
    )
    attachments: Mapped[list["ProjectDiscussionAttachment"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )
    reactions: Mapped[list["ProjectDiscussionReaction"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )
    mentions: Mapped[list["ProjectDiscussionMention"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class ProjectDiscussionAttachment(Base):
    __tablename__ = "project_discussion_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("project_discussion_messages.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), default="file")  # image | file
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped[ProjectDiscussionMessage] = relationship(back_populates="attachments")


class ProjectDiscussionReaction(Base):
    __tablename__ = "project_discussion_reactions"
    __table_args__ = (UniqueConstraint("message_id", "user_id", "emoji", name="uq_discussion_reaction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("project_discussion_messages.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped[ProjectDiscussionMessage] = relationship(back_populates="reactions")
    user: Mapped[User] = relationship("User")


class ProjectDiscussionMention(Base):
    __tablename__ = "project_discussion_mentions"
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_discussion_mention"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("project_discussion_messages.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    message: Mapped[ProjectDiscussionMessage] = relationship(back_populates="mentions")
    user: Mapped[User] = relationship("User")


class AuditLog(Base):
    """Login & email password events for admin review."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # login_success | login_failed | password_email_sent | password_email_failed
    # welcome_email_sent | welcome_email_failed
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    actor_email: Mapped[str] = mapped_column(String(180), default="")
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_name: Mapped[str] = mapped_column(String(120), default="")
    target_email: Mapped[str] = mapped_column(String(180), default="", index=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
