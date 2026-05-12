"""
Inventory Service — manages all inventory movements atomically.

Rules:
- NEVER update WarehouseStock.quantity directly from outside this module.
- Every movement must go through one of these functions.
- The caller (router / background task) is responsible for db.commit().
  These functions only stage changes within the current session — this allows
  multiple operations to be bundled into a single atomic DB transaction.
- All stock queries use .with_for_update() to prevent race conditions when
  two technicians try to issue the same part simultaneously.
"""

from typing import Optional
from sqlalchemy.orm import Session

from app.models.warehouse_stock import WarehouseStock
from app.models.inventory_transaction import InventoryTransaction


def _get_or_create_stock(
    db: Session,
    part_id,
    warehouse_id,
    lock: bool = False
) -> WarehouseStock:
    """Return the stock row for (part, warehouse), creating it at 0 if missing."""
    q = db.query(WarehouseStock).filter_by(part_id=part_id, warehouse_id=warehouse_id)
    if lock:
        q = q.with_for_update()
    stock = q.first()
    if not stock:
        stock = WarehouseStock(part_id=part_id, warehouse_id=warehouse_id, quantity=0)
        db.add(stock)
        db.flush()  # assign id without committing
    return stock


def issue_part(
    db: Session,
    *,
    part_id,
    warehouse_id,
    quantity: int,
    service_call_id=None,
    technician_id=None,
    notes: Optional[str] = None,
) -> InventoryTransaction:
    """
    Dispense a part from a warehouse for a service call.
    Raises ValueError if there is insufficient stock.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    stock = _get_or_create_stock(db, part_id, warehouse_id, lock=True)

    if stock.quantity < quantity:
        raise ValueError(
            f"Insufficient stock: requested {quantity}, available {stock.quantity}."
        )

    stock.quantity -= quantity

    transaction = InventoryTransaction(
        part_id=part_id,
        source_warehouse_id=warehouse_id,
        transaction_type="ISSUE",
        quantity=quantity,
        service_call_id=service_call_id,
        created_by=technician_id,
        notes=notes,
    )
    db.add(transaction)
    return transaction


def transfer_part(
    db: Session,
    *,
    part_id,
    source_warehouse_id,
    target_warehouse_id,
    quantity: int,
    technician_id=None,
    notes: Optional[str] = None,
) -> InventoryTransaction:
    """
    Move stock between two warehouses (e.g. main warehouse → technician vehicle).
    Both stock rows are locked to prevent race conditions.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")
    if source_warehouse_id == target_warehouse_id:
        raise ValueError("Source and target warehouse must differ.")

    source_stock = _get_or_create_stock(db, part_id, source_warehouse_id, lock=True)
    if source_stock.quantity < quantity:
        raise ValueError(
            f"Insufficient stock in source warehouse: requested {quantity}, available {source_stock.quantity}."
        )

    target_stock = _get_or_create_stock(db, part_id, target_warehouse_id, lock=True)

    source_stock.quantity -= quantity
    target_stock.quantity += quantity

    transaction = InventoryTransaction(
        part_id=part_id,
        source_warehouse_id=source_warehouse_id,
        target_warehouse_id=target_warehouse_id,
        transaction_type="TRANSFER",
        quantity=quantity,
        created_by=technician_id,
        notes=notes,
    )
    db.add(transaction)
    return transaction


def receive_part(
    db: Session,
    *,
    part_id,
    warehouse_id,
    quantity: int,
    unit_price: Optional[float] = None,
    reference_number: Optional[str] = None,
    technician_id=None,
    notes: Optional[str] = None,
) -> InventoryTransaction:
    """
    Record goods received from a supplier into a warehouse.
    Increases warehouse stock and logs the receipt.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    stock = _get_or_create_stock(db, part_id, warehouse_id, lock=True)
    stock.quantity += quantity

    transaction = InventoryTransaction(
        part_id=part_id,
        target_warehouse_id=warehouse_id,
        transaction_type="RECEIPT",
        quantity=quantity,
        unit_price=unit_price,
        reference_number=reference_number,
        created_by=technician_id,
        notes=notes,
    )
    db.add(transaction)
    return transaction


def return_part(
    db: Session,
    *,
    part_id,
    warehouse_id,
    quantity: int,
    service_call_id=None,
    technician_id=None,
    notes: Optional[str] = None,
) -> InventoryTransaction:
    """
    Return a part from the field back to a warehouse
    (e.g. a technician returns an unused spare).
    """
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    stock = _get_or_create_stock(db, part_id, warehouse_id, lock=True)
    stock.quantity += quantity

    transaction = InventoryTransaction(
        part_id=part_id,
        target_warehouse_id=warehouse_id,
        transaction_type="RETURN",
        quantity=quantity,
        service_call_id=service_call_id,
        created_by=technician_id,
        notes=notes,
    )
    db.add(transaction)
    return transaction
