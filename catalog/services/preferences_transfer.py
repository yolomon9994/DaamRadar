"""Read-only portable watch-target and budget preview; never import observations."""
from catalog.services.list_transfer import resolve_list


def resolve_preferences(document):
    targets = document["targets"]
    resolved = resolve_list({"source": document["source"], "items": [
        {"slug": item["slug"], "quantity": 1, "product": item["product"]} for item in targets]})
    rows = []
    for original, item in zip(targets, resolved["items"]):
        rows.append({key: value for key, value in item.items() if key not in {"quantity", "imported_name"}} | {
            "target": original["target"],
            "name": item["product"]["name"] if item["product"] else original["name"],
            "size": item["product"]["size"] if item["product"] else original["size"],
        })
    return {"source": document["source"], "budget": document["budget"], "targets": rows}
