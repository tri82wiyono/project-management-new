from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import (
    ProjectStatus,
    TaskStatus,
    TicketEnvironment,
    TicketPriority,
    TicketRecordType,
    TicketStatus,
)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    avatar_url: str
    is_active: bool


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    user: UserOut


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    pic: str = Field(default="", max_length=500)
    status: ProjectStatus = ProjectStatus.backlog
    progress: float = Field(default=0, ge=0, le=100)
    color: str = "#4F7CFF"
    start_date: date
    end_date: date
    developed_by: str | None = Field(default=None, max_length=40)
    budget: int | None = Field(default=None, ge=0)
    owner_type: str = "unassigned"
    owner_division_id: int | None = None
    owner_bidang_id: int | None = None


class ProjectCreate(ProjectBase):
    member_ids: list[int] = []


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    pic: str | None = Field(default=None, max_length=500)
    status: ProjectStatus | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    color: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    developed_by: str | None = Field(default=None, max_length=40)
    budget: int | None = Field(default=None, ge=0)
    member_ids: list[int] | None = None
    owner_type: str | None = None
    owner_division_id: int | None = None
    owner_bidang_id: int | None = None


class ProjectOwnershipUpdate(BaseModel):
    owner_type: str = Field(min_length=1, max_length=20)
    owner_division_id: int | None = None
    owner_bidang_id: int | None = None


class ProjectDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    kind: str = "file"  # file | url
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
    external_url: str | None = None
    download_url: str | None = None
    open_url: str | None = None


class ProjectDocumentUrlCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: str | None = Field(default=None, max_length=255)


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    members: list[TeamMemberOut] = []
    task_count: int = 0
    documents: list[ProjectDocumentOut] = []
    owner_division_code: str = ""
    owner_division_name: str = ""
    owner_bidang_code: str = ""
    owner_bidang_name: str = ""
    is_classified: bool = False
    ownership_classified_at: datetime | None = None


class ProjectStats(BaseModel):
    total: int
    in_progress: int
    completed: int
    planning: int


class ProjectListResponse(BaseModel):
    items: list[ProjectOut]
    total: int
    page: int
    page_size: int
    pages: int


class ProjectProgress(BaseModel):
    id: int
    name: str
    progress: float
    status: ProjectStatus
    color: str


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str = "General"
    status: TaskStatus = TaskStatus.todo
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: date | None = None
    project_id: int
    assignee_id: int | None = None
    assignee_ids: list[int] = []


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    status: TaskStatus | None = None
    priority: Literal["low", "medium", "high"] | None = None
    due_date: date | None = None
    project_id: int | None = None
    assignee_id: int | None = None
    assignee_ids: list[int] | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    category: str
    status: TaskStatus
    priority: str
    due_date: date | None
    project_id: int
    assignee_id: int | None
    assignee_ids: list[int] = []
    completed_at: datetime | None
    created_at: datetime
    assignee: UserOut | None = None
    assignees: list[UserOut] = []
    project_name: str | None = None
    project_progress: float | None = None
    notes_count: int = 0
    has_problem: bool = False


class TaskNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    kind: Literal["problem", "note"] = "problem"


class TaskNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    body: str
    kind: str
    author_id: int | None = None
    author_name: str | None = None
    created_at: datetime


class ProjectTaskNoteOut(TaskNoteOut):
    task_title: str
    task_status: TaskStatus | None = None


class KanbanColumn(BaseModel):
    status: TaskStatus
    label: str
    count: int
    tasks: list[TaskOut]


class KanbanBoard(BaseModel):
    columns: list[KanbanColumn]


class TimelineItem(BaseModel):
    id: int
    name: str
    progress: float
    color: str
    start_date: date
    end_date: date
    status: ProjectStatus


class AnalyticsPoint(BaseModel):
    date: date
    completed: int
    created: int


class AnalyticsResponse(BaseModel):
    tasks_completed: int
    tasks_created: int
    completed_growth: float
    created_growth: float
    series: list[AnalyticsPoint]


class DeadlineItem(BaseModel):
    id: int
    title: str
    due_date: date
    status: TaskStatus
    category: str
    project_name: str
    assignee: UserOut | None = None


class OverdueItem(DeadlineItem):
    days_overdue: int = 0


class OverdueAlert(BaseModel):
    count: int
    items: list[OverdueItem] = []


class CalendarDay(BaseModel):
    date: date
    count: int
    deadlines: list[DeadlineItem]


class CalendarResponse(BaseModel):
    year: int
    month: int
    days: list[CalendarDay]
    upcoming: list[DeadlineItem]


class DashboardKPI(BaseModel):
    total_projects: int
    total_projects_growth: float
    completed_tasks: int
    completed_tasks_growth: float
    in_progress: int
    in_progress_growth: float
    on_time_delivery: float
    on_time_delivery_growth: float


class TeamOverview(BaseModel):
    total: int
    visible: list[UserOut]
    extra: int


class TicketAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
    download_url: str | None = None


class TicketBase(BaseModel):
    record_type: TicketRecordType = TicketRecordType.ticket_kendala
    project_id: int
    module_name: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=220)
    description: str | None = None
    priority: TicketPriority = TicketPriority.medium
    environment: TicketEnvironment = TicketEnvironment.development
    follow_up_target: date | None = None
    pic_ids: list[int] = []


class TicketCreate(TicketBase):
    # status is always forced to open on create (server-side)
    pass


class TicketUpdate(BaseModel):
    record_type: TicketRecordType | None = None
    project_id: int | None = None
    module_name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=220)
    description: str | None = None
    priority: TicketPriority | None = None
    environment: TicketEnvironment | None = None
    follow_up_target: date | None = None
    status: TicketStatus | None = None
    pic_ids: list[int] | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_number: str
    record_type: TicketRecordType
    project_id: int
    project_name: str | None = None
    module_name: str = ""
    title: str
    description: str | None = None
    priority: TicketPriority
    environment: TicketEnvironment
    follow_up_target: date | None = None
    status: TicketStatus
    pic_ids: list[int] = []
    pics: list[UserOut] = []
    attachments: list[TicketAttachmentOut] = []
    created_by_id: int | None = None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    items: list[TicketOut]
    total: int
    page: int
    page_size: int
    pages: int


class TicketStats(BaseModel):
    total: int
    open: int
    in_progress: int
    resolved: int


class TicketModulesResponse(BaseModel):
    project_id: int | None = None
    modules: list[str]


class DiscussionAuthorOut(BaseModel):
    id: int
    name: str
    role: str
    avatar_url: str


class DiscussionAttachmentOut(BaseModel):
    id: int
    kind: str
    original_name: str
    content_type: str
    size_bytes: int
    url: str


class DiscussionReactionOut(BaseModel):
    emoji: str
    count: int
    reacted_by_me: bool
    user_ids: list[int] = []


class DiscussionMentionOut(BaseModel):
    id: int
    name: str


class DiscussionParentPreview(BaseModel):
    id: int
    author_name: str
    body_preview: str


class DiscussionMessageOut(BaseModel):
    id: int
    project_id: int
    body: str
    created_at: datetime
    updated_at: datetime | None = None
    is_deleted: bool = False
    author: DiscussionAuthorOut
    parent: DiscussionParentPreview | None = None
    attachments: list[DiscussionAttachmentOut] = []
    reactions: list[DiscussionReactionOut] = []
    mentions: list[DiscussionMentionOut] = []


class DiscussionMessageCreate(BaseModel):
    body: str = Field(default="", max_length=8000)
    parent_id: int | None = None
    mention_ids: list[int] = []


class DiscussionReactionCreate(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class DiscussionListResponse(BaseModel):
    items: list[DiscussionMessageOut]
    total: int
    has_more: bool = False
