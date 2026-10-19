from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, Dec


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="staff")  # admin | staff
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(80), default="")
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str] = mapped_column(String(30), default="", index=True)
    address: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    phone: Mapped[str] = mapped_column(String(30), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(30))  # cash|bank|upi|card|owner_personal|staff_advance|other
    is_physical_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    opening_balance: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class CashMovement(Base):
    """Every actual inflow/outflow of money, posted exactly once. Signed amount."""
    __tablename__ = "cash_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    amount: Mapped[Decimal] = mapped_column(Dec)  # signed
    movement_type: Mapped[str] = mapped_column(String(40), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reversal_of_id: Mapped[int | None] = mapped_column(ForeignKey("cash_movements.id"), nullable=True)
    account: Mapped[Account] = relationship()


class SaleBill(Base):
    __tablename__ = "sale_bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_no: Mapped[str] = mapped_column(String(60), index=True)
    pos_bill_no: Mapped[str] = mapped_column(String(60), default="")
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    business_date: Mapped[date] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Dec)
    paid_now: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    in_pos_report: Mapped[bool] = mapped_column(Boolean, default=True)
    count_as_new_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    attachment: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="posted")  # posted|voided
    void_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    customer: Mapped[Customer] = relationship()
    lines: Mapped[list["SaleBillLine"]] = relationship(cascade="all, delete-orphan")


class SaleBillLine(Base):
    __tablename__ = "sale_bill_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("sale_bills.id"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(200), default="")
    quantity: Mapped[Decimal] = mapped_column(Dec, default=Decimal("1"))
    unit: Mapped[str] = mapped_column(String(30), default="")
    unit_price: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    discount: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    receipt_date: Mapped[date] = mapped_column(Date)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    amount: Mapped[Decimal] = mapped_column(Dec)
    method: Mapped[str] = mapped_column(String(20))  # cash|upi|card|bank|other
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    reference: Mapped[str] = mapped_column(String(100), default="")
    received_by: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="collection")  # collection|bill_time
    post_to_cashbook: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="posted")  # posted|voided
    void_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    customer: Mapped[Customer] = relationship()
    account: Mapped[Account] = relationship()
    allocations: Mapped[list["ReceiptAllocation"]] = relationship(back_populates="receipt")


class ReceiptAllocation(Base):
    __tablename__ = "receipt_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), index=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("sale_bills.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Dec)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    receipt: Mapped[Receipt] = relationship(back_populates="allocations")
    bill: Mapped[SaleBill] = relationship()


class BillAdjustment(Base):
    """Approved credit note / write-off reducing a bill's outstanding (admin only)."""
    __tablename__ = "bill_adjustments"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("sale_bills.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # credit_note|writeoff
    amount: Mapped[Decimal] = mapped_column(Dec)
    reason: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    adj_date: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    payee_name: Mapped[str] = mapped_column(String(160), default="")
    bill_ref: Mapped[str] = mapped_column(String(80), default="")
    total: Mapped[Decimal] = mapped_column(Dec)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    attachment: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    purchase_bill_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_bills.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="posted")  # posted|voided
    void_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    vendor: Mapped[Vendor | None] = relationship()
    payments: Mapped[list["ExpensePayment"]] = relationship(back_populates="expense")


class ExpensePayment(Base):
    __tablename__ = "expense_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Dec)
    paid_date: Mapped[date] = mapped_column(Date, index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    method: Mapped[str] = mapped_column(String(20))
    funded_by: Mapped[str] = mapped_column(String(20), default="account")  # account|owner
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    paid_by: Mapped[str] = mapped_column(String(100), default="")
    payee: Mapped[str] = mapped_column(String(160), default="")
    reference: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="posted")
    void_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expense: Mapped[Expense] = relationship(back_populates="payments")
    account: Mapped[Account | None] = relationship()


class OwnerLedgerEntry(Base):
    __tablename__ = "owner_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))  # funded|contribution|reimbursement
    amount: Mapped[Decimal] = mapped_column(Dec)  # always positive; kind gives direction
    expense_payment_id: Mapped[int | None] = mapped_column(ForeignKey("expense_payments.id"), nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    method: Mapped[str] = mapped_column(String(20), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    norm_name: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str] = mapped_column(String(120), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(20), default="product")  # product|prepared_dish
    base_unit: Mapped[str] = mapped_column(String(30), default="Nos")
    sell_unit: Mapped[str] = mapped_column(String(30), default="")
    purchase_unit: Mapped[str] = mapped_column(String(30), default="")
    purchase_to_base: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    sell_to_base: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    track_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    low_stock_threshold: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=True)  # not yet reviewed by owner
    uom_hint: Mapped[str] = mapped_column(String(30), default="")
    source_name: Mapped[str] = mapped_column(String(200), default="")
    source_report: Mapped[str] = mapped_column(String(40), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ItemAlias(Base):
    __tablename__ = "item_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(200))
    norm_alias: Mapped[str] = mapped_column(String(200), unique=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    source_report: Mapped[str] = mapped_column(String(40), default="")
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    movement_type: Mapped[str] = mapped_column(String(30))
    # opening_count|purchase_in|sale_out|sale_return|supplier_return|wastage|adjustment_in|adjustment_out|other_in|other_out
    quantity: Mapped[Decimal] = mapped_column(Dec)  # signed, base unit. opening_count = absolute baseline
    source_type: Mapped[str] = mapped_column(String(40), default="")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)
    item: Mapped[Item] = relationship()


class PurchaseBill(Base):
    __tablename__ = "purchase_bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    invoice_no: Mapped[str] = mapped_column(String(80), default="")
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    discount: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Dec)
    notes: Mapped[str] = mapped_column(Text, default="")
    attachment: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="posted")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    vendor: Mapped[Vendor] = relationship()
    lines: Mapped[list["PurchaseLine"]] = relationship(cascade="all, delete-orphan")


class PurchaseLine(Base):
    __tablename__ = "purchase_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("purchase_bills.id"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    quantity: Mapped[Decimal] = mapped_column(Dec)
    unit: Mapped[str] = mapped_column(String(30), default="")
    conversion_factor: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    base_quantity: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(Dec)
    stock_posted: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(30))  # item_sales|stock_position
    filename: Mapped[str] = mapped_column(String(200))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    stored_file: Mapped[str] = mapped_column(String(200), default="")
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    print_info: Mapped[str] = mapped_column(String(100), default="")
    outlet_name: Mapped[str] = mapped_column(String(160), default="")
    extraction_method: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|confirmed|rejected|reversed
    printed_grand_total: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    printed_grand_qty: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    rows: Mapped[list["ImportRow"]] = relationship(cascade="all, delete-orphan", order_by="ImportRow.seq")


class ImportRow(Base):
    __tablename__ = "import_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer, default=1)
    row_type: Mapped[str] = mapped_column(String(20))  # item|heading|subtotal|grand_total|ditto|unknown|end
    raw_name: Mapped[str] = mapped_column(String(300), default="")
    name: Mapped[str] = mapped_column(String(300), default="")  # editable normalized name
    category: Mapped[str] = mapped_column(String(120), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    qty: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    cancel_orders: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    uom: Mapped[str] = mapped_column(String(30), default="")
    confidence: Mapped[float] = mapped_column(default=1.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    exclude_reason: Mapped[str] = mapped_column(String(200), default="")
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    suggested_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    create_item: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)


class ItemSaleLine(Base):
    """Confirmed item sales (report data — NOT cash collected)."""
    __tablename__ = "item_sale_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    source_name: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str] = mapped_column(String(120), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    qty: Mapped[Decimal] = mapped_column(Dec)
    amount: Mapped[Decimal] = mapped_column(Dec)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    item: Mapped[Item] = relationship()


class DayClose(Base):
    __tablename__ = "day_closes"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|finalized|reopened
    opening_cash: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    opening_note: Mapped[str] = mapped_column(Text, default="")
    pos_total_sales: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    cash_sales: Mapped[Decimal] = mapped_column(Dec, default=Decimal("0"))
    upi_sales: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    card_sales: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    other_sales: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    credit_sales: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    physical_counted: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    variance: Mapped[Decimal | None] = mapped_column(Dec, nullable=True)
    variance_reason: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reopen_reason: Mapped[str] = mapped_column(Text, default="")
    reopened_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
