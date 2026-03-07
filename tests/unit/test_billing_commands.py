"""
Tests for BillingCommands - catalog and balance display logic
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.billing_commands import BillingCommands


# === Helpers ===


def _make_billing_commands() -> tuple[BillingCommands, dict[str, AsyncMock]]:
    """Create BillingCommands with mocked services."""
    mocks = {
        "billing_service": AsyncMock(),
        "subscription_service": AsyncMock(),
        "payment_service": AsyncMock(),
    }

    commands = BillingCommands(
        billing_service=mocks["billing_service"],
        subscription_service=mocks["subscription_service"],
        payment_service=mocks["payment_service"],
    )

    return commands, mocks


def _mock_tier(tier_id: int = 1, name: str = "Pro", daily_limit: float = 30.0) -> MagicMock:
    tier = MagicMock()
    tier.id = tier_id
    tier.name = name
    tier.daily_limit_minutes = daily_limit
    tier.description = f"{name} subscription"
    return tier


def _mock_price(
    price_id: int = 1,
    tier_id: int = 1,
    period: str = "month",
    amount_rub: float = 299.0,
    amount_stars: int = 150,
    description: str | None = None,
) -> MagicMock:
    price = MagicMock()
    price.id = price_id
    price.tier_id = tier_id
    price.period = period
    price.amount_rub = amount_rub
    price.amount_stars = amount_stars
    price.description = description
    return price


def _mock_package(
    pkg_id: int = 1,
    name: str = "50 минут",
    minutes: float = 50.0,
    price_rub: float = 149.0,
    price_stars: int = 75,
    description: str | None = None,
) -> MagicMock:
    pkg = MagicMock()
    pkg.id = pkg_id
    pkg.name = name
    pkg.minutes = minutes
    pkg.price_rub = price_rub
    pkg.price_stars = price_stars
    pkg.description = description
    return pkg


def _mock_db_user(user_id: int = 42) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


# =============================================================================
# _build_subscriptions_catalog Tests
# =============================================================================


@pytest.mark.asyncio
@patch("src.bot.billing_commands.get_session")
async def test_build_subscriptions_catalog_passes_user_id(mock_get_session: MagicMock) -> None:
    """Test that _build_subscriptions_catalog resolves DB user_id and passes it."""
    commands, mocks = _make_billing_commands()

    # Setup DB user lookup
    mock_session = AsyncMock()
    mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

    db_user = _mock_db_user(user_id=42)

    with patch("src.bot.billing_commands.UserRepository") as mock_user_repo_cls:
        mock_user_repo_cls.return_value.get_by_telegram_id = AsyncMock(return_value=db_user)

        tier = _mock_tier(tier_id=1, name="Pro")
        mocks["subscription_service"].get_available_tiers.return_value = [tier]

        personal_price = _mock_price(price_id=10, amount_rub=199.0)
        mocks["subscription_service"].get_tier_prices.return_value = [personal_price]

        text, markup = await commands._build_subscriptions_catalog(telegram_user_id=100500)

    mocks["subscription_service"].get_tier_prices.assert_called_once_with(1, user_id=42)
    assert markup is not None
    # Price is in button text, not in body
    button_texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("199" in t for t in button_texts)


@pytest.mark.asyncio
async def test_build_subscriptions_catalog_without_user_id() -> None:
    """Test that _build_subscriptions_catalog works without telegram_user_id."""
    commands, mocks = _make_billing_commands()

    tier = _mock_tier(tier_id=1, name="Pro")
    mocks["subscription_service"].get_available_tiers.return_value = [tier]

    global_price = _mock_price(price_id=1, amount_rub=299.0)
    mocks["subscription_service"].get_tier_prices.return_value = [global_price]

    text, markup = await commands._build_subscriptions_catalog()

    mocks["subscription_service"].get_tier_prices.assert_called_once_with(1, user_id=None)
    assert markup is not None
    button_texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("299" in t for t in button_texts)


# =============================================================================
# _build_packages_catalog Tests
# =============================================================================


@pytest.mark.asyncio
@patch("src.bot.billing_commands.get_session")
async def test_build_packages_catalog_passes_user_id(mock_get_session: MagicMock) -> None:
    """Test that _build_packages_catalog resolves DB user_id and passes it."""
    commands, mocks = _make_billing_commands()

    mock_session = AsyncMock()
    mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

    db_user = _mock_db_user(user_id=42)

    with patch("src.bot.billing_commands.UserRepository") as mock_user_repo_cls:
        mock_user_repo_cls.return_value.get_by_telegram_id = AsyncMock(return_value=db_user)

        personal_pkg = _mock_package(pkg_id=10, name="VIP пакет", price_rub=99.0)
        mocks["payment_service"].get_active_packages.return_value = [personal_pkg]

        text, markup = await commands._build_packages_catalog(telegram_user_id=100500)

    mocks["payment_service"].get_active_packages.assert_called_once_with(user_id=42)
    assert "VIP пакет" in text
    assert "99" in text


@pytest.mark.asyncio
async def test_build_packages_catalog_without_user_id() -> None:
    """Test that _build_packages_catalog works without telegram_user_id."""
    commands, mocks = _make_billing_commands()

    global_pkg = _mock_package(pkg_id=1, name="50 минут", price_rub=149.0)
    mocks["payment_service"].get_active_packages.return_value = [global_pkg]

    text, markup = await commands._build_packages_catalog()

    mocks["payment_service"].get_active_packages.assert_called_once_with(user_id=None)
    assert "50 минут" in text
    assert "149" in text
