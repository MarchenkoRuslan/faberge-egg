import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.fraction_transfer import FractionTransfer


class TestProvenanceEndpoint:
    def test_provenance_empty(self, client: TestClient, test_asset):
        resp = client.get(f"/api/assets/{test_asset.slug}/provenance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["asset_slug"] == test_asset.slug
        assert data["total"] == 0
        assert data["items"] == []

    def test_provenance_not_found(self, client: TestClient):
        resp = client.get("/api/assets/nonexistent/provenance")
        assert resp.status_code == 404

    def test_provenance_with_transfer(
        self, client: TestClient, test_asset, test_user, test_fraction_transfer,
    ):
        resp = client.get(f"/api/assets/{test_asset.slug}/provenance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["transfer_type"] == "purchase"
        assert item["fraction_count"] == 100
        assert item["from_display"] is None
        assert item["to_display"] == test_user.display_name
        assert item["blockchain_tx_hash"] == "0xdeadbeef"
        assert item["blockchain_status"] == "confirmed"

    def test_provenance_with_wallet_display(
        self, client: TestClient, db: Session,
        test_asset, test_user, test_wallet, test_fraction_transfer,
    ):
        resp = client.get(f"/api/assets/{test_asset.slug}/provenance")
        assert resp.status_code == 200
        data = resp.json()
        item = data["items"][0]
        assert item["to_display"] == test_user.display_name

    def test_provenance_pagination(
        self, client: TestClient, db: Session, test_asset, test_user,
    ):
        for i in range(5):
            transfer = FractionTransfer(
                asset_id=test_asset.id,
                from_user_id=None,
                to_user_id=test_user.id,
                fraction_count=10 + i,
                transfer_type="purchase",
                blockchain_status="confirmed",
            )
            db.add(transfer)
        db.commit()

        resp = client.get(
            f"/api/assets/{test_asset.slug}/provenance",
            params={"limit": 2, "offset": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

        resp2 = client.get(
            f"/api/assets/{test_asset.slug}/provenance",
            params={"limit": 2, "offset": 2},
        )
        data2 = resp2.json()
        assert len(data2["items"]) == 2

        resp3 = client.get(
            f"/api/assets/{test_asset.slug}/provenance",
            params={"limit": 2, "offset": 4},
        )
        data3 = resp3.json()
        assert len(data3["items"]) == 1

    def test_provenance_order_newest_first(
        self, client: TestClient, db: Session, test_asset, test_user,
    ):
        for i in range(3):
            transfer = FractionTransfer(
                asset_id=test_asset.id,
                from_user_id=None,
                to_user_id=test_user.id,
                fraction_count=100 * (i + 1),
                transfer_type="purchase",
                blockchain_status="confirmed",
            )
            db.add(transfer)
            db.flush()
        db.commit()

        resp = client.get(f"/api/assets/{test_asset.slug}/provenance")
        data = resp.json()
        counts = [item["fraction_count"] for item in data["items"]]
        assert counts == [300, 200, 100]

    def test_provenance_user_no_name_shows_wallet_address(
        self, client: TestClient, db: Session, test_asset, test_wallet,
    ):
        from app.models.user import User
        user = db.query(User).filter(User.id == test_wallet.user_id).first()
        user.display_name = None
        db.commit()

        transfer = FractionTransfer(
            asset_id=test_asset.id,
            from_user_id=None,
            to_user_id=user.id,
            fraction_count=50,
            transfer_type="purchase",
            blockchain_status="pending",
        )
        db.add(transfer)
        db.commit()

        resp = client.get(f"/api/assets/{test_asset.slug}/provenance")
        data = resp.json()
        item = data["items"][0]
        assert "0xaabb" in item["to_display"]
        assert "..." in item["to_display"]
