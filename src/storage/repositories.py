"""
Repository pattern for database access
"""

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import User, Usage, Transaction

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for User model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID."""
        logger.debug(f"UserRepository.get_by_telegram_id(telegram_id={telegram_id})")
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        logger.debug(f"Result: {'found' if user else 'not found'}")
        return user

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by internal ID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        daily_quota_seconds: int = 60,
    ) -> User:
        """Create a new user."""
        logger.debug(
            f"UserRepository.create(telegram_id={telegram_id}, quota={daily_quota_seconds}s)"
        )
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            daily_quota_seconds=daily_quota_seconds,
            is_unlimited=False,
            today_usage_seconds=0,
            last_reset_date=date.today(),
            total_usage_seconds=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.session.add(user)
        await self.session.flush()
        logger.debug(f"User created: id={user.id}, telegram_id={telegram_id}")
        return user

    async def update_usage(self, user: User, duration_seconds: int) -> User:
        """Update user's usage statistics."""
        logger.debug(
            f"UserRepository.update_usage(user_id={user.id}, duration={duration_seconds}s)"
        )
        user.today_usage_seconds += duration_seconds
        user.total_usage_seconds += duration_seconds
        user.updated_at = datetime.utcnow()
        await self.session.flush()
        logger.debug(
            f"Usage updated: today={user.today_usage_seconds}s, total={user.total_usage_seconds}s"
        )
        return user

    async def reset_daily_quota(self, user: User) -> User:
        """Reset user's daily quota."""
        user.today_usage_seconds = 0
        user.last_reset_date = date.today()
        user.updated_at = datetime.utcnow()
        await self.session.flush()
        return user

    async def set_unlimited(self, user: User, is_unlimited: bool) -> User:
        """Set user's unlimited status."""
        user.is_unlimited = is_unlimited
        user.updated_at = datetime.utcnow()
        await self.session.flush()
        return user

    async def update_quota(self, user: User, new_quota_seconds: int) -> User:
        """Update user's daily quota limit."""
        user.daily_quota_seconds = new_quota_seconds
        user.updated_at = datetime.utcnow()
        await self.session.flush()
        return user


class UsageRepository:
    """Repository for Usage model operations with staged writes.

    Lifecycle stages:
    1. create() - Stage 1: Create record on file download
    2. update() - Stage 2: Update with duration after download
    3. update() - Stage 3: Update with transcription results and LLM model (if applicable)
    4. update() - Stage 4: Update with LLM processing time (hybrid mode only)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        voice_file_id: str,
        voice_duration_seconds: Optional[int] = None,
        model_size: Optional[str] = None,
        processing_time_seconds: Optional[float] = None,
        transcription_length: Optional[int] = None,
        language: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_processing_time_seconds: Optional[float] = None,
    ) -> Usage:
        """Create a new usage record (Stage 1: on file download).

        Minimal required fields: user_id, voice_file_id
        Other fields can be updated later via update()
        """
        logger.debug(f"UsageRepository.create(user_id={user_id}, file_id={voice_file_id})")
        usage = Usage(
            user_id=user_id,
            voice_file_id=voice_file_id,
            voice_duration_seconds=voice_duration_seconds,
            model_size=model_size,
            processing_time_seconds=processing_time_seconds,
            transcription_length=transcription_length,
            language=language,
            llm_model=llm_model,
            llm_processing_time_seconds=llm_processing_time_seconds,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.session.add(usage)
        await self.session.flush()
        await self.session.refresh(usage)  # Ensure all defaults are loaded
        logger.debug(f"Usage created: id={usage.id}")
        return usage

    async def get_by_id(self, usage_id: int) -> Optional[Usage]:
        """Get usage record by ID."""
        result = await self.session.execute(select(Usage).where(Usage.id == usage_id))
        return result.scalar_one_or_none()

    async def update(
        self,
        usage_id: int,
        voice_duration_seconds: Optional[int] = None,
        model_size: Optional[str] = None,
        processing_time_seconds: Optional[float] = None,
        transcription_length: Optional[int] = None,
        language: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_processing_time_seconds: Optional[float] = None,
    ) -> Usage:
        """Update usage record with new data (Stage 2, 3, or 4).

        Only updates provided fields. Returns updated usage record.
        """
        logger.debug(
            f"UsageRepository.update(usage_id={usage_id}, duration={voice_duration_seconds}, "
            f"model={model_size}, processing_time={processing_time_seconds}, "
            f"text_length={transcription_length}, llm_model={llm_model}, "
            f"llm_time={llm_processing_time_seconds})"
        )
        usage = await self.get_by_id(usage_id)
        if not usage:
            raise ValueError(f"Usage record {usage_id} not found")

        if voice_duration_seconds is not None:
            usage.voice_duration_seconds = voice_duration_seconds
        if model_size is not None:
            usage.model_size = model_size
        if processing_time_seconds is not None:
            usage.processing_time_seconds = processing_time_seconds
        if transcription_length is not None:
            usage.transcription_length = transcription_length
        if language is not None:
            usage.language = language
        if llm_model is not None:
            usage.llm_model = llm_model
        if llm_processing_time_seconds is not None:
            usage.llm_processing_time_seconds = llm_processing_time_seconds

        usage.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(usage)
        logger.debug(f"Usage updated: id={usage_id}")
        return usage

    async def get_by_user_id(self, user_id: int, limit: int = 10) -> list[Usage]:
        """Get usage records for a user (most recent first)."""
        result = await self.session.execute(
            select(Usage)
            .where(Usage.user_id == user_id)
            .order_by(Usage.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_user_total_duration(self, user_id: int) -> int:
        """Get total duration of all usage for a user (only completed records)."""
        result = await self.session.execute(select(Usage).where(Usage.user_id == user_id))
        usages = result.scalars().all()
        return sum(u.voice_duration_seconds or 0 for u in usages)


class TransactionRepository:
    """Repository for Transaction model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        amount: int,
        currency: str,
        quota_seconds_added: int,
        provider: Optional[str] = None,
        provider_transaction_id: Optional[str] = None,
    ) -> Transaction:
        """Create a new transaction record."""
        transaction = Transaction(
            user_id=user_id,
            amount=amount,
            currency=currency,
            quota_seconds_added=quota_seconds_added,
            status="pending",
            provider=provider,
            provider_transaction_id=provider_transaction_id,
            created_at=datetime.utcnow(),
        )
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def get_by_id(self, transaction_id: int) -> Optional[Transaction]:
        """Get transaction by ID."""
        result = await self.session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalar_one_or_none()

    async def mark_completed(self, transaction: Transaction) -> Transaction:
        """Mark transaction as completed."""
        transaction.status = "completed"
        transaction.completed_at = datetime.utcnow()
        await self.session.flush()
        return transaction

    async def mark_failed(self, transaction: Transaction) -> Transaction:
        """Mark transaction as failed."""
        transaction.status = "failed"
        transaction.completed_at = datetime.utcnow()
        await self.session.flush()
        return transaction

    async def get_by_user_id(self, user_id: int, limit: int = 10) -> list[Transaction]:
        """Get transactions for a user (most recent first)."""
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
