"""
Payment Service - routes payments to appropriate providers, handles callbacks.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Optional

from src.services.payments.base import (
    BalanceType,
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

# Type alias for session factory (e.g. database.get_session)
SessionFactory = Callable[..., Any]


class PaymentService:
    """Routes payments to providers and handles post-payment logic.

    Accepts either a session_factory (production) or pre-built repos (testing).
    """

    def __init__(
        self,
        *,
        session_factory: Optional[SessionFactory] = None,
        purchase_repo: Optional[PurchaseRepository] = None,
        subscription_repo: Optional[SubscriptionRepository] = None,
        balance_repo: Optional[UserMinuteBalanceRepository] = None,
        package_repo: Optional[MinutePackageRepository] = None,
        subscription_service: Optional[SubscriptionService] = None,
    ):
        self._session_factory = session_factory
        self._purchase_repo = purchase_repo
        self._subscription_repo = subscription_repo
        self._balance_repo = balance_repo
        self._package_repo = package_repo
        self.subscription_service = subscription_service
        self._providers: dict[str, PaymentProvider] = {}

    @asynccontextmanager
    async def _repos(
        self,
    ) -> AsyncGenerator[
        tuple[
            PurchaseRepository,
            SubscriptionRepository,
            UserMinuteBalanceRepository,
            MinutePackageRepository,
        ],
        None,
    ]:
        """Get repositories — per-request session or pre-built (tests)."""
        if self._session_factory:
            async with self._session_factory() as session:
                yield (
                    PurchaseRepository(session),
                    SubscriptionRepository(session),
                    UserMinuteBalanceRepository(session),
                    MinutePackageRepository(session),
                )
        else:
            assert self._purchase_repo is not None
            assert self._subscription_repo is not None
            assert self._balance_repo is not None
            assert self._package_repo is not None
            yield (
                self._purchase_repo,
                self._subscription_repo,
                self._balance_repo,
                self._package_repo,
            )

    async def get_active_packages(self) -> list:
        """Get all active minute packages."""
        async with self._repos() as (_, __, ___, package_repo):
            return await package_repo.get_active_packages()

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

        async with self._repos() as (purchase_repo, _, __, ___):
            # Store amount in rubles (Telegram sends RUB in kopecks)
            store_amount = request.amount / 100 if request.currency == "RUB" else request.amount

            # Create purchase record
            purchase = await purchase_repo.create(
                user_id=request.user_id,
                purchase_type=request.payment_type.value,
                item_id=request.item_id,
                amount=store_amount,
                currency=request.currency,
                payment_provider=provider_name,
            )

            # Create payment with provider
            result = await provider.create_payment(request)

            if not result.success:
                await purchase_repo.mark_failed(purchase)
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
        period: str = "month",
    ) -> bool:
        """Handle a successful payment: credit minutes or activate subscription.

        Finds the pending Purchase record by user_id + type + item_id and marks it completed.

        Args:
            provider_name: Payment provider identifier
            user_id: Internal DB user ID
            payment_type: PACKAGE or SUBSCRIPTION
            item_id: Package or tier ID
            provider_transaction_id: Provider-specific transaction ID
            period: Subscription period (week/month/year), only for SUBSCRIPTION
        """
        success = False
        if payment_type == PaymentType.PACKAGE:
            success = await self._credit_package(user_id=user_id, package_id=item_id)
        elif payment_type == PaymentType.SUBSCRIPTION:
            success = await self._activate_subscription(
                user_id=user_id,
                tier_id=item_id,
                payment_provider=provider_name,
                period=period,
            )

        # Find and mark pending purchase as completed
        if success:
            async with self._repos() as (purchase_repo, _, __, ___):
                purchase = await purchase_repo.find_pending_purchase(
                    user_id=user_id,
                    purchase_type=payment_type.value,
                    item_id=item_id,
                )
                if purchase:
                    purchase.provider_transaction_id = provider_transaction_id
                    await purchase_repo.mark_completed(purchase)
                    logger.info(f"Marked purchase {purchase.id} as completed")
                else:
                    logger.warning(
                        f"No pending purchase found for user {user_id}, "
                        f"type={payment_type.value}, item={item_id}"
                    )

        return success

    async def _credit_package(self, user_id: int, package_id: int) -> bool:
        """Credit minute package to user.

        Raises:
            ValueError: if package_id not found in database
        """
        async with self._repos() as (_, __, balance_repo, package_repo):
            package = await package_repo.get_by_id(package_id)
            if not package:
                raise ValueError(f"Package {package_id} not found")

            await balance_repo.create(
                user_id=user_id,
                balance_type=BalanceType.PACKAGE,
                minutes_remaining=package.minutes,
                source_description=f"Package: {package.name}",
            )

        logger.info(f"Credited {package.minutes} min to user {user_id} (package {package.name})")
        return True

    async def _activate_subscription(
        self, user_id: int, tier_id: int, payment_provider: str, period: str = "month"
    ) -> bool:
        """Activate subscription for user."""
        assert self.subscription_service is not None
        await self.subscription_service.create_subscription(
            user_id=user_id,
            tier_id=tier_id,
            period=period,
            payment_provider=payment_provider,
        )

        logger.info(f"Activated subscription tier {tier_id} for user {user_id}")
        return True
