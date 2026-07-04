"""Create the first admin user and seed demo water providers on startup if they don't exist."""
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.provider import Provider, ProviderServiceArea, ProviderStatus
from app.models.user import User, UserRole

log = structlog.get_logger(__name__)

_SEED_PROVIDERS = [
    {
        "email":             "info@wasac.rw",
        "full_name":         "WASAC Administrator",
        "organization_name": "WASAC",
        "description":       "Water and Sanitation Corporation — Rwanda's national water utility.",
        "phone":             "+250788123000",
        "org_phone":         "+250788123000",
        "org_email":         "info@wasac.rw",
        "website":           "https://www.wasac.rw",
        "service_categories": ["water_supply", "sanitation", "infrastructure"],
        "provinces":         ["Kigali City", "Northern Province", "Southern Province",
                              "Eastern Province", "Western Province"],
    },
    {
        "email":             "support@iriba.rw",
        "full_name":         "IRIBA Water Group Admin",
        "organization_name": "IRIBA Water Group",
        "description":       "Urban water distribution specialist serving Kigali and peri-urban areas.",
        "phone":             "+250788345000",
        "org_phone":         "+250788345000",
        "org_email":         "support@iriba.rw",
        "website":           None,
        "service_categories": ["water_supply", "meter_services", "water_quality"],
        "provinces":         ["Kigali City"],
    },
    {
        "email":             "hello@prowater.rw",
        "full_name":         "Pro Water Rwanda Admin",
        "organization_name": "Pro Water Rwanda",
        "description":       "Commercial water supply and water truck delivery across Rwanda.",
        "phone":             "+250788567000",
        "org_phone":         "+250788567000",
        "org_email":         "hello@prowater.rw",
        "website":           None,
        "service_categories": ["truck_delivery", "water_storage", "water_supply"],
        "provinces":         ["Kigali City", "Eastern Province", "Southern Province"],
    },
    {
        "email":             "contact@wateraccessrwanda.rw",
        "full_name":         "Water Access Rwanda Admin",
        "organization_name": "Water Access Rwanda",
        "description":       "Rural water supply and connection services across Rwanda's countryside.",
        "phone":             "+250788234567",
        "org_phone":         "+250788234567",
        "org_email":         "contact@wateraccessrwanda.rw",
        "website":           None,
        "service_categories": ["water_supply", "rural_connections"],
        "provinces":         ["Northern Province", "Southern Province", "Eastern Province", "Western Province"],
    },
    {
        "email":             "info@aquasan.rw",
        "full_name":         "Aquasan Limited Admin",
        "organization_name": "Aquasan Limited",
        "description":       "Sanitation and drainage services for Kigali City and surrounding areas.",
        "phone":             "+250788456789",
        "org_phone":         "+250788456789",
        "org_email":         "info@aquasan.rw",
        "website":           None,
        "service_categories": ["sanitation", "drainage"],
        "provinces":         ["Kigali City"],
    },
    {
        "email":             "fidelemessielimaestro@gmail.com",
        "full_name":         "Bikorimana Jean",
        "organization_name": "Temba Digital Bridge",
        "description":       "Digital water services platform connecting communities with water providers across Kigali.",
        "phone":             "+250790147995",
        "org_phone":         "+250790147995",
        "org_email":         "f.ndihokubw1@alustudent.com",
        "website":           None,
        "service_categories": ["water_supply", "sanitation", "meter_services"],
        "provinces":         ["Kigali City"],
    },
]


async def init_db(db: AsyncSession) -> None:
    # ── Admin user ────────────────────────────────────────────────────────────
    result = await db.execute(
        select(User).where(User.email == settings.FIRST_ADMIN_EMAIL)
    )
    if not result.scalar_one_or_none():
        admin = User(
            email=settings.FIRST_ADMIN_EMAIL,
            hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
            full_name="Platform Administrator",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        db.add(admin)
        await db.commit()
        log.info("Created first admin user", email=settings.FIRST_ADMIN_EMAIL)

    # ── Seed demo water providers (idempotent) ────────────────────────────────
    for p in _SEED_PROVIDERS:
        existing = (await db.execute(
            select(User).where(User.email == p["email"])
        )).scalar_one_or_none()

        if existing:
            # Make sure provider profile exists and is APPROVED
            prov = (await db.execute(
                select(Provider).where(Provider.user_id == existing.id)
            )).scalar_one_or_none()
            if prov and prov.status != ProviderStatus.APPROVED:
                prov.status = ProviderStatus.APPROVED
                await db.commit()
            continue

        # Check phone conflict — skip phone if taken
        phone_taken = (await db.execute(
            select(User).where(User.phone == p["phone"])
        )).scalar_one_or_none()

        user = User(
            email=p["email"],
            phone=None if phone_taken else p["phone"],
            full_name=p["full_name"],
            hashed_password=hash_password("Temba@Provider2025!"),
            role=UserRole.PROVIDER,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.flush()

        provider = Provider(
            user_id=user.id,
            organization_name=p["organization_name"],
            description=p["description"],
            phone=p["org_phone"],
            email=p["org_email"],
            website=p["website"],
            service_categories=p["service_categories"],
            custom_services=[],
            status=ProviderStatus.APPROVED,
            working_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            work_start_time="08:00",
            work_end_time="17:00",
            max_appointments_per_day=20,
            unavailable_dates=[],
        )
        db.add(provider)
        await db.flush()

        for province in p["provinces"]:
            db.add(ProviderServiceArea(provider_id=provider.id, province=province))

        await db.commit()
        log.info("Seeded provider", org=p["organization_name"])

    # Approve any providers still in PENDING status (auto-approve model)
    result = await db.execute(
        update(Provider)
        .where(Provider.status == ProviderStatus.PENDING)
        .values(status=ProviderStatus.APPROVED)
        .returning(Provider.id)
    )
    approved_ids = result.fetchall()
    if approved_ids:
        await db.commit()
        log.info("Auto-approved pending providers", count=len(approved_ids))
