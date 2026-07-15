import threading
import uuid
from datetime import datetime, timedelta
from math import floor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, restock_orders

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

# Restocking feature: submitted orders always ship with this fixed lead time
RESTOCK_LEAD_TIME_DAYS = 10
# Guards the read-then-append sequence below so concurrent submissions can't
# race onto the same order_number.
restock_orders_lock = threading.Lock()

class RestockRecommendation(BaseModel):
    item_sku: str
    item_name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    current_demand: int
    forecasted_demand: int
    trend: str
    is_urgent: bool
    demand_growth_percent: float
    suggested_quantity: int
    estimated_cost: float

class RestockRecommendationsResponse(BaseModel):
    budget: float
    total_estimated_cost: float
    remaining_budget: float
    recommendations: List[RestockRecommendation]

class RestockOrderItemRequest(BaseModel):
    sku: str
    quantity: int = Field(gt=0)

class CreateRestockOrderRequest(BaseModel):
    items: List[RestockOrderItemRequest]
    notes: Optional[str] = None

class RestockOrder(BaseModel):
    id: str
    order_number: str
    items: List[dict]
    status: str
    order_date: str
    lead_time_days: int
    expected_delivery: str
    total_value: float
    notes: Optional[str] = None

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

@app.get("/api/restock/recommendations", response_model=RestockRecommendationsResponse)
def get_restock_recommendations(budget: float):
    """Get urgency-ranked restock recommendations that fit within a budget.

    Urgency-first: items trending "increasing" AND at/below their inventory
    reorder_point are ranked ahead of other "increasing" items, each bucket
    sorted by forecasted demand growth %. The budget is then greedily filled
    in that rank order.
    """
    if budget < 0:
        raise HTTPException(status_code=400, detail="Budget must be non-negative")

    inventory_by_sku = {item["sku"]: item for item in inventory_items}

    # Quantity already submitted in prior restock orders, per SKU — subtracted
    # from the target so repeat visits don't recommend (and re-order) the same
    # shortfall that's already on its way.
    pending_by_sku = {}
    for order in restock_orders:
        for order_item in order["items"]:
            pending_by_sku[order_item["sku"]] = pending_by_sku.get(order_item["sku"], 0) + order_item["quantity"]

    candidates = []
    for forecast in demand_forecasts:
        inv = inventory_by_sku.get(forecast["item_sku"])
        if inv is None or forecast["trend"].lower() != "increasing":
            continue

        current = forecast["current_demand"]
        forecasted = forecast["forecasted_demand"]
        growth_percent = round((forecasted - current) / current * 100, 1) if current > 0 else 0.0

        is_urgent = inv["quantity_on_hand"] <= inv["reorder_point"]
        shortfall = max(0, inv["reorder_point"] - inv["quantity_on_hand"])
        growth_units = max(0, forecasted - current)
        pending = pending_by_sku.get(inv["sku"], 0)
        qty_target = shortfall + growth_units - pending
        if qty_target <= 0:
            continue  # already fully covered by outstanding restock orders

        candidates.append({
            "item_sku": inv["sku"],
            "item_name": inv["name"],
            "category": inv["category"],
            "warehouse": inv["warehouse"],
            "quantity_on_hand": inv["quantity_on_hand"],
            "reorder_point": inv["reorder_point"],
            "unit_cost": inv["unit_cost"],
            "current_demand": current,
            "forecasted_demand": forecasted,
            "trend": forecast["trend"],
            "is_urgent": is_urgent,
            "demand_growth_percent": growth_percent,
            "qty_target": qty_target,
        })

    urgent = sorted([c for c in candidates if c["is_urgent"]], key=lambda c: -c["demand_growth_percent"])
    others = sorted([c for c in candidates if not c["is_urgent"]], key=lambda c: -c["demand_growth_percent"])
    ranked = urgent + others

    remaining_budget = budget
    recommendations = []
    for c in ranked:
        if c["unit_cost"] > remaining_budget:
            continue  # can't afford even 1 unit — skip, keep scanning for a cheaper fit

        suggested_quantity = min(c["qty_target"], floor(remaining_budget / c["unit_cost"]))
        if suggested_quantity <= 0:
            continue

        estimated_cost = round(suggested_quantity * c["unit_cost"], 2)
        remaining_budget = round(remaining_budget - estimated_cost, 2)

        recommendations.append(RestockRecommendation(
            item_sku=c["item_sku"],
            item_name=c["item_name"],
            category=c["category"],
            warehouse=c["warehouse"],
            quantity_on_hand=c["quantity_on_hand"],
            reorder_point=c["reorder_point"],
            unit_cost=c["unit_cost"],
            current_demand=c["current_demand"],
            forecasted_demand=c["forecasted_demand"],
            trend=c["trend"],
            is_urgent=c["is_urgent"],
            demand_growth_percent=c["demand_growth_percent"],
            suggested_quantity=suggested_quantity,
            estimated_cost=estimated_cost,
        ))

    total_estimated_cost = round(budget - remaining_budget, 2)

    return RestockRecommendationsResponse(
        budget=budget,
        total_estimated_cost=total_estimated_cost,
        remaining_budget=remaining_budget,
        recommendations=recommendations,
    )

@app.post("/api/restock-orders", response_model=RestockOrder, status_code=201)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a restock order for the chosen items/quantities (direct submit)."""
    if not request.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    inventory_by_sku = {item["sku"]: item for item in inventory_items}

    # Merge duplicate SKUs in the request into a single line item instead of
    # creating separate lines for the same product.
    quantity_by_sku = {}
    for req_item in request.items:
        quantity_by_sku[req_item.sku] = quantity_by_sku.get(req_item.sku, 0) + req_item.quantity

    resolved_items = []
    for sku, quantity in quantity_by_sku.items():
        inv = inventory_by_sku.get(sku)
        if inv is None:
            raise HTTPException(status_code=404, detail=f"Item with sku '{sku}' not found in inventory")
        resolved_items.append({
            "sku": sku,
            "name": inv["name"],
            "quantity": quantity,
            "unit_cost": inv["unit_cost"],
        })

    total_value = round(sum(i["quantity"] * i["unit_cost"] for i in resolved_items), 2)
    now = datetime.now()
    order_date = now.isoformat(timespec="seconds")
    expected_delivery = (now + timedelta(days=RESTOCK_LEAD_TIME_DAYS)).isoformat(timespec="seconds")

    # Lock the read-modify-append so concurrent submissions can't compute the
    # same sequence number (sync endpoints run in a thread pool).
    with restock_orders_lock:
        seq = len(restock_orders) + 1
        order_id = str(uuid.uuid4())
        new_order = {
            "id": order_id,
            "order_number": f"RESTOCK-{now.year}-{seq:04d}",
            "items": resolved_items,
            "status": "Placed",
            "order_date": order_date,
            "lead_time_days": RESTOCK_LEAD_TIME_DAYS,
            "expected_delivery": expected_delivery,
            "total_value": total_value,
            "notes": request.notes,
        }
        restock_orders.append(new_order)
        return new_order

@app.get("/api/restock-orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Get all submitted restock orders"""
    return restock_orders

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
