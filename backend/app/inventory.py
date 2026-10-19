"""Item catalogue + stock movement ledger. Stock is always derived from movements."""
import difflib
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from .core import audit, err, norm_name
from .models import InventoryMovement, Item, ItemAlias, User

ZERO = Decimal("0")
IN_TYPES = {"purchase_in", "sale_return", "adjustment_in", "other_in"}
OUT_TYPES = {"sale_out", "supplier_return", "wastage", "adjustment_out", "other_out"}


def find_item(db: Session, name: str) -> Item | None:
    n = norm_name(name)
    if not n:
        return None
    al = db.query(ItemAlias).filter(ItemAlias.norm_alias == n).first()
    if al:
        return db.get(Item, al.item_id)
    return db.query(Item).filter(Item.norm_name == n).first()


def suggest_item(db: Session, name: str):
    """Fuzzy suggestion only — never applied automatically."""
    n = norm_name(name)
    best, score = None, 0.0
    for it in db.query(Item).filter(Item.active.is_(True)):
        s = difflib.SequenceMatcher(None, n, it.norm_name).ratio()
        if s > score:
            best, score = it, s
    return (best, score) if best and score >= 0.82 else (None, 0.0)


def create_item(db: Session, user: User | None, name: str, *, source_report="", source_name="", category="",
                department="", uom_hint="", pending=True, **kw) -> Item:
    n = norm_name(name)
    if not n:
        err(422, "Item name is required")
    if db.query(Item).filter(Item.norm_name == n).first() or db.query(ItemAlias).filter(ItemAlias.norm_alias == n).first():
        err(409, f"An item or alias named '{name}' already exists")
    it = Item(name=name.strip(), norm_name=n, source_report=source_report, source_name=source_name or name,
              category=category, department=department, uom_hint=uom_hint, pending=pending, **kw)
    db.add(it)
    db.flush()
    audit(db, user, "create", "item", it.id, after={"name": it.name, "source": source_report})
    return it


def add_alias(db, user, item: Item, alias: str, source_report=""):
    n = norm_name(alias)
    if not n or n == item.norm_name:
        return None
    ex = db.query(ItemAlias).filter(ItemAlias.norm_alias == n).first()
    if ex:
        if ex.item_id != item.id:
            err(409, f"Alias '{alias}' already points to a different item")
        return ex
    other = db.query(Item).filter(Item.norm_name == n).first()
    if other and other.id != item.id:
        err(409, f"Alias '{alias}' matches another catalogue item")
    a = ItemAlias(alias=alias.strip(), norm_alias=n, item_id=item.id, source_report=source_report,
                  confirmed_by=user.id if user else None)
    db.add(a)
    return a


def post_movement(db, user, item: Item, mtype: str, quantity: Decimal, d: date, reason="", source_type="",
                  source_id=None, batch_id=None) -> InventoryMovement:
    if mtype in IN_TYPES:
        signed = abs(quantity)
    elif mtype in OUT_TYPES:
        signed = -abs(quantity)
    elif mtype == "opening_count":
        signed = quantity
    else:
        err(422, f"Unknown movement type {mtype}")
    mv = InventoryMovement(item_id=item.id, business_date=d, movement_type=mtype, quantity=signed, reason=reason,
                           source_type=source_type, source_id=source_id, import_batch_id=batch_id,
                           user_id=user.id if user else None)
    db.add(mv)
    return mv


def stock_view(db: Session, item: Item) -> dict:
    mvs = db.query(InventoryMovement).filter(InventoryMovement.item_id == item.id, InventoryMovement.reversed.is_(False)) \
        .order_by(InventoryMovement.business_date, InventoryMovement.id).all()
    openings = [m for m in mvs if m.movement_type == "opening_count"]
    base = openings[-1] if openings else None
    moves_after = [m for m in mvs if m.movement_type != "opening_count" and
                   (base is None or (m.business_date, m.id) > (base.business_date, base.id))]
    net = sum((m.quantity for m in moves_after), ZERO)
    out = {
        "item_id": item.id, "name": item.name, "base_unit": item.base_unit, "track_stock": item.track_stock,
        "baseline_status": "set" if base else "unknown",
        "baseline_date": base.business_date.isoformat() if base else None,
        "baseline_qty": base.quantity if base else None,
        "net_movement_since_baseline": net,
        "estimated_stock": (base.quantity + net) if base else None,
        "last_movement": max((m.business_date for m in mvs), default=None),
        "low_stock_threshold": item.low_stock_threshold,
    }
    out["last_movement"] = out["last_movement"].isoformat() if out["last_movement"] else None
    out["below_threshold"] = bool(base and item.low_stock_threshold is not None and out["estimated_stock"] < item.low_stock_threshold)
    out["label"] = ("Estimated stock" if base else "Opening baseline unknown — movements only")
    return out


def post_sale_out(db, user, item: Item, quantity: Decimal, d: date, batch_id: int):
    """Sale-side stock-out. Only tracked, non-dish items are affected."""
    if not item.track_stock or item.kind == "prepared_dish":
        return None
    return post_movement(db, user, item, "sale_out", quantity, d, "Confirmed Item Sales import", "import", batch_id, batch_id)
