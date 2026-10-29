
import os

from sqlalchemy import (
    create_engine,
    ForeignKey,
    String,
    Text,
    DateTime,
    Integer,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'resume_matcher.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    job_title: Mapped[str] = mapped_column(
        String(150), default="Job Match Analysis"
    )
    semantic_score: Mapped[int] = mapped_column(Integer)
    ats_score: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="analyses")


Base.metadata.create_all(bind=engine)
