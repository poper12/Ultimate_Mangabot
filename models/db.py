import os
from typing import Type, List, TypeVar, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, Field, Session, select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from tools import LanguageSingleton

T = TypeVar("T")

#user_data = database['users']


class ChapterFile(SQLModel, table=True):
    url: str = Field(primary_key=True)
    file_id: Optional[str]
    file_unique_id: Optional[str]
    cbz_id: Optional[str]
    cbz_unique_id: Optional[str]
    #telegraph_url: Optional[str]

class UserInfo(SQLModel, table=True):
    user_id: str = Field(primary_key=True, regex=r'\d+')
    thumb: Optional[str]
    cap: Optional[str]
    b1: Optional[str]
    b2: Optional[str]

class MangaOutput(SQLModel, table=True):
    user_id: str = Field(primary_key=True, regex=r'\d+')
    output: int = Field


class Subscription(SQLModel, table=True):
    url: str = Field(primary_key=True)
    user_id: str = Field(primary_key=True, regex=r'\d+')


class LastChapter(SQLModel, table=True):
    url: str = Field(primary_key=True)
    chapter_url: str = Field


class MangaName(SQLModel, table=True):
    url: str = Field(primary_key=True)
    name: str = Field


class DB(metaclass=LanguageSingleton):

    def __init__(self, dbname: str = 'sqlite+aiosqlite:///test.db'):
        if dbname.startswith('postgres://'):
            dbname = dbname.replace('postgres://', 'postgresql+asyncpg://', 1)
        elif dbname.startswith('postgresql://'):
            dbname = dbname.replace('postgresql://', 'postgresql+asyncpg://', 1)
        elif dbname.startswith('sqlite'):
            dbname = dbname.replace('sqlite', 'sqlite+aiosqlite', 1)

        self.engine = create_async_engine(dbname)

    async def connect(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all, checkfirst=True)

    async def add(self, other: SQLModel):
        async with AsyncSession(self.engine) as session:  # type: AsyncSession
            async with session.begin():
                session.add(other)

    async def get(self, table: Type[T], id) -> T:
        async with AsyncSession(self.engine) as session:  # type: AsyncSession
            return await session.get(table, id)

    async def get_all(self, table: Type[T]) -> List[T]:
        async with AsyncSession(self.engine) as session:  # type: AsyncSession
            statement = select(table)
            return await session.exec(statement=statement)

    async def erase(self, other: SQLModel):
        async with AsyncSession(self.engine) as session:  # type: AsyncSession
            async with session.begin():
                await session.delete(other)

    async def get_chapter_file_by_id(self, id: str):
        async with AsyncSession(self.engine) as session:  # type: AsyncSession
            statement = select(ChapterFile).where((ChapterFile.file_unique_id == id) |
                                                  (ChapterFile.cbz_unique_id == id) |
                                                  (ChapterFile.telegraph_url == id))
            return (await session.exec(statement=statement)).first()

    async def get_user(self, user_id: str):
        async with AsyncSession(self.engine) as session:  # type: AsyncSession
            # Create a select statement to query UserInfo by user_id
            statement = select(UserInfo).where(UserInfo.user_id == user_id)
            result = await session.execute(statement)
            return result.scalars().first()
    
    async def add_users(self, user_id: str, thumb: str, cap: str, b1: str, b2: str):
    # Check if the user already exists
        async with AsyncSession(self.engine) as session:
            result = await session.execute(select(UserInfo).where(UserInfo.user_id == user_id))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                await session.execute(
                    update(UserInfo)
                    .where(UserInfo.user_id == user_id)
                    .values(thumb=thumb, cap=cap, b1=b1, b2=b2)
                )
            else:
                new_user = UserInfo(user_id=user_id, thumb=thumb, cap=cap, b1=b1, b2=b2)
                session.add(new_user)
            await session.commit()
            return
    
    async def get_subs(self, user_id: str, filters=None) -> List[MangaName]:
        async with AsyncSession(self.engine) as session:
            statement = (
                select(MangaName)
                .join(Subscription, Subscription.url == MangaName.url)
                .where(Subscription.user_id == user_id)
            )
            for filter_ in filters or []:
                statement = statement.where(MangaName.name.ilike(f'%{filter_}%') | MangaName.url.ilike(f'%{filter_}%'))
            return (await session.exec(statement=statement)).all()

    async def erase_subs(self, user_id: str):
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                statement = delete(Subscription).where(Subscription.user_id == user_id)
                await session.exec(statement=statement)

