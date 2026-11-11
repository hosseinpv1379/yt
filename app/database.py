"""PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and downloads."""

from datetime import UTC, datetime
import uuid

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func, select, text
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

    async def create_wallet_job(
        self, job_id: str, user_id: int, chat_id: int, url: str,
        selected_height: int | None, mode: str, api_provider: str,
        billable_minutes: int, amount_toman: int,
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
                source_url=url, mode=mode, api_provider=api_provider,
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
            if not job or not job.billed_amount_toman or job.billed_amount_toman <= 0:
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
                .where(JobRecord.billed_amount_toman.is_not(None), JobRecord.billed_amount_toman > 0)
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
            return {
                "users": int(users), "jobs": int(jobs), "completed": int(completed),
                "wallet_total_toman": int(wallet_total), "gross_sales_toman": int(gross),
                "refunds_toman": int(refunds), "net_sales_toman": int(gross - refunds),
                "pending_deposits": int(pending_deposits),
                "api_cost_usd": float(api_cost) if api_cost is not None else 0.0,
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
