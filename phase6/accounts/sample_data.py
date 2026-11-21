"""A small set of departments, users and one asset, shared by the automated tests."""
from decimal import Decimal
from types import SimpleNamespace

from accounts.models import Department, User
from assets.models import Category
from assets.services import AssetService


def make_user(username, role, department):
    # Tests sign in with force_login, so no password is needed (hashing one is slow).
    return User.objects.create(username=username, role=role, department=department)


def build_sample_world(units=2):
    """Physics needs oscilloscopes; Engineering owns them (design example, Section 17.4)."""
    w = SimpleNamespace()
    w.physics = Department.objects.create(code="PHY", name="Physics", campus="SAN Campus")
    w.engineering = Department.objects.create(code="ENG", name="Engineering", campus="Main Campus")
    w.facilities = Department.objects.create(code="FAC", name="Facilities", campus="Main Campus")

    w.physics_rep = make_user("physics.rep", User.REPRESENTATIVE, w.physics)
    w.physics_coord = make_user("physics.coord", User.COORDINATOR, w.physics)
    w.eng_rep = make_user("eng.rep", User.REPRESENTATIVE, w.engineering)
    w.eng_coord = make_user("eng.coord", User.COORDINATOR, w.engineering)
    w.fac_rep = make_user("fac.rep", User.REPRESENTATIVE, w.facilities)
    w.admin = make_user("admin", User.ADMINISTRATOR, w.facilities)

    w.lab = Category.objects.create(name="Lab Equipment", keywords="oscilloscope,multimeter,lab")
    w.scope = AssetService.register(w.eng_coord, {
        "name": "Digital oscilloscope",
        "description": "100 MHz two-channel digital oscilloscope",
        "category": w.lab,
        "condition": "Good",
        "tags": "oscilloscope, 100 MHz",
        "quantity": units,
        "estimated_value": Decimal("4200"),
        "weight_kg": Decimal("2.6"),
    }, code="A-2026-0412")
    AssetService.publish(w.eng_coord, w.scope)
    return w
