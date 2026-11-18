from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import ProjectStatus, TaskStatus


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
    member_ids: list[int] | None = None


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    members: list[TeamMemberOut] = []
    task_count: int = 0


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
