"""Tests for asset rules: the state machine, history, permissions and search (C2, C3, C6)."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from accounts.common import BusinessRuleError
from accounts.sample_data import build_sample_world
from resource_requests.services import RequestService

from .lifecycle import AssetStateMachine
from .models import Asset, LifecycleEvent
from .services import AssetService

NEW_ASSET = {
    "name": "Office chair", "description": "Ergonomic office chair", "condition": "Good",
    "tags": "", "quantity": 4, "estimated_value": Decimal("450"), "weight_kg": Decimal("12"),
}


class StateMachineTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()

    def make_asset(self, state):
        asset = AssetService.register(self.w.eng_coord, dict(NEW_ASSET, category=self.w.lab))
        Asset.objects.filter(pk=asset.pk).update(state=state)
        asset.refresh_from_db()
        return asset

    def test_only_the_six_design_moves_are_allowed(self):
        self.assertEqual(AssetStateMachine.ALLOWED_MOVES, {
            ("Draft", "Available"), ("Available", "Reserved"), ("Reserved", "In Transfer"),
            ("In Transfer", "In Use"), ("Reserved", "Available"), ("Available", "Withdrawn"),
        })

    def test_illegal_moves_are_refused_and_leave_no_trace(self):
        illegal = [("Draft", "In Use"), ("Draft", "Reserved"), ("Available", "In Use"),
                   ("In Use", "Available"), ("Withdrawn", "Available"), ("In Transfer", "Available")]
        for old_state, new_state in illegal:
            with self.subTest(move=f"{old_state} -> {new_state}"):
                asset = self.make_asset(old_state)
                events_before = asset.events.count()
                with self.assertRaises(BusinessRuleError):
                    AssetStateMachine.change_state(asset, new_state, self.w.eng_coord, "Try")
                asset.refresh_from_db()
                self.assertEqual(asset.state, old_state)
                self.assertEqual(asset.events.count(), events_before)

    def test_allowed_move_writes_who_what_when_old_and_new_state(self):
        asset = self.make_asset("Draft")
        AssetStateMachine.change_state(asset, "Available", self.w.eng_coord, "Published")
        event = asset.events.last()
        self.assertEqual((event.old_state, event.new_state), ("Draft", "Available"))
        self.assertEqual(event.performed_by, self.w.eng_coord)
        self.assertEqual(event.action, "Published")
        self.assertIsNotNone(event.occurred_at)

    def test_history_cannot_be_edited(self):
        event = LifecycleEvent.objects.first()
        event.note = "changed"
        with self.assertRaises(ValueError):
            event.save()


class AssetServiceTests(TestCase):
    def setUp(self):
        self.w = build_sample_world()

    def test_register_saves_a_draft_in_the_coordinators_department(self):
        asset = AssetService.register(self.w.physics_coord, dict(NEW_ASSET, category=self.w.lab))
        self.assertEqual(asset.state, Asset.DRAFT)
        self.assertEqual(asset.department, self.w.physics)
        self.assertEqual(asset.events.first().action, "Registered")

    def test_representative_cannot_register(self):
        with self.assertRaises(PermissionDenied):
            AssetService.register(self.w.physics_rep, dict(NEW_ASSET, category=self.w.lab))

    def test_coordinator_of_another_department_cannot_publish(self):
        asset = AssetService.register(self.w.eng_coord, dict(NEW_ASSET, category=self.w.lab))
        with self.assertRaises(PermissionDenied):
            AssetService.publish(self.w.physics_coord, asset)

    def test_publish_makes_all_units_available(self):
        asset = AssetService.register(self.w.eng_coord, dict(NEW_ASSET, category=self.w.lab))
        AssetService.publish(self.w.eng_coord, asset)
        self.assertEqual((asset.state, asset.available_quantity), (Asset.AVAILABLE, 4))

    def test_withdraw_is_refused_while_a_request_is_open(self):
        RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Teaching lab", date(2099, 1, 1))
        with self.assertRaises(BusinessRuleError):
            AssetService.withdraw(self.w.eng_coord, self.w.scope)

    def test_search_shows_only_published_assets_and_applies_filters(self):
        AssetService.register(self.w.eng_coord, dict(NEW_ASSET, category=self.w.lab))  # draft, hidden
        self.assertEqual(list(AssetService.search()), [self.w.scope])
        self.assertEqual(list(AssetService.search(keyword="oscillo")), [self.w.scope])
        self.assertEqual(list(AssetService.search(keyword="chair")), [])
        self.assertEqual(list(AssetService.search(condition="Poor")), [])
        self.assertEqual(list(AssetService.search(department=self.w.physics)), [])
        self.assertEqual(list(AssetService.search(category=self.w.lab, department=self.w.engineering)), [self.w.scope])
