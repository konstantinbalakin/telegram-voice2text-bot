"""
Tests for Payment Service abstraction (Phase 7)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.payments.base import (
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    PaymentType,
)
from src.services.payments.payment_service import PaymentService


# === Helpers ===


def _mock_provider(name: str = "test_provider") -> MagicMock:
    """Create a mock payment provider."""
    provider = MagicMock(spec=PaymentProvider)
    provider.provider_name = name
    provider.create_payment = AsyncMock()
    provider.handle_callback = AsyncMock()
    provider.verify_payment = AsyncMock()
    return provider


def _make_payment_service() -> tuple[PaymentService, dict[str, AsyncMock]]:
    """Create PaymentService with mocked repos."""
    mocks = {
        "purchase_repo": AsyncMock(),
        "subscription_repo": AsyncMock(),
        "balance_repo": AsyncMock(),
        "package_repo": AsyncMock(),
        "subscription_service": AsyncMock(),
    }

    service = PaymentService(
        purchase_repo=mocks["purchase_repo"],
        subscription_repo=mocks["subscription_repo"],
        balance_repo=mocks["balance_repo"],
        package_repo=mocks["package_repo"],
        subscription_service=mocks["subscription_service"],
    )

    return service, mocks


# =============================================================================
# PaymentProvider Protocol Tests (Task 7.1)
# =============================================================================


def test_payment_provider_protocol_has_required_methods():
    """Test that PaymentProvider protocol defines required methods."""
    provider = _mock_provider()
    assert hasattr(provider, "provider_name")
    assert hasattr(provider, "create_payment")
    assert hasattr(provider, "handle_callback")
    assert hasattr(provider, "verify_payment")


def test_payment_request_creation():
    """Test PaymentRequest dataclass."""
    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=149.0,
        currency="RUB",
        description="50 minutes package",
    )
    assert request.user_id == 1
    assert request.payment_type == PaymentType.PACKAGE


def test_payment_result_success():
    """Test PaymentResult for success."""
    result = PaymentResult(success=True, provider_transaction_id="tx_123")
    assert result.success is True
    assert result.provider_transaction_id == "tx_123"


def test_payment_result_failure():
    """Test PaymentResult for failure."""
    result = PaymentResult(success=False, error_message="Insufficient funds")
    assert result.success is False
    assert result.error_message == "Insufficient funds"


# =============================================================================
# PaymentService Tests (Task 7.2)
# =============================================================================


def test_register_provider():
    """Test registering a payment provider."""
    service, _ = _make_payment_service()
    provider = _mock_provider("telegram_stars")

    service.register_provider(provider)
    assert "telegram_stars" in service.available_providers
    assert service.get_provider("telegram_stars") is provider


def test_get_unknown_provider():
    """Test getting an unknown provider returns None."""
    service, _ = _make_payment_service()
    assert service.get_provider("unknown") is None


@pytest.mark.asyncio
async def test_create_payment_success():
    """Test creating a payment via provider."""
    service, mocks = _make_payment_service()
    provider = _mock_provider("telegram_stars")
    provider.create_payment.return_value = PaymentResult(
        success=True, provider_transaction_id="tx_123"
    )
    service.register_provider(provider)

    mock_purchase = MagicMock()
    mock_purchase.id = 1
    mocks["purchase_repo"].create.return_value = mock_purchase

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=149.0,
        currency="RUB",
        description="50 minutes",
    )

    result = await service.create_payment("telegram_stars", request)
    assert result.success is True
    provider.create_payment.assert_called_once_with(request)
    mocks["purchase_repo"].create.assert_called_once()


@pytest.mark.asyncio
async def test_create_payment_unknown_provider():
    """Test creating payment with unknown provider."""
    service, _ = _make_payment_service()

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=149.0,
        currency="RUB",
        description="50 minutes",
    )

    result = await service.create_payment("unknown_provider", request)
    assert result.success is False
    assert "Unknown payment provider" in result.error_message


@pytest.mark.asyncio
async def test_create_payment_provider_fails():
    """Test handling provider failure."""
    service, mocks = _make_payment_service()
    provider = _mock_provider("telegram_stars")
    provider.create_payment.return_value = PaymentResult(
        success=False, error_message="Provider error"
    )
    service.register_provider(provider)

    mock_purchase = MagicMock()
    mocks["purchase_repo"].create.return_value = mock_purchase

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=149.0,
        currency="RUB",
        description="50 minutes",
    )

    result = await service.create_payment("telegram_stars", request)
    assert result.success is False
    mocks["purchase_repo"].mark_failed.assert_called_once_with(mock_purchase)


@pytest.mark.asyncio
async def test_handle_successful_package_payment():
    """Test crediting package after successful payment."""
    service, mocks = _make_payment_service()

    mocks["purchase_repo"].find_by_transaction_id = AsyncMock(return_value=None)

    mock_package = MagicMock()
    mock_package.id = 1
    mock_package.name = "50 минут"
    mock_package.minutes = 50.0
    mocks["package_repo"].get_by_id.return_value = mock_package

    mock_balance = MagicMock()
    mocks["balance_repo"].create.return_value = mock_balance

    success = await service.handle_successful_payment(
        provider_name="telegram_stars",
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
    )

    assert success is True
    mocks["balance_repo"].create.assert_called_once()
    call_kwargs = mocks["balance_repo"].create.call_args.kwargs
    assert call_kwargs["minutes_remaining"] == 50.0
    assert call_kwargs["balance_type"] == "package"


@pytest.mark.asyncio
async def test_handle_successful_subscription_payment():
    """Test activating subscription after successful payment."""
    service, mocks = _make_payment_service()

    mocks["purchase_repo"].find_by_transaction_id = AsyncMock(return_value=None)

    mock_sub = MagicMock()
    mocks["subscription_service"].create_subscription.return_value = mock_sub

    success = await service.handle_successful_payment(
        provider_name="telegram_stars",
        user_id=1,
        payment_type=PaymentType.SUBSCRIPTION,
        item_id=1,
    )

    assert success is True
    mocks["subscription_service"].create_subscription.assert_called_once()


@pytest.mark.asyncio
async def test_handle_successful_payment_package_not_found():
    """Test handling when package not found → returns False (error handled internally)."""
    service, mocks = _make_payment_service()
    mocks["package_repo"].get_by_id.return_value = None
    mocks["purchase_repo"].find_by_transaction_id = AsyncMock(return_value=None)
    mocks["purchase_repo"].find_pending_purchase = AsyncMock(return_value=None)

    result = await service.handle_successful_payment(
        provider_name="telegram_stars",
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=999,
    )

    assert result is False


def test_available_providers():
    """Test listing available providers."""
    service, _ = _make_payment_service()
    service.register_provider(_mock_provider("stars"))
    service.register_provider(_mock_provider("yookassa"))

    providers = service.available_providers
    assert len(providers) == 2
    assert "stars" in providers
    assert "yookassa" in providers


@pytest.mark.asyncio
async def test_create_payment_provider_exception_marks_purchase_failed():
    """Test: provider raises exception -> Purchase marked_failed."""
    service, mocks = _make_payment_service()
    provider = _mock_provider("telegram_stars")
    provider.create_payment.side_effect = RuntimeError("Network error")
    service.register_provider(provider)

    mock_purchase = MagicMock()
    mock_purchase.id = 1
    mocks["purchase_repo"].create.return_value = mock_purchase

    request = PaymentRequest(
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        amount=149.0,
        currency="RUB",
        description="50 minutes",
    )

    with pytest.raises(RuntimeError, match="Network error"):
        await service.create_payment("telegram_stars", request)

    mocks["purchase_repo"].create.assert_called_once()


# =============================================================================
# get_active_packages with user_id Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_active_packages_passes_user_id():
    """Test that get_active_packages passes user_id to get_effective_packages."""
    service, mocks = _make_payment_service()

    personal_pkg = MagicMock()
    personal_pkg.id = 10
    personal_pkg.name = "VIP пакет"
    personal_pkg.minutes = 100.0
    personal_pkg.price_rub = 99.0
    mocks["package_repo"].get_effective_packages.return_value = [personal_pkg]

    packages = await service.get_active_packages(user_id=42)
    assert len(packages) == 1
    assert packages[0].name == "VIP пакет"
    mocks["package_repo"].get_effective_packages.assert_called_once_with(user_id=42)


@pytest.mark.asyncio
async def test_get_active_packages_without_user_id():
    """Test that get_active_packages works without user_id (backward compat)."""
    service, mocks = _make_payment_service()

    global_pkg = MagicMock()
    global_pkg.id = 1
    global_pkg.name = "50 минут"
    global_pkg.minutes = 50.0
    mocks["package_repo"].get_effective_packages.return_value = [global_pkg]

    packages = await service.get_active_packages()
    assert len(packages) == 1
    mocks["package_repo"].get_effective_packages.assert_called_once_with(user_id=None)


# =============================================================================
# Phase 2: Idempotency, error handling, purchase FAILED
# =============================================================================


@pytest.mark.asyncio
async def test_handle_successful_payment_idempotent_by_transaction_id():
    """Task 2.1: duplicate transaction_id → no-op, returns True."""
    service, mocks = _make_payment_service()

    # Simulate already-completed purchase with this transaction_id
    existing_purchase = MagicMock()
    existing_purchase.id = 42
    existing_purchase.status = "completed"
    mocks["purchase_repo"].find_by_transaction_id = AsyncMock(return_value=existing_purchase)

    result = await service.handle_successful_payment(
        provider_name="telegram_stars",
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        provider_transaction_id="tx_duplicate_123",
    )

    assert result is True
    # Should NOT credit package again
    mocks["balance_repo"].create.assert_not_called()


@pytest.mark.asyncio
async def test_handle_successful_payment_credit_error_marks_failed():
    """Task 2.2: _credit_package raises → Purchase marked FAILED."""
    service, mocks = _make_payment_service()

    # No duplicate
    mocks["purchase_repo"].find_by_transaction_id = AsyncMock(return_value=None)
    # Package not found → ValueError
    mocks["package_repo"].get_by_id.return_value = None

    # find_pending_purchase returns a purchase to mark
    mock_purchase = MagicMock()
    mock_purchase.id = 1
    mocks["purchase_repo"].find_pending_purchase = AsyncMock(return_value=mock_purchase)

    result = await service.handle_successful_payment(
        provider_name="telegram_stars",
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=999,
        provider_transaction_id="tx_error_456",
    )

    assert result is False
    mocks["purchase_repo"].mark_failed.assert_called_once_with(mock_purchase)


@pytest.mark.asyncio
async def test_handle_successful_payment_purchase_not_found():
    """Task 2.3: handle_successful_payment when purchase not found still credits."""
    service, mocks = _make_payment_service()

    mocks["purchase_repo"].find_by_transaction_id = AsyncMock(return_value=None)

    mock_package = MagicMock()
    mock_package.id = 1
    mock_package.name = "50 минут"
    mock_package.minutes = 50.0
    mocks["package_repo"].get_by_id.return_value = mock_package

    # No pending purchase found
    mocks["purchase_repo"].find_pending_purchase = AsyncMock(return_value=None)

    result = await service.handle_successful_payment(
        provider_name="telegram_stars",
        user_id=1,
        payment_type=PaymentType.PACKAGE,
        item_id=1,
        provider_transaction_id="tx_orphan_789",
    )

    # Should still credit the package (payment went through)
    assert result is True
    mocks["balance_repo"].create.assert_called_once()
