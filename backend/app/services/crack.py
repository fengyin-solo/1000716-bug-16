"""裂缝处置业务规则：状态流转、字段校验、合并处置与处理留痕都收在这里。

所有流转结果（处置状态、裂缝类型等字段、处理记录、时间戳）都直接写回
store 里的同一行 dict，保证列表、详情、看板读到的是同一份已落库数据，
服务重启前刷新页面仍然停留在流转后的环节。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "crack"
REQUIRED_FIELDS = ["处置单号", "所在路段", "裂缝类型"]
# 动作执行时允许一并修改的业务字段；处置单号与所在路段是关联键，不在这里开放
EDITABLE_FIELDS = ["裂缝类型", "裂缝长度", "灌缝材料", "作业班组"]
STATUS_ORDER = ["待安排", "处置中", "已完成", "已取消"]
ACTION_RULES = {
    "安排处置": "处置中",
    "确认完成": "已完成",
    "退回重做": "处置中",
    "取消处置": "已取消",
}
# 每个动作允许从哪些状态发起；不写死成顺序推进，合并处置时同伴单据可被带流转
ALLOWED_TRANSITIONS = {
    "安排处置": {"待安排"},
    "确认完成": {"处置中"},
    "退回重做": {"已完成"},
    "取消处置": {"待安排", "处置中"},
}
NEGATIVE_ACTIONS = ["退回重做", "取消处置"]
# 流转到这些状态后单据不再占用待处理口径（看板/列表统计共用）
SETTLED_STATUSES = {"已完成", "已取消"}
TERMINAL_STATUS = "已取消"


def _today() -> str:
    return date.today().isoformat()


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _clean(value: Any) -> str:
    return str(value if value is not None else "").strip()


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
        missing = [field for field in REQUIRED_FIELDS if not _clean(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: _clean(values.get(field)) for field in REQUIRED_FIELDS})
        # 选填字段登记时也一并落库
        for field in ["裂缝长度", "灌缝材料", "作业班组"]:
            text = _clean(values.get(field))
            if text:
                entry[field] = text
        entry["完成日期"] = None
        entry["处置完成时间"] = None
        entry["处置状态"] = STATUS_ORDER[0]
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["处理记录"] = []
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
        remark: str | None = None,
        merge_ids: list[int] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"处置单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于裂缝处置可执行范围"

        target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current not in ALLOWED_TRANSITIONS[action]:
            allowed = "、".join(sorted(ALLOWED_TRANSITIONS[action]))
            return None, f"处置单当前为「{current}」，仅{allowed}状态可执行「{action}」"

        # 同路段合并处置：同伴处置单必须存在且与主单在同一路段
        merge_entries: list[dict[str, Any]] = []
        for other_id in merge_ids or []:
            if other_id == entry_id:
                continue
            other = store.find(MODULE, other_id)
            if other is None:
                return None, f"被合并的处置单 {other_id} 不存在或已归档"
            if _clean(other.get("所在路段")) != _clean(entry.get("所在路段")):
                return None, f"处置单 {other_id} 所在路段与主单不一致，不能合并处置"
            if other.get("status") == TERMINAL_STATUS:
                return None, f"处置单 {other_id} 已取消，不能参与合并处置"
            merge_entries.append(other)

        opinion = _clean(values.pop("处理意见", remark))
        raw_photos = values.pop("处置照片", [])
        if isinstance(raw_photos, str):
            raw_photos = [p for p in raw_photos.replace("，", ",").split(",")]
        photos = [p.strip() for p in raw_photos if _clean(p)]

        # 裂缝类型等业务字段随本次动作一起落库，字段改了才走得动下一环节
        changed_fields: dict[str, str] = {}
        for field in EDITABLE_FIELDS:
            if field in values:
                text = _clean(values.get(field))
                if text:
                    entry[field] = text
                    changed_fields[field] = text

        group_ids = [entry_id, *(int(row["id"]) for row in merge_entries)]
        group_ids.sort()
        acted = [entry, *merge_entries]
        for index, row in enumerate(acted):
            is_primary = index == 0
            record: dict[str, Any] = {
                "动作": action,
                "流转后状态": target,
                "处理意见": opinion,
                "处置照片": list(photos),
                "操作时间": _now_text(),
            }
            if merge_entries:
                record["合并组"] = list(group_ids)
                record["合并角色"] = "主单" if is_primary else "同路段合并"
            # 同伴单据的字段修改不套用主单的值，只同步状态与处理留痕
            if is_primary:
                for field, text in changed_fields.items():
                    row[field] = text
            row["status"] = target
            row["处置状态"] = target
            row["pending"] = target not in SETTLED_STATUSES
            row["abnormal"] = action in NEGATIVE_ACTIONS
            if action == "确认完成":
                row["完成日期"] = _today()
                row["处置完成时间"] = _now_text()
            elif action == "退回重做":
                # 退回后回到处置中，原完成结论清空，但历次处理意见与照片在处理记录里保留
                row["完成日期"] = None
                row["处置完成时间"] = None
            row.setdefault("处理记录", []).append(record)

        if merge_entries:
            merged_nos = "、".join(str(row.get("处置单号", row.get("id"))) for row in merge_entries)
            return entry, f"处置单已{action}，已同步同路段处置单：{merged_nos}"
        return entry, f"处置单已{action}"
