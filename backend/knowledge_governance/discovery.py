"""Ontology Discovery —— 从当前图谱生成本体草稿，供人工确认后落地。"""

from collections import defaultdict

from .analyzer import analyze_graph
from .seed import RESOURCE_SUBTYPES, classify_resource_subtype, GRAPH_TO_ONTOLOGY
from .repository import get_kg_store


def discover_ontology(store=None):
    report = analyze_graph(store)
    kg = get_kg_store()
    existing = {t["name"]: t for t in kg.list_types()}

    draft = {
        "entityTypes": [],
        "from_graph": True,
        "note": "由现有节点/关系反向生成，不会改写已有 type 字段。确认后才写入本体层。",
    }

    type_counts = report.get("types") or {}
    for gtype, count in type_counts.items():
        oname = GRAPH_TO_ONTOLOGY.get(gtype, gtype)
        entry = {
            "entityType": oname,
            "graphType": gtype,
            "instanceCount": count,
            "alreadyInOntology": oname in existing,
            "subTypes": [],
        }
        if gtype == "Resource":
            buckets = defaultdict(list)
            # members from clusters + hierarchy
            for cluster in report.get("clusters") or []:
                if cluster.get("graph_type") != "Resource":
                    continue
                onto = cluster.get("ontology_type") or "DeliveryResource"
                for m in cluster.get("members") or []:
                    buckets[onto].append(m)
            for item in report.get("hierarchy_candidates") or []:
                buckets[item.get("suggested_ontology") or "DeliveryResource"].append({
                    "id": item.get("child_id"),
                    "name": item.get("child"),
                })
            seen = set()
            for sub in RESOURCE_SUBTYPES:
                children = []
                for m in buckets.get(sub["name"]) or []:
                    key = m.get("id") or m.get("name")
                    if key in seen:
                        continue
                    seen.add(key)
                    children.append(m)
                entry["subTypes"].append({
                    "name": sub["name"],
                    "label": sub["label"],
                    "description": sub["description"],
                    "children": children[:40],
                    "alreadyInOntology": sub["name"] in existing,
                })
        draft["entityTypes"].append(entry)

    draft["allowedRelations"] = [
        {"name": r["name"], "sourceType": r["source_type"], "targetType": r["target_type"], "description": r.get("description")}
        for r in kg.list_ontology_relations()
    ]
    draft["problems"] = report.get("problems") or []
    return draft


def classify_node(node):
    gtype = node.get("type")
    onto = GRAPH_TO_ONTOLOGY.get(gtype, gtype or "Entity")
    if gtype == "Resource":
        onto = classify_resource_subtype(node)
    return onto
