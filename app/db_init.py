from app.models.database import Base, engine
from app.models import User, Lot, Order  # noqa: F401 - register models


def init_db():
    Base.metadata.create_all(bind=engine)


def seed_first_lot(db_session):
    from app.models import Lot

    if db_session.query(Lot).filter(Lot.slug == "faberge-egg").first():
        return
    lot = Lot(
        name="Faberge Egg",
        slug="faberge-egg",
        total_fractions=100_000_000,
        special_price_fractions_cap=3_000_000,
        price_special_eur=0.03,
        price_nominal_eur=0.09,
        sold_special_fractions=0,
        is_active=True,
    )
    db_session.add(lot)
    db_session.commit()
