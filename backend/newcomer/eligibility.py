"""按角色评估范围 + 新人成熟度门槛，筛选竞争分析人员。"""

from database import get_all_members, get_ai_role_assignments

from . import repository as repo
from .templates import level_index, SCOPE_LABELS


def max_completed_level(newcomer_id):
    tasks = repo.list_tasks(newcomer_id)
    done = [t for t in tasks if t.get("status") == "completed"]
    if not done:
        return -1
    return max(level_index(t.get("task_level")) for t in done)


def newcomer_qualifies(nc, role):
    if not nc or not nc.get("compete_in_ranking"):
        return False
    min_lv = level_index(role.get("minimum_competition_level") or "L2")
    if max_completed_level(nc["id"]) >= min_lv:
        return True
    min_score = float(role.get("minimum_match_score") or 60)
    assigns = get_ai_role_assignments(role["id"])
    mine = next((a for a in assigns if a["employee_id"] == nc["employee_id"]), None)
    if mine and float(mine.get("match_score") or 0) >= min_score:
        return True
    return False


def resolve_candidates_for_role(role, members=None):
    members = members if members is not None else get_all_members()
    mmap = {m["id"]: m for m in members}
    scope = (role.get("evaluation_scope_type") or "TEAM").upper()
    config = role.get("evaluation_scope_config") or {}
    newcomers = {n["employee_id"]: n for n in repo.list_newcomers()}

    if scope == "CUSTOM":
        ids = list(config.get("employee_ids") or [])
        return [mmap[i] for i in ids if i in mmap]

    if scope == "PROJECT":
        pids = repo.project_member_ids(config.get("project"))
        pool = [m for m in members if m["id"] in pids] if pids else list(members)
    else:
        pool = list(members)

    result = []
    for m in pool:
        nc = newcomers.get(m["id"])
        if not nc:
            result.append(m)
            continue
        if newcomer_qualifies(nc, role):
            result.append(m)
    return result


def scope_label(role):
    scope = (role.get("evaluation_scope_type") or "TEAM").upper()
    label = SCOPE_LABELS.get(scope, scope)
    if scope == "PROJECT":
        proj = (role.get("evaluation_scope_config") or {}).get("project")
        if proj:
            return f"{label} · {proj}"
    if scope == "CUSTOM":
        n = len((role.get("evaluation_scope_config") or {}).get("employee_ids") or [])
        return f"{label}（{n} 人）"
    return label
