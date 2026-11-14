"""PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and downloads."""

from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, Numeric, String, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from telegram import User as TelegramUser


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(32))
    is_bot: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_allowed: Mapped[bool] = mapped_column(default=False, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wallet_balance_toman: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')",
            name="ck_jobs_status",
        ),
        CheckConstraint("mode IN ('subtitle', 'dub')", name="ck_jobs_mode"),
        CheckConstraint("api_provider IN ('openai', 'openrouter')", name="ck_jobs_api_provider"),
        Index("ix_jobs_user_created", "telegram_user_id", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="RESTRICT"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(String(12), nullable=False, default="subtitle")
    api_provider: Mapped[str] = mapped_column(String(12), nullable=False, default="openai")
    selected_height: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    openai_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 8))
    subtitle_srt: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billable_minutes: Mapped[int | None] = mapped_column(nullable=True)
    billed_stars: Mapped[int | None] = mapped_column(nullable=True)
    payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billed_amount_toman: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wallet_refunded: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    package_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    package_minutes: Mapped[int | None] = mapped_column(nullable=True)


class MinutePackage(Base):
    __tablename__ = "minute_packages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    remaining_minutes: Mapped[int] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price_toman: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    glossary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class TeamMember(Base):
    __tablename__ = "team_members"
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(32), ForeignKey("teams.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class TeamInvite(Base):
    __tablename__ = "team_invites"
    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(32), ForeignKey("teams.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentOrder(Base):
    __tablename__ = "content_orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("jobs.id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    amount_toman: Mapped[int] = mapped_column(BigInteger, nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text)
    api_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ImageOrder(Base):
    __tablename__ = "image_orders"
    __table_args__ = (Index("ix_image_orders_user_created", "user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    reference_image: Mapped[bytes | None] = mapped_column(LargeBinary)
    reference_media_type: Mapped[str | None] = mapped_column(String(32))
    optimized_prompt: Mapped[str | None] = mapped_column(Text)
    aspect_ratio: Mapped[str] = mapped_column(String(8), nullable=False)
    provider: Mapped[str] = mapped_column(String(12), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    optimizer_provider: Mapped[str] = mapped_column(String(12), nullable=False)
    optimizer_model: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_toman: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    media_type: Mapped[str | None] = mapped_column(String(32))
    image_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 8))
    optimizer_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DownloadTask(Base):
    __tablename__ = "download_tasks"
    __table_args__ = (Index("ix_download_tasks_user_created", "user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    title: Mapped[str | None] = mapped_column(String(255))
    token: Mapped[str | None] = mapped_column(String(32))
    extension: Mapped[str | None] = mapped_column(String(4))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DownloadRecord(Base):
    __tablename__ = "downloads"
    __table_args__ = (
        Index("ix_downloads_expiry", "expires_at"),
        Index("ix_downloads_job", "job_id"),
    )

    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BotSetting(Base):
    __tablename__ = "bot_settings"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (Index("ix_payment_orders_user_created", "telegram_user_id", "created_at"),)

    payload: Mapped[str] = mapped_column(String(64), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    api_provider: Mapped[str] = mapped_column(String(12), nullable=False)
    selected_height: Mapped[int | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[int] = mapped_column(nullable=False)
    billable_minutes: Mapped[int] = mapped_column(nullable=False)
    amount_stars: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        CheckConstraint("amount_toman <> 0", name="ck_wallet_transactions_nonzero"),
        CheckConstraint(
            "entry_type IN ('card_transfer_deposit', 'admin_credit', 'admin_debit', 'job_charge', 'job_refund')",
            name="ck_wallet_transactions_type",
        ),
        Index("ix_wallet_transactions_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="RESTRICT"), nullable=False)
    amount_toman: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    deposit_request_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("card_transfer_requests.id", ondelete="RESTRICT"), nullable=True
    )
    admin_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CardTransferRequest(Base):
    __tablename__ = "card_transfer_requests"
    __table_args__ = (
        CheckConstraint("amount_toman > 0", name="ck_card_transfer_amount_positive"),
        CheckConstraint(
            "status IN ('awaiting_proof', 'pending_review', 'approved', 'rejected', 'cancelled')",
            name="ck_card_transfer_status",
        ),
        Index("ix_card_transfer_user_status", "user_id", "status"),
        Index("ix_card_transfer_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="RESTRICT"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_toman: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="awaiting_proof")
    proof_type: Mapped[str | None] = mapped_column(String(12), nullable=True)
    proof_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proof_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            # Forward-only additions for databases created by the previous bot version.
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS mode VARCHAR(12) NOT NULL DEFAULT 'subtitle'"
            ))
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS openai_cost_usd NUMERIC(12, 8)"
            ))
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS api_provider VARCHAR(12) NOT NULL DEFAULT 'openai'"
            ))
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS billable_minutes INTEGER"
            ))
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS billed_stars INTEGER"
            ))
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS payment_charge_id VARCHAR(255)"
            ))
            await connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ"
            ))
            await connection.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance_toman BIGINT NOT NULL DEFAULT 0"
            ))
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS billed_amount_toman BIGINT"
            ))
            await connection.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS wallet_refunded BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            await connection.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS package_id VARCHAR(32)"))
            await connection.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS package_minutes INTEGER"))
            await connection.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS title VARCHAR(255)"))
            await connection.execute(text("ALTER TABLE content_orders ADD COLUMN IF NOT EXISTS api_cost_usd NUMERIC(12, 8)"))
            await connection.execute(text("ALTER TABLE image_orders ADD COLUMN IF NOT EXISTS reference_image BYTEA"))
            await connection.execute(text("ALTER TABLE image_orders ADD COLUMN IF NOT EXISTS reference_media_type VARCHAR(32)"))
            # Move installations using the former bundled default prices to the new rates.
            # Custom rates configured by the admin are left untouched.
            await connection.execute(text(
                "UPDATE bot_settings SET value = '5000' "
                "WHERE name = 'price_subtitle_toman_per_minute' AND value = '10000'"
            ))
            await connection.execute(text(
                "UPDATE bot_settings SET value = '10000' "
                "WHERE name = 'price_dub_toman_per_minute' AND value = '25000'"
            ))
        # The queue is intentionally in-memory; mark work lost during a restart.
        async with self.sessions.begin() as session:
            now = datetime.now(UTC)
            await session.execute(
                JobRecord.__table__.update()
                .where(JobRecord.status.in_(("queued", "running")))
                .values(status="interrupted", finished_at=now)
            )
            await session.execute(DownloadTask.__table__.update()
                .where(DownloadTask.status.in_(("queued", "running"))).values(status="interrupted"))
            # Stop historical Stars invoices; a handler refunds any late successful old payment.
            await session.execute(
                PaymentOrder.__table__.update()
                .where(PaymentOrder.status == "pending")
                .values(status="cancelled")
            )

    async def upsert_user(self, user: TelegramUser, allowed: bool) -> None:
        now = datetime.now(UTC)
        async with self.sessions.begin() as session:
            record = await session.get(User, user.id)
            if record is None:
                record = User(telegram_id=user.id, first_seen_at=now)
                session.add(record)
            record.username = user.username
            record.first_name = user.first_name
            record.last_name = user.last_name
            record.language_code = user.language_code
            record.is_bot = user.is_bot
            record.is_allowed = allowed
            record.last_seen_at = now

    async def create_job(
        self, job_id: str, user_id: int, chat_id: int, url: str,
        selected_height: int | None, mode: str, api_provider: str,
    ) -> None:
        async with self.sessions.begin() as session:
            session.add(
                JobRecord(
                    id=job_id,
                    telegram_user_id=user_id,
                    chat_id=chat_id,
                    source_url=url,
                    mode=mode,
                    api_provider=api_provider,
                    selected_height=selected_height,
                    status="queued",
                )
            )

    async def get_setting(self, name: str, default: str) -> str:
        async with self.sessions() as session:
            setting = await session.get(BotSetting, name)
            return setting.value if setting else default

    async def set_setting(self, name: str, value: str) -> None:
        async with self.sessions.begin() as session:
            setting = await session.get(BotSetting, name)
            if setting is None:
                session.add(BotSetting(name=name, value=value))
            else:
                setting.value = value

    async def accept_terms(self, user_id: int) -> None:
        async with self.sessions.begin() as session:
            record = await session.get(User, user_id)
            if record:
                record.terms_accepted_at = datetime.now(UTC)

    async def has_accepted_terms(self, user_id: int) -> bool:
        async with self.sessions() as session:
            record = await session.get(User, user_id)
            return bool(record and record.terms_accepted_at)

    async def get_wallet_balance(self, user_id: int) -> int:
        async with self.sessions() as session:
            value = await session.scalar(select(User.wallet_balance_toman).where(User.telegram_id == user_id))
            return int(value or 0)

    async def wallet_history(self, user_id: int, limit: int = 10) -> list[dict]:
        async with self.sessions() as session:
            rows = (await session.scalars(
                select(WalletTransaction).where(WalletTransaction.user_id == user_id)
                .order_by(WalletTransaction.created_at.desc()).limit(limit)
            )).all()
            return [{
                "amount_toman": row.amount_toman,
                "entry_type": row.entry_type,
                "memo": row.memo or "",
                "created_at": row.created_at,
            } for row in rows]

    async def user_admin_summary(self, user_id: int, limit: int = 8) -> dict | None:
        async with self.sessions() as session:
            user = await session.get(User, user_id)
            if not user:
                return None
            job_count = await session.scalar(
                select(func.count()).select_from(JobRecord).where(JobRecord.telegram_user_id == user_id)
            ) or 0
            completed = await session.scalar(
                select(func.count()).select_from(JobRecord).where(
                    JobRecord.telegram_user_id == user_id, JobRecord.status == "completed"
                )
            ) or 0
            total_deposited = await session.scalar(select(func.coalesce(
                func.sum(WalletTransaction.amount_toman), 0
            )).where(
                WalletTransaction.user_id == user_id,
                WalletTransaction.entry_type.in_(("card_transfer_deposit", "admin_credit")),
            )) or 0
            jobs = (await session.scalars(
                select(JobRecord).where(JobRecord.telegram_user_id == user_id)
                .order_by(JobRecord.created_at.desc()).limit(limit)
            )).all()
            return {
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_seen_at": user.last_seen_at,
                "wallet_balance_toman": user.wallet_balance_toman,
                "total_deposited_toman": int(total_deposited),
                "jobs": int(job_count),
                "completed": int(completed),
                "recent_jobs": [{
                    "created_at": job.created_at, "status": job.status,
                    "mode": job.mode, "minutes": job.billable_minutes,
                    "amount_toman": job.billed_amount_toman,
                } for job in jobs],
            }

    async def create_deposit_request(
        self, request_id: str, user_id: int, chat_id: int, amount_toman: int
    ) -> bool:
        async with self.sessions.begin() as session:
            user = await session.scalar(
                select(User).where(User.telegram_id == user_id).with_for_update()
            )
            if not user:
                return False
            existing = await session.scalar(
                select(CardTransferRequest.id).where(
                    CardTransferRequest.user_id == user_id,
                    CardTransferRequest.status.in_(("awaiting_proof", "pending_review")),
                ).limit(1)
            )
            if existing:
                return False
            session.add(CardTransferRequest(
                id=request_id, user_id=user_id, chat_id=chat_id,
                amount_toman=amount_toman, status="awaiting_proof",
            ))
            return True

    async def get_user_pending_deposit(self, user_id: int) -> dict | None:
        async with self.sessions() as session:
            request = await session.scalar(
                select(CardTransferRequest).where(
                    CardTransferRequest.user_id == user_id,
                    CardTransferRequest.status.in_(("awaiting_proof", "pending_review")),
                ).order_by(CardTransferRequest.created_at.desc()).limit(1)
            )
            if not request:
                return None
            return {
                "id": request.id, "amount_toman": request.amount_toman,
                "status": request.status, "chat_id": request.chat_id,
            }

    async def submit_deposit_proof(
        self, request_id: str, user_id: int, proof_type: str,
        proof_text: str | None = None, proof_file_id: str | None = None,
    ) -> dict | None:
        async with self.sessions.begin() as session:
            request = await session.scalar(
                select(CardTransferRequest).where(CardTransferRequest.id == request_id).with_for_update()
            )
            if not request or request.user_id != user_id or request.status != "awaiting_proof":
                return None
            request.proof_type = proof_type
            request.proof_text = proof_text[:2000] if proof_text else None
            request.proof_file_id = proof_file_id
            request.status = "pending_review"
            request.submitted_at = datetime.now(UTC)
            return {
                "id": request.id, "user_id": request.user_id,
                "chat_id": request.chat_id, "amount_toman": request.amount_toman,
                "proof_type": request.proof_type, "proof_text": request.proof_text,
                "proof_file_id": request.proof_file_id,
            }

    async def get_deposit_request(self, request_id: str) -> dict | None:
        async with self.sessions() as session:
            request = await session.get(CardTransferRequest, request_id)
            if not request:
                return None
            return {
                "id": request.id, "user_id": request.user_id,
                "chat_id": request.chat_id, "amount_toman": request.amount_toman,
                "status": request.status, "proof_type": request.proof_type,
                "proof_text": request.proof_text, "proof_file_id": request.proof_file_id,
            }

    async def list_pending_deposits(self, limit: int = 20) -> list[dict]:
        async with self.sessions() as session:
            rows = (await session.execute(
                select(CardTransferRequest, User.username)
                .join(User, User.telegram_id == CardTransferRequest.user_id)
                .where(CardTransferRequest.status == "pending_review")
                .order_by(CardTransferRequest.created_at.asc()).limit(limit)
            )).all()
            return [{
                "id": request.id, "user_id": request.user_id,
                "chat_id": request.chat_id, "amount_toman": request.amount_toman,
                "proof_type": request.proof_type, "proof_text": request.proof_text,
                "proof_file_id": request.proof_file_id, "username": username,
            } for request, username in rows]

    async def approve_deposit(self, request_id: str, admin_id: int) -> dict | None:
        async with self.sessions.begin() as session:
            request = await session.scalar(
                select(CardTransferRequest).where(CardTransferRequest.id == request_id).with_for_update()
            )
            if not request or request.status != "pending_review":
                return None
            user = await session.scalar(
                select(User).where(User.telegram_id == request.user_id).with_for_update()
            )
            if not user:
                return None
            user.wallet_balance_toman += request.amount_toman
            request.status = "approved"
            request.reviewed_at = datetime.now(UTC)
            request.reviewed_by = admin_id
            session.add(WalletTransaction(
                id=uuid.uuid4().hex, user_id=user.telegram_id,
                amount_toman=request.amount_toman, entry_type="card_transfer_deposit",
                deposit_request_id=request.id, admin_user_id=admin_id,
                memo="واریز کارت‌به‌کارت تأییدشده",
            ))
            return {
                "user_id": user.telegram_id, "chat_id": request.chat_id,
                "amount_toman": request.amount_toman,
                "balance_toman": user.wallet_balance_toman,
            }

    async def reject_deposit(self, request_id: str, admin_id: int) -> dict | None:
        async with self.sessions.begin() as session:
            request = await session.scalar(
                select(CardTransferRequest).where(CardTransferRequest.id == request_id).with_for_update()
            )
            if not request or request.status != "pending_review":
                return None
            request.status = "rejected"
            request.reviewed_at = datetime.now(UTC)
            request.reviewed_by = admin_id
            return {
                "user_id": request.user_id, "chat_id": request.chat_id,
                "amount_toman": request.amount_toman,
            }

    async def cancel_deposit_request(self, request_id: str, user_id: int) -> bool:
        async with self.sessions.begin() as session:
            request = await session.scalar(
                select(CardTransferRequest).where(CardTransferRequest.id == request_id).with_for_update()
            )
            if not request or request.user_id != user_id or request.status != "awaiting_proof":
                return False
            request.status = "cancelled"
            request.reviewed_at = datetime.now(UTC)
            return True

    async def direct_wallet_adjustment(
        self, user_id: int, amount_toman: int, admin_id: int, *, credit: bool, memo: str = ""
    ) -> int | None:
        if amount_toman <= 0:
            return None
        async with self.sessions.begin() as session:
            user = await session.scalar(
                select(User).where(User.telegram_id == user_id).with_for_update()
            )
            if not user:
                user = User(telegram_id=user_id, is_allowed=True, wallet_balance_toman=0)
                session.add(user)
                await session.flush()
            delta = amount_toman if credit else -amount_toman
            if not credit and user.wallet_balance_toman < amount_toman:
                return None
            user.wallet_balance_toman += delta
            session.add(WalletTransaction(
                id=uuid.uuid4().hex, user_id=user_id, amount_toman=delta,
                entry_type="admin_credit" if credit else "admin_debit",
                admin_user_id=admin_id, memo=memo[:1000] or "تنظیم موجودی توسط مدیر",
            ))
            return user.wallet_balance_toman

    async def purchase_minutes(self, user_id: int, mode: str, minutes: int, price: int, days: int) -> str:
        if mode not in {"subtitle", "dub"} or not 1 <= minutes <= 10000 or not 1 <= price <= 1_000_000_000 or not 1 <= days <= 365:
            return "invalid"
        async with self.sessions.begin() as session:
            user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
            if not user or user.wallet_balance_toman < price:
                return "balance"
            user.wallet_balance_toman -= price
            package_id = uuid.uuid4().hex
            session.add(MinutePackage(id=package_id, user_id=user_id, mode=mode, remaining_minutes=minutes,
                                      expires_at=datetime.now(UTC) + timedelta(days=days), price_toman=price))
            session.add(WalletTransaction(id=uuid.uuid4().hex, user_id=user_id, amount_toman=-price,
                entry_type="job_charge", memo=f"خرید بسته {minutes} دقیقه‌ای {mode} ({package_id})"))
            return "purchased"

    async def available_minutes(self, user_id: int) -> list[dict]:
        async with self.sessions() as session:
            packages = (await session.scalars(select(MinutePackage).where(MinutePackage.user_id == user_id,
                MinutePackage.remaining_minutes > 0, MinutePackage.expires_at > datetime.now(UTC))
                .order_by(MinutePackage.expires_at))).all()
            return [{"id": p.id, "mode": p.mode, "minutes": p.remaining_minutes, "expires_at": p.expires_at} for p in packages]

    async def create_package_job(self, job_id: str, user_id: int, chat_id: int, url: str,
                                 selected_height: int | None, mode: str, api_provider: str,
                                 billable_minutes: int, package_id: str,
                                 title: str | None = None) -> int | None:
        if billable_minutes < 1:
            return None
        async with self.sessions.begin() as session:
            user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
            package = await session.scalar(select(MinutePackage).where(MinutePackage.id == package_id,
                MinutePackage.user_id == user_id).with_for_update())
            if not user or not package or package.mode != mode or package.expires_at <= datetime.now(UTC) or package.remaining_minutes < billable_minutes:
                return None
            package.remaining_minutes -= billable_minutes
            session.add(JobRecord(id=job_id, telegram_user_id=user_id, chat_id=chat_id,
                source_url=url, title=title[:255] if title else None,
                mode=mode, api_provider=api_provider, selected_height=selected_height,
                status="queued", billable_minutes=billable_minutes, billed_amount_toman=0,
                package_id=package.id, package_minutes=billable_minutes))
            return package.remaining_minutes

    async def create_team(self, owner_id: int, name: str) -> str | None:
        async with self.sessions.begin() as session:
            user = await session.scalar(select(User).where(User.telegram_id == owner_id).with_for_update())
            if not user or await session.get(TeamMember, owner_id):
                return None
            team_id = uuid.uuid4().hex
            session.add(Team(id=team_id, owner_id=owner_id, name=name, glossary=""))
            session.add(TeamMember(user_id=owner_id, team_id=team_id))
            return team_id

    async def team_info(self, user_id: int) -> dict | None:
        async with self.sessions() as session:
            team = await session.scalar(select(Team).join(TeamMember, TeamMember.team_id == Team.id)
                                        .where(TeamMember.user_id == user_id))
            if not team:
                return None
            count = await session.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id))
            return {"id": team.id, "owner_id": team.owner_id, "name": team.name,
                    "glossary": team.glossary, "members": int(count or 0)}

    async def create_team_invite(self, owner_id: int) -> str | None:
        async with self.sessions.begin() as session:
            team = await session.scalar(select(Team).where(Team.owner_id == owner_id).with_for_update())
            if not team:
                return None
            token = uuid.uuid4().hex
            session.add(TeamInvite(token=token, team_id=team.id, expires_at=datetime.now(UTC) + timedelta(days=2)))
            return token

    async def preview_team_invite(self, token: str) -> dict | None:
        async with self.sessions() as session:
            row = (await session.execute(select(Team, TeamInvite).join(TeamInvite, TeamInvite.team_id == Team.id)
                .where(TeamInvite.token == token, TeamInvite.used_at.is_(None),
                       TeamInvite.expires_at > datetime.now(UTC)))).first()
            return {"name": row[0].name, "owner_id": row[0].owner_id} if row else None

    async def remove_team_member(self, owner_id: int, member_id: int) -> bool:
        async with self.sessions.begin() as session:
            team = await session.scalar(select(Team).where(Team.owner_id == owner_id).with_for_update())
            if not team or member_id == owner_id:
                return False
            member = await session.scalar(select(TeamMember).where(TeamMember.team_id == team.id,
                TeamMember.user_id == member_id).with_for_update())
            if not member:
                return False
            await session.delete(member)
            return True

    async def join_team(self, user_id: int, token: str) -> str:
        async with self.sessions.begin() as session:
            user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
            invitation = await session.scalar(select(TeamInvite).where(TeamInvite.token == token).with_for_update())
            if not user or not invitation or invitation.used_at or invitation.expires_at <= datetime.now(UTC):
                return "invalid"
            if await session.get(TeamMember, user_id):
                return "member"
            team = await session.scalar(select(Team).where(Team.id == invitation.team_id).with_for_update())
            count = await session.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id))
            if (count or 0) >= 20:
                return "full"
            session.add(TeamMember(user_id=user_id, team_id=team.id))
            invitation.used_at = datetime.now(UTC)
            return "joined"

    async def leave_team(self, user_id: int) -> str:
        async with self.sessions.begin() as session:
            member = await session.scalar(select(TeamMember).where(TeamMember.user_id == user_id).with_for_update())
            if not member:
                return "missing"
            team = await session.get(Team, member.team_id)
            if team.owner_id == user_id:
                return "owner"
            await session.delete(member)
            return "left"

    async def set_team_glossary(self, owner_id: int, glossary: str) -> bool:
        async with self.sessions.begin() as session:
            team = await session.scalar(select(Team).where(Team.owner_id == owner_id).with_for_update())
            if not team:
                return False
            team.glossary = glossary
            return True

    async def team_report(self, owner_id: int) -> list[dict] | None:
        async with self.sessions() as session:
            team = await session.scalar(select(Team).where(Team.owner_id == owner_id))
            if not team:
                return None
            rows = (await session.execute(select(TeamMember.user_id,
                func.count(JobRecord.id), func.coalesce(func.sum(JobRecord.billable_minutes), 0))
                .outerjoin(JobRecord, (JobRecord.telegram_user_id == TeamMember.user_id) & (JobRecord.status == "completed") & (JobRecord.created_at >= TeamMember.joined_at))
                .where(TeamMember.team_id == team.id).group_by(TeamMember.user_id))).all()
            return [{"user_id": row[0], "jobs": int(row[1]), "minutes": int(row[2])} for row in rows]

    async def create_download_task(self, job_id: str, user_id: int, chat_id: int,
                                   url: str, kind: str) -> None:
        async with self.sessions.begin() as session:
            session.add(DownloadTask(id=job_id, user_id=user_id, chat_id=chat_id,
                                     source_url=url, kind=kind, status="queued"))

    async def update_download_task(self, job_id: str, status: str, *, title: str | None = None,
                                   token: str | None = None, extension: str | None = None,
                                   expires_at: datetime | None = None) -> None:
        values: dict[str, object] = {"status": status}
        if title is not None:
            values["title"] = title[:255]
        if token is not None:
            values.update(token=token, extension=extension, expires_at=expires_at)
        async with self.sessions.begin() as session:
            await session.execute(DownloadTask.__table__.update().where(DownloadTask.id == job_id).values(**values))

    async def list_orders(self, user_id: int, category: str, offset: int = 0, limit: int = 5) -> list[dict]:
        if category == "processing":
            model, owner = JobRecord, JobRecord.telegram_user_id
        elif category == "download":
            model, owner = DownloadTask, DownloadTask.user_id
        elif category == "content":
            model, owner = ContentOrder, ContentOrder.user_id
        else:
            return []
        async with self.sessions() as session:
            rows = (await session.scalars(select(model).where(owner == user_id)
                .order_by(model.created_at.desc(), model.id.desc()).offset(max(0, offset)).limit(limit))).all()
            return [{"id": row.id, "status": row.status, "created_at": row.created_at,
                     "title": getattr(row, "title", None),
                     "source_url": getattr(row, "source_url", None),
                     "kind": ("caption_video" if row.source_url == "telegram-upload" else row.mode)
                     if category == "processing" else row.kind} for row in rows]

    async def update_job_title_if_missing(self, user_id: int, job_id: str, title: str) -> bool:
        clean_title = title[:255].strip()
        if not clean_title:
            return False
        async with self.sessions.begin() as session:
            result = await session.execute(JobRecord.__table__.update().where(
                JobRecord.id == job_id, JobRecord.telegram_user_id == user_id,
                JobRecord.title.is_(None),
            ).values(title=clean_title))
            return result.rowcount == 1

    async def get_owned_order(self, user_id: int, category: str, order_id: str) -> dict | None:
        if category == "processing":
            model, owner = JobRecord, JobRecord.telegram_user_id
        elif category == "download":
            model, owner = DownloadTask, DownloadTask.user_id
        elif category == "content":
            model, owner = ContentOrder, ContentOrder.user_id
        else:
            return None
        async with self.sessions() as session:
            row = await session.scalar(select(model).where(model.id == order_id, owner == user_id))
            if not row:
                return None
            result = {"id": row.id, "status": row.status, "created_at": row.created_at,
                      "kind": ("caption_video" if row.source_url == "telegram-upload" else row.mode)
                      if category == "processing" else row.kind}
            if category == "processing":
                result.update(source_url=row.source_url, title=row.title, minutes=row.billable_minutes,
                              amount=row.billed_amount_toman, package_minutes=row.package_minutes)
                links = (await session.scalars(select(DownloadRecord).where(DownloadRecord.job_id == order_id)
                    .order_by(DownloadRecord.created_at.desc()).limit(10))).all()
                result["links"] = [{"token": link.token, "filename": link.filename,
                                    "expires_at": link.expires_at} for link in links]
            elif category == "download":
                result.update(source_url=row.source_url, title=row.title, token=row.token,
                              extension=row.extension, expires_at=row.expires_at)
            return result

    async def recent_completed_jobs(self, user_id: int, limit: int = 8) -> list[dict]:
        async with self.sessions() as session:
            jobs = (await session.scalars(select(JobRecord).where(
                JobRecord.telegram_user_id == user_id, JobRecord.status == "completed",
                JobRecord.subtitle_srt.is_not(None),
            ).order_by(JobRecord.created_at.desc()).limit(limit))).all()
            return [{"id": job.id, "mode": job.mode, "created_at": job.created_at,
                     "minutes": job.billable_minutes} for job in jobs]

    async def owned_subtitle(self, job_id: str, user_id: int) -> str | None:
        async with self.sessions() as session:
            return await session.scalar(select(JobRecord.subtitle_srt).where(
                JobRecord.id == job_id, JobRecord.telegram_user_id == user_id,
                JobRecord.status == "completed"))

    async def replace_subtitle(self, job_id: str, user_id: int, old: str, new: str) -> bool:
        async with self.sessions.begin() as session:
            job = await session.scalar(select(JobRecord).where(
                JobRecord.id == job_id, JobRecord.telegram_user_id == user_id,
                JobRecord.status == "completed").with_for_update())
            if not job or job.subtitle_srt != old:
                return False
            job.subtitle_srt = new
            return True

    async def content_results(self, user_id: int, job_id: str) -> list[dict]:
        async with self.sessions() as session:
            rows = (await session.scalars(select(ContentOrder).where(ContentOrder.user_id == user_id,
                ContentOrder.job_id == job_id, ContentOrder.status == "completed",
                ContentOrder.output_text.is_not(None)).order_by(ContentOrder.created_at.desc()).limit(5))).all()
            return [{"id": row.id, "kind": row.kind, "created_at": row.created_at} for row in rows]

    async def owned_content_result(self, user_id: int, order_id: str) -> dict | None:
        async with self.sessions() as session:
            row = await session.scalar(select(ContentOrder).where(ContentOrder.id == order_id,
                ContentOrder.user_id == user_id, ContentOrder.status == "completed"))
            return {"kind": row.kind, "text": row.output_text} if row and row.output_text else None

    async def create_content_order(self, order_id: str, user_id: int, job_id: str,
                                   chat_id: int, kind: str, amount: int) -> str:
        if amount <= 0 or kind not in {"summary", "social"}:
            return "unavailable"
        async with self.sessions.begin() as session:
            user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
            job = await session.scalar(select(JobRecord).where(JobRecord.id == job_id,
                JobRecord.telegram_user_id == user_id, JobRecord.status == "completed",
                JobRecord.subtitle_srt.is_not(None)))
            if not job or not user:
                return "missing"
            if user.wallet_balance_toman < amount:
                return "balance"
            user.wallet_balance_toman -= amount
            session.add(ContentOrder(id=order_id, user_id=user_id, job_id=job_id, chat_id=chat_id,
                                     kind=kind, amount_toman=amount, status="queued"))
            session.add(WalletTransaction(id=uuid.uuid4().hex, user_id=user_id,
                amount_toman=-amount, entry_type="job_charge", job_id=job_id,
                memo=f"سفارش محتوای تکمیلی {order_id}"))
            return "created"

    async def finish_content_order(self, order_id: str, output: str, api_cost_usd: float | None = None) -> bool:
        async with self.sessions.begin() as session:
            order = await session.scalar(select(ContentOrder).where(ContentOrder.id == order_id).with_for_update())
            if not order or order.status != "queued":
                return False
            order.output_text = output
            order.api_cost_usd = api_cost_usd
            order.status = "completed"
            return True

    async def refund_content_order(self, order_id: str) -> bool:
        async with self.sessions.begin() as session:
            order = await session.scalar(select(ContentOrder).where(ContentOrder.id == order_id).with_for_update())
            if not order or order.status != "queued":
                return False
            user = await session.scalar(select(User).where(User.telegram_id == order.user_id).with_for_update())
            if not user:
                return False
            user.wallet_balance_toman += order.amount_toman
            order.status = "refunded"
            session.add(WalletTransaction(id=uuid.uuid4().hex, user_id=order.user_id,
                amount_toman=order.amount_toman, entry_type="job_refund", job_id=order.job_id,
                memo=f"بازگشت هزینهٔ محتوای تکمیلی {order.id}"))
            return True

    async def unfinished_content_orders(self) -> list[dict]:
        async with self.sessions() as session:
            orders = (await session.scalars(select(ContentOrder).where(ContentOrder.status == "queued"))).all()
            return [{"id": order.id, "chat_id": order.chat_id} for order in orders]

    async def create_image_order(self, order_id: str, user_id: int, chat_id: int, prompt: str,
                                 aspect: str, provider: str, model: str, optimizer_provider: str,
                                 optimizer_model: str, amount: int, reference: bytes | None = None,
                                 reference_media_type: str | None = None) -> str:
        if amount <= 0 or aspect not in {"1:1", "2:3", "3:2"} or not 1 <= len(prompt) <= 3000:
            return "unavailable"
        if reference is not None and (not reference or len(reference) > 10_000_000 or reference_media_type not in {"image/png", "image/jpeg", "image/webp"}):
            return "unavailable"
        async with self.sessions.begin() as session:
            user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
            if not user or user.wallet_balance_toman < amount:
                return "balance"
            user.wallet_balance_toman -= amount
            session.add(ImageOrder(id=order_id, user_id=user_id, chat_id=chat_id, original_prompt=prompt,
                aspect_ratio=aspect, provider=provider, model=model, optimizer_provider=optimizer_provider,
                optimizer_model=optimizer_model, amount_toman=amount, status="queued",
                reference_image=reference, reference_media_type=reference_media_type))
            session.add(WalletTransaction(id=uuid.uuid4().hex, user_id=user_id, amount_toman=-amount,
                entry_type="job_charge", memo=f"ساخت تصویر {order_id}"))
            return "created"

    async def set_image_prompt(self, order_id: str, prompt: str, cost: float | None) -> bool:
        async with self.sessions.begin() as session:
            order = await session.scalar(select(ImageOrder).where(ImageOrder.id == order_id).with_for_update())
            if not order or order.status != "queued":
                return False
            order.optimized_prompt, order.optimizer_cost_usd = prompt, cost
            return True

    async def finish_image_order(self, order_id: str, image: bytes, media_type: str, cost: float | None) -> bool:
        async with self.sessions.begin() as session:
            order = await session.scalar(select(ImageOrder).where(ImageOrder.id == order_id).with_for_update())
            if not order or order.status != "queued":
                return False
            order.image_data, order.media_type, order.image_cost_usd = image, media_type, cost
            order.status, order.finished_at = "completed", datetime.now(UTC)
            return True

    async def refund_image_order(self, order_id: str) -> bool:
        async with self.sessions.begin() as session:
            order = await session.scalar(select(ImageOrder).where(ImageOrder.id == order_id).with_for_update())
            if not order or order.status != "queued":
                return False
            user = await session.scalar(select(User).where(User.telegram_id == order.user_id).with_for_update())
            if not user:
                return False
            user.wallet_balance_toman += order.amount_toman
            order.status, order.finished_at = "refunded", datetime.now(UTC)
            session.add(WalletTransaction(id=uuid.uuid4().hex, user_id=order.user_id,
                amount_toman=order.amount_toman, entry_type="job_refund", memo=f"بازگشت هزینهٔ تصویر {order.id}"))
            return True

    async def unfinished_image_orders(self) -> list[dict]:
        async with self.sessions() as session:
            rows = (await session.scalars(select(ImageOrder).where(ImageOrder.status == "queued"))).all()
            return [{"id": row.id, "chat_id": row.chat_id} for row in rows]

    async def list_image_orders(self, user_id: int, offset: int = 0, limit: int = 6) -> list[dict]:
        async with self.sessions() as session:
            rows = (await session.execute(select(ImageOrder.id, ImageOrder.status, ImageOrder.created_at,
                                                  ImageOrder.amount_toman).where(ImageOrder.user_id == user_id)
                    .order_by(ImageOrder.created_at.desc(), ImageOrder.id.desc()).offset(max(0, offset)).limit(limit))).all()
            return [{"id": row.id, "status": row.status, "created_at": row.created_at,
                     "amount": row.amount_toman} for row in rows]

    async def owned_image(self, user_id: int, order_id: str) -> dict | None:
        async with self.sessions() as session:
            row = await session.scalar(select(ImageOrder).where(ImageOrder.id == order_id,
                                        ImageOrder.user_id == user_id, ImageOrder.status == "completed"))
            if not row or not row.image_data:
                return None
            return {"image": row.image_data, "media_type": row.media_type, "prompt": row.original_prompt}

    async def create_wallet_job(
        self, job_id: str, user_id: int, chat_id: int, url: str,
        selected_height: int | None, mode: str, api_provider: str,
        billable_minutes: int, amount_toman: int, title: str | None = None,
    ) -> int | None:
        async with self.sessions.begin() as session:
            user = await session.scalar(
                select(User).where(User.telegram_id == user_id).with_for_update()
            )
            if not user or user.wallet_balance_toman < amount_toman:
                return None
            user.wallet_balance_toman -= amount_toman
            session.add(JobRecord(
                id=job_id, telegram_user_id=user_id, chat_id=chat_id,
                source_url=url, title=title[:255] if title else None,
                mode=mode, api_provider=api_provider,
                selected_height=selected_height, status="queued",
                billable_minutes=billable_minutes, billed_amount_toman=amount_toman,
            ))
            session.add(WalletTransaction(
                id=uuid.uuid4().hex, user_id=user_id, amount_toman=-amount_toman,
                entry_type="job_charge", job_id=job_id,
                memo=f"پردازش {billable_minutes} دقیقه‌ای ({mode})",
            ))
            return user.wallet_balance_toman

    async def refund_job_wallet(self, job_id: str) -> dict | None:
        async with self.sessions.begin() as session:
            job = await session.scalar(select(JobRecord).where(JobRecord.id == job_id).with_for_update())
            if not job:
                return None
            if job.wallet_refunded:
                return {"refunded": False}
            if job.package_id and job.package_minutes:
                package = await session.scalar(select(MinutePackage).where(MinutePackage.id == job.package_id,
                    MinutePackage.user_id == job.telegram_user_id).with_for_update())
                if not package:
                    return None
                package.remaining_minutes += job.package_minutes
                if package.expires_at <= datetime.now(UTC):
                    package.expires_at = datetime.now(UTC) + timedelta(days=1)
                job.wallet_refunded = True
                return {"refunded": True, "package_minutes": job.package_minutes}
            if not job.billed_amount_toman or job.billed_amount_toman <= 0:
                return None
            user = await session.scalar(
                select(User).where(User.telegram_id == job.telegram_user_id).with_for_update()
            )
            if not user:
                return None
            if job.wallet_refunded:
                return {"balance_toman": user.wallet_balance_toman, "refunded": False}
            user.wallet_balance_toman += job.billed_amount_toman
            job.wallet_refunded = True
            session.add(WalletTransaction(
                id=uuid.uuid4().hex, user_id=user.telegram_id,
                amount_toman=job.billed_amount_toman, entry_type="job_refund",
                job_id=job.id, memo="بازگشت هزینهٔ پردازش ناموفق یا لغوشده",
            ))
            return {"balance_toman": user.wallet_balance_toman, "refunded": True}

    async def interrupted_wallet_jobs(self) -> list[dict]:
        async with self.sessions() as session:
            rows = (await session.execute(
                select(JobRecord.id, JobRecord.telegram_user_id, JobRecord.chat_id)
                .where(JobRecord.status == "interrupted")
                .where((JobRecord.billed_amount_toman > 0) | (JobRecord.package_minutes > 0))
                .where(JobRecord.wallet_refunded.is_(False))
            )).all()
            return [{"job_id": r[0], "user_id": r[1], "chat_id": r[2]} for r in rows]

    async def legacy_failed_stars_jobs(self) -> list[dict]:
        async with self.sessions() as session:
            rows = (await session.execute(
                select(PaymentOrder.payload, PaymentOrder.payment_charge_id,
                       JobRecord.telegram_user_id, JobRecord.chat_id)
                .join(JobRecord, JobRecord.id == PaymentOrder.job_id)
                .where(PaymentOrder.status == "paid")
                .where(PaymentOrder.payment_charge_id.is_not(None))
                .where(JobRecord.status.in_(("failed", "cancelled", "interrupted")))
            )).all()
            return [{
                "payload": row[0], "charge_id": row[1],
                "user_id": row[2], "chat_id": row[3],
            } for row in rows]

    async def mark_legacy_stars_refunded(self, payload: str) -> None:
        async with self.sessions.begin() as session:
            order = await session.get(PaymentOrder, payload)
            if order and order.status == "paid":
                order.status = "refunded"

    async def get_business_stats(self) -> dict[str, int | float]:
        async with self.sessions() as session:
            users = await session.scalar(select(func.count()).select_from(User)) or 0
            jobs = await session.scalar(select(func.count()).select_from(JobRecord)) or 0
            completed = await session.scalar(
                select(func.count()).select_from(JobRecord).where(JobRecord.status == "completed")
            ) or 0
            wallet_total = await session.scalar(select(func.coalesce(func.sum(User.wallet_balance_toman), 0))) or 0
            gross = await session.scalar(select(func.coalesce(
                -func.sum(WalletTransaction.amount_toman), 0
            )).where(WalletTransaction.entry_type == "job_charge")) or 0
            refunds = await session.scalar(select(func.coalesce(
                func.sum(WalletTransaction.amount_toman), 0
            )).where(WalletTransaction.entry_type == "job_refund")) or 0
            pending_deposits = await session.scalar(select(func.count()).select_from(CardTransferRequest)
                .where(CardTransferRequest.status == "pending_review")) or 0
            api_cost = await session.scalar(select(func.sum(JobRecord.openai_cost_usd)))
            content_cost = await session.scalar(select(func.sum(ContentOrder.api_cost_usd)).where(ContentOrder.status == "completed"))
            content_unknown = await session.scalar(select(func.count()).select_from(ContentOrder).where(
                ContentOrder.status == "completed", ContentOrder.api_cost_usd.is_(None))) or 0
            image_cost = await session.scalar(select(func.sum(ImageOrder.image_cost_usd)))
            image_optimizer_cost = await session.scalar(select(func.sum(ImageOrder.optimizer_cost_usd)))
            image_unknown = await session.scalar(select(func.count()).select_from(ImageOrder).where(
                ImageOrder.status == "completed", ImageOrder.image_cost_usd.is_(None))) or 0
            return {
                "users": int(users), "jobs": int(jobs), "completed": int(completed),
                "wallet_total_toman": int(wallet_total), "gross_sales_toman": int(gross),
                "refunds_toman": int(refunds), "net_sales_toman": int(gross - refunds),
                "pending_deposits": int(pending_deposits),
                "api_cost_usd": float(api_cost) if api_cost is not None else 0.0,
                "content_cost_usd": float(content_cost) if content_cost is not None else 0.0,
                "content_cost_unknown": int(content_unknown),
                "image_cost_usd": float(image_cost or 0),
                "image_optimizer_cost_usd": float(image_optimizer_cost or 0),
                "image_cost_unknown": int(image_unknown),
            }

    async def close(self) -> None:
        await self.engine.dispose()

    async def update_job(
        self,
        job_id: str,
        status: str,
        *,
        size: int | None = None,
        cost_usd: float | None = None,
        subtitle: str | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        values: dict[str, object] = {"status": status}
        if status == "running":
            values["started_at"] = now
        if status in {"completed", "failed", "cancelled", "interrupted"}:
            values["finished_at"] = now
        if size is not None:
            values["output_size_bytes"] = size
        if cost_usd is not None:
            values["openai_cost_usd"] = cost_usd
        if subtitle is not None:
            values["subtitle_srt"] = subtitle
        if error is not None:
            values["error_message"] = error[:4000]
        async with self.sessions.begin() as session:
            await session.execute(JobRecord.__table__.update().where(JobRecord.id == job_id).values(**values))

    async def add_download(
        self, job_id: str, token: str, filename: str, size: int, expires_at: datetime
    ) -> None:
        async with self.sessions.begin() as session:
            session.add(
                DownloadRecord(
                    token=token,
                    job_id=job_id,
                    filename=filename,
                    size_bytes=size,
                    expires_at=expires_at,
                )
            )

    async def close(self) -> None:
        await self.engine.dispose()
