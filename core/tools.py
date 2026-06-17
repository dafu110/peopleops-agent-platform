from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from .audit import write_audit_event
from .config import get_settings
from .database import create_interview_action
from .security import redact_pii, stable_hash


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    status: str
    message: str
    metadata: Dict[str, Any]

    def to_markdown(self) -> str:
        details = "\n".join([f"- {key}: {value}" for key, value in self.metadata.items()])
        if details:
            details = f"\n\n{details}"
        return f"**[{self.status}] {self.tool_name}**\n\n{self.message}{details}"


def _safe_slug(value: str) -> str:
    return stable_hash(value or str(uuid4()))


def _write_email_draft(candidate_name: str, interview_time: str) -> Path:
    settings = get_settings()
    settings.email_draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = settings.email_draft_dir / f"interview_{_safe_slug(candidate_name + interview_time)}.eml"

    message = EmailMessage()
    message["Subject"] = f"面试邀约 - {candidate_name}"
    message["From"] = "hr@example.com"
    message["To"] = "candidate@example.com"
    message.set_content(
        f"""您好，{candidate_name}：

感谢您关注我们的岗位。现邀请您参加面试，时间为：{interview_time}。

请提前准备个人项目、AI Agent/RAG 相关经历，并回复确认是否方便。

PeopleOps Agent Platform
"""
    )
    draft_path.write_text(message.as_string(), encoding="utf-8")
    return draft_path


def _write_calendar_event(candidate_name: str, interview_time: str) -> Path:
    settings = get_settings()
    settings.calendar_dir.mkdir(parents=True, exist_ok=True)
    event_id = _safe_slug(candidate_name + interview_time)
    event_path = settings.calendar_dir / f"interview_{event_id}.ics"
    event_path.write_text(
        f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PeopleOps Agent Platform//Interview Scheduler//CN
BEGIN:VEVENT
UID:{event_id}@peopleops-agent.local
SUMMARY:Interview with {candidate_name}
DESCRIPTION:Interview arranged by PeopleOps Agent Platform. Requested time: {interview_time}
END:VEVENT
END:VCALENDAR
""",
        encoding="utf-8",
    )
    return event_path


def schedule_interview(
    candidate_name: str,
    interview_time: str,
    *,
    created_by: str = "local-admin",
) -> ToolExecutionResult:
    settings = get_settings()
    mode = settings.tool_execution_mode.lower()
    safe_candidate_name = redact_pii(candidate_name)
    safe_interview_time = redact_pii(interview_time)

    email_draft_path: Optional[Path] = None
    calendar_event_path: Optional[Path] = None
    status = "DRY_RUN"

    if mode in {"local", "live"}:
        email_draft_path = _write_email_draft(candidate_name, interview_time)
        calendar_event_path = _write_calendar_event(candidate_name, interview_time)
        status = "PERSISTED"

    action_id = create_interview_action(
        candidate_name=safe_candidate_name,
        interview_time=safe_interview_time,
        status=status,
        email_draft_path=email_draft_path,
        calendar_event_path=calendar_event_path,
        created_by=created_by,
    )

    result = ToolExecutionResult(
        tool_name="schedule_interview",
        status=status,
        message=f"已为候选人【{safe_candidate_name}】生成面试邀约动作，并写入本地 ATS 数据库。",
        metadata={
            "action_id": action_id,
            "interview_time": safe_interview_time,
            "execution_mode": mode,
            "email_draft_path": str(email_draft_path) if email_draft_path else "dry_run",
            "calendar_event_path": str(calendar_event_path) if calendar_event_path else "dry_run",
            "ats_record": "interview_actions",
        },
    )

    write_audit_event(
        "tool.schedule_interview",
        {
            "candidate_ref": stable_hash(candidate_name),
            "interview_time": safe_interview_time,
            "execution_mode": mode,
            "result": asdict(result),
        },
    )
    return result
