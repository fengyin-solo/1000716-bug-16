"""裂缝处置业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "crack"
REQUIRED_FIELDS = ["处置单号", "所在路段", "裂缝类型"]
STATUS_ORDER = ["待安排", "处置中", "已完成", "已取消"]
ACTION_RULES = {"安排处置": "处置中", "确认完成": "已完成", "取消处置": "已取消"}
RETURN_ACTION = "退回重做"
NEGATIVE_ACTIONS = []
TERMINAL_STATUSES = ["已完成", "已取消"]
# 随动作一起落库的字段；处理意见与照片在退回重做后仍然保留
EDITABLE_FIELDS = ["所在路段", "裂缝类型", "裂缝长度", "灌缝材料", "作业班组", "完成日期", "处理意见", "照片"]


class CrackService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("处置单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["处置状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"处置单 {entry_id} 不存在或已归档"
        updates = self._collect_updates(values or {})
        if not action:
            if not updates:
                return None, "未指定要执行的动作，也没有需要保存的字段"
            entry.update(updates)
            return entry, "处置单修改已保存"
        if action == RETURN_ACTION:
            target = self._return_target(entry)
            if target is None:
                return None, f"处置单当前状态「{entry.get('status')}」不能退回重做"
        elif action in ACTION_RULES:
            target = ACTION_RULES[action]
        else:
            return None, f"动作「{action}」不属于裂缝处置可执行范围"
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        origin = entry.get("status")
        entry.update(updates)
        self._transition(entry, target, action, provided_date=updates.get("完成日期"))
        merged = self._cascade_section(entry, origin, target, action)
        message = f"处置单已{action}"
        if merged:
            message += f"，同路段另有 {merged} 条处置单一并流转"
        return entry, message

    def _collect_updates(self, values: dict[str, Any]) -> dict[str, Any]:
        """只保留允许随动作落库的字段，action 等控制字段不写入单据。"""
        return {
            field: values[field]
            for field in EDITABLE_FIELDS
            if field in values and values[field] is not None
        }

    def _return_target(self, entry: dict[str, Any]) -> str | None:
        """退回重做：沿状态序列回退一个环节；待安排与已取消不允许再退。"""
        status = entry.get("status")
        if status not in STATUS_ORDER or status == STATUS_ORDER[-1]:
            return None
        index = STATUS_ORDER.index(status)
        if index == 0:
            return None
        return STATUS_ORDER[index - 1]

    def _transition(
        self,
        entry: dict[str, Any],
        target: str,
        action: str,
        *,
        provided_date: Any = None,
    ) -> None:
        """把状态、处置状态与看板标记一起写牢，确认完成时留下完成日期。"""
        entry["status"] = target
        entry["处置状态"] = target
        entry["pending"] = target not in TERMINAL_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "确认完成":
            stamped = str(provided_date or "").strip()
            entry["完成日期"] = stamped or date.today().isoformat()

    def _cascade_section(
        self,
        entry: dict[str, Any],
        origin: Any,
        target: str,
        action: str,
    ) -> int:
        """同一路段、同一环节的处置单按合并处理一起流转，不允许半路掉队。"""
        section = str(entry.get("所在路段") or "").strip()
        if not section:
            return 0
        merged = 0
        for sibling in store.rows(MODULE):
            if sibling is entry:
                continue
            if str(sibling.get("所在路段") or "").strip() != section:
                continue
            if sibling.get("status") != origin:
                continue
            self._transition(sibling, target, action)
            merged += 1
        return merged
