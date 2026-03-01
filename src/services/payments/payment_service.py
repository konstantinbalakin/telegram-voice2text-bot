"""
Payment Service - routes payments to appropriate providers, handles callbacks.
"""

import logging
from typing import Optional

from src.services.payments.base import (
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    PaymentType,
)
from src.storage.billing_repositories import (
    PurchaseRepository,
    SubscriptionRepository,
    UserMinuteBalanceRepository,
    MinutePackageRepository,
)
from src.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class PaymentService:
    """Routes payments to providers and handles post-payment logic."""

    def __init__(
        self,
        purchase_repo: PurchaseRepository,
        subscription_repo: SubscriptionRepository,
        balance_repo: UserMinuteBalanceRepository,
        package_repo: MinutePackageRepository,
        subscription_service: SubscriptionService,
    ):
        self.purchase_repo = purchase_repo
        self.subscription_repo = subscription_repo
        self.balance_repo = balance_repo
        self.package_repo = package_repo
        self.subscription_service = subscription_service
        self._providers: dict[str, PaymentProvider] = {}

    def register_provider(self, provider: PaymentProvider) -> None:
        """Register a payment provider."""
        self._providers[provider.provider_name] = provider
        logger.info(f"Registered payment provider: {provider.provider_name}")

    def get_provider(self, name: str) -> Optional[PaymentProvider]:
        """Get a registered payment provider by name."""
        return self._providers.get(name)

    @property
    def available_providers(self) -> list[str]:
        """List of registered provider names."""
        return list(self._providers.keys())

    async def create_payment(
        self,
        provider_name: str,
        request: PaymentRequest,
    ) -> PaymentResult:
        """Create a payment via the specified provider."""
        provider = self.get_provider(provider_name)
        if not provider:
            return PaymentResult(
                success=False,
                error_message=f"Unknown payment provider: {provider_name}",
            )

        # Create purchase record
        purchase = await self.purchase_repo.create(
            user_id=request.user_id,
            purchase_type=request.payment_type.value,
            item_id=request.item_id,
            amount=request.amount,
            currency=request.currency,
            payment_provider=provider_name,
        )

        # Create payment with provider
        result = await provider.create_payment(request)

        if not result.success:
            await self.purchase_repo.mark_failed(purchase)
            logger.warning(
                f"Payment creation failed for user {request.user_id}: {result.error_message}"
            )

        return result

    async def handle_successful_payment(
        self,
        provider_name: str,
        user_id: int,
        payment_type: PaymentType,
        item_id: int,
        provider_transaction_id: Optional[str] = None,
    ) -> bool:
        """Handle a successful payment: credit minutes or activate subscription."""
        if payment_type == PaymentType.PACKAGE:
            return await self._credit_package(user_id=user_id, package_id=item_id)
        elif payment_type == PaymentType.SUBSCRIPTION:
            return await self._activate_subscription(
                user_id=user_id,
                tier_id=item_id,
                payment_provider=provider_name,
            )
        return False

    async def _credit_package(self, user_id: int, package_id: int) -> bool:
        """Credit minute package to user."""
        package = await self.package_repo.get_by_id(package_id)
        if not package:
            logger.error(f"Package {package_id} not found")
            return False

        await self.balance_repo.create(
            user_id=user_id,
            balance_type="package",
            minutes_remaining=package.minutes,
            source_description=f"Package: {package.name}",
        )

        logger.info(f"Credited {package.minutes} min to user {user_id} (package {package.name})")
        return True

    async def _activate_subscription(
        self, user_id: int, tier_id: int, payment_provider: str
    ) -> bool:
        """Activate subscription for user."""
        await self.subscription_service.create_subscription(
            user_id=user_id,
            tier_id=tier_id,
            period="month",
            payment_provider=payment_provider,
        )

        logger.info(f"Activated subscription tier {tier_id} for user {user_id}")
        return True
