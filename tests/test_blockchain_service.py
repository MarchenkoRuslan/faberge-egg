from app.services.blockchain_service import (
    BlockchainService,
    StubBlockchainService,
    TransferResult,
    WalletKeyPair,
    get_blockchain_service,
    reset_blockchain_service,
    set_blockchain_service,
)


class TestStubBlockchainService:
    def setup_method(self):
        self.svc = StubBlockchainService()

    def test_create_wallet_returns_keypair(self):
        result = self.svc.create_wallet()
        assert isinstance(result, WalletKeyPair)
        assert result.address.startswith("0x")
        assert len(result.address) == 42
        assert result.private_key.startswith("0x")

    def test_create_wallet_unique_addresses(self):
        w1 = self.svc.create_wallet()
        w2 = self.svc.create_wallet()
        assert w1.address != w2.address
        assert w1.private_key != w2.private_key

    def test_check_fraction_availability_available(self):
        assert self.svc.check_fraction_availability("contract_ref", 100, 200) is True

    def test_check_fraction_availability_exact(self):
        assert self.svc.check_fraction_availability("contract_ref", 200, 200) is True

    def test_check_fraction_availability_exceeded(self):
        assert self.svc.check_fraction_availability("contract_ref", 201, 200) is False

    def test_transfer_fractions_returns_result(self):
        result = self.svc.transfer_fractions("0xfrom", "0xto", "contract_ref", 50)
        assert isinstance(result, TransferResult)
        assert result.tx_hash.startswith("0x")
        assert result.status == "confirmed"

    def test_transfer_fractions_unique_tx_hash(self):
        r1 = self.svc.transfer_fractions("0xfrom", "0xto", "contract_ref", 50)
        r2 = self.svc.transfer_fractions("0xfrom", "0xto", "contract_ref", 50)
        assert r1.tx_hash != r2.tx_hash

    def test_get_transaction_status(self):
        assert self.svc.get_transaction_status("0xhash") == "confirmed"


class TestBlockchainServiceFactory:
    def setup_method(self):
        reset_blockchain_service()

    def teardown_method(self):
        reset_blockchain_service()

    def test_get_returns_stub_by_default(self):
        svc = get_blockchain_service()
        assert isinstance(svc, StubBlockchainService)

    def test_get_returns_same_instance(self):
        svc1 = get_blockchain_service()
        svc2 = get_blockchain_service()
        assert svc1 is svc2

    def test_set_overrides_service(self):
        custom = StubBlockchainService()
        set_blockchain_service(custom)
        assert get_blockchain_service() is custom

    def test_reset_clears_service(self):
        svc1 = get_blockchain_service()
        reset_blockchain_service()
        svc2 = get_blockchain_service()
        assert svc1 is not svc2

    def test_stub_satisfies_protocol(self):
        svc = StubBlockchainService()
        assert isinstance(svc, BlockchainService)
