"""
Tests for restocking API endpoints.
"""
import pytest
from datetime import datetime


class TestRestockRecommendationsEndpoint:
    """Test suite for the restock recommendations endpoint."""

    def test_get_recommendations_requires_budget(self, client):
        """Test that omitting the budget query param returns a validation error."""
        response = client.get("/api/restock/recommendations")
        assert response.status_code == 422

    def test_get_recommendations_invalid_budget_type(self, client):
        """Test that a non-numeric budget returns a validation error."""
        response = client.get("/api/restock/recommendations?budget=abc")
        assert response.status_code == 422

    def test_get_recommendations_negative_budget(self, client):
        """Test that a negative budget is rejected."""
        response = client.get("/api/restock/recommendations?budget=-10")
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_get_all_recommendations_structure(self, client):
        """Test the full response structure for a large budget."""
        response = client.get("/api/restock/recommendations?budget=1000000")
        assert response.status_code == 200

        data = response.json()
        assert "budget" in data
        assert "total_estimated_cost" in data
        assert "remaining_budget" in data
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) > 0

        required_fields = [
            "item_sku", "item_name", "category", "warehouse",
            "quantity_on_hand", "reorder_point", "unit_cost",
            "current_demand", "forecasted_demand", "trend",
            "is_urgent", "demand_growth_percent",
            "suggested_quantity", "estimated_cost"
        ]
        first_item = data["recommendations"][0]
        for field in required_fields:
            assert field in first_item

    def test_recommendations_only_increasing_trend(self, client):
        """Test that only 'increasing' trend items are ever recommended."""
        response = client.get("/api/restock/recommendations?budget=1000000")
        data = response.json()

        skus = [item["item_sku"] for item in data["recommendations"]]
        assert "PSU-501" not in skus  # trend is "stable"
        assert "BRG-102" not in skus  # trend is "stable"

        for item in data["recommendations"]:
            assert item["trend"].lower() == "increasing"

    def test_recommendations_skip_unmatched_forecast_skus(self, client):
        """Test that forecast SKUs with no matching inventory item are excluded."""
        response = client.get("/api/restock/recommendations?budget=1000000")
        data = response.json()

        skus = [item["item_sku"] for item in data["recommendations"]]
        # These forecast SKUs (WDG-001, GSK-203, FLT-405) have no inventory match
        assert "WDG-001" not in skus
        assert "GSK-203" not in skus
        assert "FLT-405" not in skus

    def test_recommendations_urgency_first_ordering(self, client):
        """Test that all urgent items are ranked ahead of non-urgent items."""
        response = client.get("/api/restock/recommendations?budget=1000000")
        data = response.json()

        urgent_flags = [item["is_urgent"] for item in data["recommendations"]]
        first_false_index = next(
            (i for i, urgent in enumerate(urgent_flags) if not urgent), None
        )
        if first_false_index is not None:
            assert all(urgent_flags[i] for i in range(first_false_index))
            assert not any(urgent_flags[first_false_index:])

    def test_recommendations_is_urgent_matches_inventory(self, client):
        """Test that is_urgent is consistent with live inventory reorder_point data."""
        recs_response = client.get("/api/restock/recommendations?budget=1000000")
        recommendations = recs_response.json()["recommendations"]

        inventory_response = client.get("/api/inventory")
        inventory_by_sku = {item["sku"]: item for item in inventory_response.json()}

        for item in recommendations:
            inv = inventory_by_sku[item["item_sku"]]
            expected_urgent = inv["quantity_on_hand"] <= inv["reorder_point"]
            assert item["is_urgent"] == expected_urgent

    def test_recommendations_budget_zero(self, client):
        """Test that a budget of 0 returns no recommendations."""
        response = client.get("/api/restock/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["recommendations"] == []
        assert data["total_estimated_cost"] == 0
        assert data["remaining_budget"] == 0

    def test_recommendations_estimated_cost_and_budget_calculation(self, client):
        """Test that estimated_cost, total_estimated_cost and remaining_budget are consistent."""
        budget = 5000
        response = client.get(f"/api/restock/recommendations?budget={budget}")
        data = response.json()

        calculated_total = 0
        for item in data["recommendations"]:
            expected_cost = round(item["suggested_quantity"] * item["unit_cost"], 2)
            assert abs(item["estimated_cost"] - expected_cost) < 0.01
            calculated_total += item["estimated_cost"]

        assert abs(data["total_estimated_cost"] - calculated_total) < 0.01
        assert abs(data["remaining_budget"] - (budget - data["total_estimated_cost"])) < 0.01
        assert data["total_estimated_cost"] <= budget

    def test_recommendations_large_budget_bounded_by_candidates(self, client):
        """Test that an unbounded budget doesn't fabricate more items than qualify."""
        small_budget_response = client.get("/api/restock/recommendations?budget=1000000")
        huge_budget_response = client.get("/api/restock/recommendations?budget=100000000")

        small_count = len(small_budget_response.json()["recommendations"])
        huge_count = len(huge_budget_response.json()["recommendations"])
        assert huge_count == small_count


class TestRestockOrdersEndpoints:
    """Test suite for the restock orders create/list endpoints."""

    def test_get_restock_orders_returns_list(self, client):
        """Test that listing restock orders returns a list."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_restock_order_success(self, client):
        """Test successfully submitting a restock order."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "TMP-201", "quantity": 50}]
        })
        assert response.status_code == 201

        order = response.json()
        assert "id" in order
        assert order["order_number"].startswith("RESTOCK-")
        assert order["status"] == "Placed"
        assert order["lead_time_days"] == 10
        assert len(order["items"]) == 1
        assert order["items"][0]["sku"] == "TMP-201"
        assert order["items"][0]["quantity"] == 50

    def test_create_restock_order_expected_delivery_matches_lead_time(self, client):
        """Test that expected_delivery is exactly lead_time_days after order_date."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "SRV-301", "quantity": 5}]
        })
        order = response.json()

        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert (expected_delivery - order_date).days == order["lead_time_days"]

    def test_create_restock_order_unknown_sku_404(self, client):
        """Test that an unknown SKU returns 404."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "NON-EXISTENT-SKU", "quantity": 5}]
        })
        assert response.status_code == 404

        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_create_restock_order_empty_items_400(self, client):
        """Test that an empty items list is rejected."""
        response = client.post("/api/restock-orders", json={"items": []})
        assert response.status_code == 400

    def test_create_restock_order_invalid_quantity_422(self, client):
        """Test that a non-positive quantity is rejected by validation."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "TMP-201", "quantity": 0}]
        })
        assert response.status_code == 422

    def test_restock_order_total_value_calculation(self, client):
        """Test that total_value matches sum(quantity * unit_cost) for resolved items."""
        response = client.post("/api/restock-orders", json={
            "items": [
                {"sku": "PCB-001", "quantity": 10},
                {"sku": "MCU-401", "quantity": 20},
            ]
        })
        order = response.json()

        calculated_total = sum(
            item["quantity"] * item["unit_cost"] for item in order["items"]
        )
        assert abs(order["total_value"] - calculated_total) < 0.01

    def test_restock_order_fields_structure(self, client):
        """Test that a created restock order has all required fields."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "PSU-508", "quantity": 5}]
        })
        order = response.json()

        required_fields = [
            "id", "order_number", "items", "status", "order_date",
            "expected_delivery", "total_value", "lead_time_days"
        ]
        for field in required_fields:
            assert field in order

    def test_create_then_get_round_trip(self, client):
        """Test that a submitted order shows up in the subsequent GET list."""
        create_response = client.post("/api/restock-orders", json={
            "items": [{"sku": "TMP-201", "quantity": 15}]
        })
        created_order = create_response.json()

        list_response = client.get("/api/restock-orders")
        all_orders = list_response.json()

        matching = [o for o in all_orders if o["id"] == created_order["id"]]
        assert len(matching) == 1
        assert matching[0]["total_value"] == created_order["total_value"]

    def test_create_restock_order_merges_duplicate_skus(self, client):
        """Test that duplicate SKUs in one request are merged into a single line item."""
        response = client.post("/api/restock-orders", json={
            "items": [
                {"sku": "PSU-508", "quantity": 5},
                {"sku": "PSU-508", "quantity": 3},
            ]
        })
        order = response.json()

        matching_lines = [item for item in order["items"] if item["sku"] == "PSU-508"]
        assert len(matching_lines) == 1
        assert matching_lines[0]["quantity"] == 8

    def test_submitted_order_reduces_future_recommendations(self, client):
        """Test that placing a restock order lowers (or removes) that SKU's future
        suggested_quantity, so repeated submissions don't keep recommending the
        same already-ordered shortfall."""
        before_response = client.get("/api/restock/recommendations?budget=1000000")
        before = {
            item["item_sku"]: item["suggested_quantity"]
            for item in before_response.json()["recommendations"]
        }
        assert "SRV-301" in before

        # Order enough to fully cover SRV-301's outstanding shortfall/growth target.
        client.post("/api/restock-orders", json={
            "items": [{"sku": "SRV-301", "quantity": before["SRV-301"]}]
        })

        after_response = client.get("/api/restock/recommendations?budget=1000000")
        after = {
            item["item_sku"]: item["suggested_quantity"]
            for item in after_response.json()["recommendations"]
        }

        # Fully covered now, so it should no longer be recommended at all.
        assert "SRV-301" not in after
