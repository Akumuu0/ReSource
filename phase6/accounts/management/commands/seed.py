"""python manage.py seed

Empties the database and loads the demo data. All passwords are "demo1234".
Requests are created through the real services, so every record has its
history, approvals and notifications exactly as if people had clicked the buttons.
All names and data are synthetic (design rule ORG-2).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Department, User
from assets.models import Category
from assets.services import AssetService
from resource_requests.services import ApprovalService, RequestService, TransferService
from sustainability.models import CategoryValue

PASSWORD = "demo1234"

DEPARTMENTS = [
    ("PHY", "Physics", "SAN Campus"),
    ("ENG", "Engineering", "Main Campus"),
    ("FAC", "Facilities", "Main Campus"),
]

# username, first name, last name, role, department code
USERS = [
    ("physics.rep", "Sara", "Khalid", User.REPRESENTATIVE, "PHY"),
    ("physics.coord", "Omar", "Haddad", User.COORDINATOR, "PHY"),
    ("eng.rep", "Layla", "Nasser", User.REPRESENTATIVE, "ENG"),
    ("eng.coord", "Yousef", "Karim", User.COORDINATOR, "ENG"),
    ("fac.rep", "Mariam", "Saeed", User.REPRESENTATIVE, "FAC"),
    ("fac.coord", "Hassan", "Ali", User.COORDINATOR, "FAC"),
    ("admin", "Fatima", "Rashed", User.ADMINISTRATOR, "FAC"),
]

# name, keywords used by the rule-based classifier
CATEGORIES = [
    ("Lab Equipment", "oscilloscope,multimeter,power supply,signal generator,microscope,centrifuge,probe,lab"),
    ("Computers & Monitors", "monitor,laptop,desktop,computer,pc,keyboard,screen,dell,lenovo,elitedesk"),
    ("Furniture", "chair,desk,table,cabinet,shelf,stool,bookcase,locker,drawer"),
    ("Audio-Visual", "projector,speaker,microphone,camera,lumens,hdmi,video"),
    ("Office Equipment", "printer,scanner,shredder,copier,whiteboard,laserjet,phone"),
    ("Tools & Workshop", "drill,saw,toolbox,ladder,wrench,workbench,soldering"),
]

# The EPA WARM mixed-electronics factor fits only these categories; the others get no factor (FR-13.8).
ELECTRONIC_CATEGORIES = ["Lab Equipment", "Computers & Monitors", "Audio-Visual"]

# code, name, description, category, condition, department, quantity, value (AED/unit), kg/unit, final state
ASSETS = [
    ("A-2026-0401", "Dell 24-inch monitor", "Dell P2419H 24-inch IPS monitor with HDMI and DisplayPort, small scratch on the stand",
     "Computers & Monitors", "Good", "ENG", 6, "650", "4.5", "Available"),
    ("A-2026-0402", "Ergonomic office chair", "Adjustable mesh office chair with armrests and lumbar support",
     "Furniture", "Good", "FAC", 10, "450", "12", "Available"),
    ("A-2026-0403", "Epson classroom projector", "Epson EB-W51 projector, 4000 lumens, lamp at 60 percent",
     "Audio-Visual", "Fair", "FAC", 1, "1800", "3.1", "Available"),
    ("A-2026-0404", "Lab bench stool", "Height-adjustable lab stool, some wear on the seat",
     "Furniture", "Fair", "PHY", 8, "120", "5", "Available"),
    ("A-2026-0405", "HP EliteDesk desktop PC", "HP EliteDesk 800 G5 desktop computer, Intel i5, 16 GB RAM, 512 GB SSD",
     "Computers & Monitors", "Good", "ENG", 4, "2500", "5.5", "Available"),
    ("A-2026-0406", "Mobile whiteboard", "Double-sided magnetic whiteboard on wheels",
     "Office Equipment", "Good", "FAC", 2, "700", "15", "Available"),
    ("A-2026-0407", "Bench power supply", "Triple-output DC bench power supply, 0-30 V, unused",
     "Lab Equipment", "New", "ENG", 3, "900", "4", "Available"),
    ("A-2026-0408", "Analog oscilloscope", "50 MHz dual-trace analog oscilloscope, works but the knobs are worn",
     "Lab Equipment", "Fair", "PHY", 1, "3000", "3.0", "Available"),
    ("A-2026-0409", "Steel filing cabinet", "Four-drawer steel filing cabinet, dented side, lock broken",
     "Furniture", "Poor", "FAC", 2, "500", "30", "Draft"),
    ("A-2026-0410", "Laser printer", "HP LaserJet Pro M404 mono laser printer",
     "Office Equipment", "Good", "PHY", 1, "1500", "10", "Withdrawn"),
    ("A-2026-0411", "Soldering station", "Temperature-controlled soldering station with stand and tips",
     "Tools & Workshop", "Good", "ENG", 2, "350", "1.8", "Draft"),
    ("A-2026-0412", "Digital oscilloscope", "100 MHz two-channel digital storage oscilloscope from the EE teaching "
     "lab upgrade. Works; probes and power cables included.",
     "Lab Equipment", "Good", "ENG", 2, "4200", "2.6", "Available"),
]

# Expected repair cost per unit in AED (design Table 17-1, F6); every other asset needs none.
REPAIR_COSTS = {"A-2026-0408": "150", "A-2026-0409": "80"}


class Command(BaseCommand):
    help = "Empty the database and load the ReSource demo data (password for every user: demo1234)."

    def handle(self, *args, **options):
        call_command("flush", interactive=False, verbosity=0)
        with transaction.atomic():
            self.departments = {code: Department.objects.create(code=code, name=name, campus=campus)
                                for code, name, campus in DEPARTMENTS}
            self.users = {}
            for username, first, last, role, dept in USERS:
                self.users[username] = User.objects.create_user(
                    username, password=PASSWORD, first_name=first, last_name=last, role=role,
                    department=self.departments[dept],
                    is_staff=(role == User.ADMINISTRATOR), is_superuser=(role == User.ADMINISTRATOR),
                )
            self.categories = {}
            for name, keywords in CATEGORIES:
                category = Category.objects.create(name=name, keywords=keywords)
                if name in ELECTRONIC_CATEGORIES:
                    CategoryValue.objects.create(
                        category=category, value_type=CategoryValue.EMISSION_FACTOR, value=Decimal("22.92"),
                        unit="kg CO2e per kg", effective_date=date(2026, 1, 1), version=1,
                        source="EPA WARM v16 source-reduction factor, mixed electronics",
                    )
                self.categories[name] = category
            self.create_assets()
            self.create_requests()
        self.print_summary()

    def coordinator_of(self, dept_code):
        return User.objects.get(role=User.COORDINATOR, department=self.departments[dept_code])

    def create_assets(self):
        self.assets = {}
        for code, name, description, category, condition, dept, qty, value, kg, final_state in ASSETS:
            coordinator = self.coordinator_of(dept)
            asset = AssetService.register(coordinator, {
                "name": name, "description": description, "category": self.categories[category],
                "condition": condition, "tags": "", "quantity": qty,
                "estimated_value": Decimal(value), "weight_kg": Decimal(kg),
                "repair_cost": Decimal(REPAIR_COSTS.get(code, "0")),
            }, code=code)
            if final_state in ("Available", "Withdrawn"):
                AssetService.publish(coordinator, asset)
            if final_state == "Withdrawn":
                AssetService.withdraw(coordinator, asset)
            self.assets[code] = asset

    def create_requests(self):
        u, a = self.users, self.assets
        soon = date.today() + timedelta(days=21)

        # An open need, waiting for the requester to pick an AI match (design example R-2026-0391).
        RequestService.submit_need(u["physics.rep"], self.categories["Lab Equipment"], 2,
                                   "Two oscilloscopes for the teaching lab", soon,
                                   specifications="At least 70 MHz, 2 channels", min_condition="Good",
                                   urgency="Medium", code="R-2026-0391")

        # Completed: 2 monitors from Engineering to Physics.
        req = RequestService.submit(u["physics.rep"], a["A-2026-0401"], 2, "Second screens for the data-analysis room", soon)
        ApprovalService.release(u["eng.coord"], req)
        ApprovalService.approve(u["admin"], req)
        TransferService.hand_over(u["eng.coord"], req)
        TransferService.confirm_receipt(u["physics.rep"], req, "Good")

        # Completed: 4 chairs from Facilities to Engineering.
        req = RequestService.submit(u["eng.rep"], a["A-2026-0402"], 4, "Chairs for the new design studio", soon)
        ApprovalService.release(u["fac.coord"], req)
        ApprovalService.approve(u["admin"], req)
        TransferService.hand_over(u["fac.coord"], req)
        TransferService.confirm_receipt(u["eng.rep"], req, "Good")

        # In transfer: the projector is on its way to Physics (waiting for receipt).
        req = RequestService.submit(u["physics.rep"], a["A-2026-0403"], 1, "Projector for the seminar room", soon)
        ApprovalService.release(u["fac.coord"], req)
        ApprovalService.approve(u["admin"], req)
        TransferService.hand_over(u["fac.coord"], req)

        # Released: waiting for an Administrator.
        req = RequestService.submit(u["eng.rep"], a["A-2026-0404"], 2, "Stools for the electronics lab", soon)
        ApprovalService.release(u["physics.coord"], req)

        # Submitted: waiting for the Engineering Asset Coordinator.
        RequestService.submit(u["physics.rep"], a["A-2026-0405"], 2, "Computers for the student project room", soon)

        # Rejected: declined by the owner with a reason.
        req = RequestService.submit(u["fac.rep"], a["A-2026-0407"], 1, "Power supply for the workshop", soon)
        ApprovalService.decline(u["eng.coord"], req, "Kept for the new electronics course next term")

        # Approved: units reserved, waiting for hand-over.
        req = RequestService.submit(u["eng.rep"], a["A-2026-0406"], 1, "Whiteboard for team meetings", soon)
        ApprovalService.release(u["fac.coord"], req)
        ApprovalService.approve(u["admin"], req)

    def print_summary(self):
        self.stdout.write(self.style.SUCCESS("Demo data loaded. Every password is demo1234."))
        for username, first, last, role, dept in USERS:
            self.stdout.write(f"  {username:<14} {dict(User.ROLE_CHOICES)[role]:<26} {self.departments[dept].name}")
