"""Tests for requests, approvals and transfers (C4, C5) and their permission checks (C1)."""
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from accounts.common import BusinessRuleError
from accounts.models import Notification, User
from accounts.sample_data import build_sample_world
from assets.models import Asset

from .models import Request, Transfer
from .services import ApprovalService, RequestService, TransferService

NEXT_MONTH = date.today() + timedelta(days=30)


class RequestFlowTests(TestCase):
    def setUp(self):
        self.w = build_sample_world(units=2)

    def submit_and_release(self, quantity=2, requester=None):
        req = RequestService.submit(requester or self.w.physics_rep, self.w.scope, quantity, "Teaching lab", NEXT_MONTH)
        ApprovalService.release(self.w.eng_coord, req)
        return req

    def test_full_flow_moves_the_asset_to_the_receiving_department(self):
        req = self.submit_and_release(quantity=2)
        ApprovalService.approve(self.w.admin, req)
        TransferService.hand_over(self.w.eng_coord, req)
        TransferService.confirm_receipt(self.w.physics_rep, req, "Good")

        req.refresh_from_db()
        moved = req.transfer.asset
        self.assertEqual(req.state, Request.COMPLETED)
        self.assertEqual(req.transfer.state, Transfer.RECEIVED)
        self.assertEqual(moved.state, Asset.IN_USE)
        self.assertEqual(moved.department, self.w.physics)
        states = [(e.old_state, e.new_state) for e in moved.events.all()]
        self.assertIn(("Available", "Reserved"), states)
        self.assertIn(("Reserved", "In Transfer"), states)
        self.assertIn(("In Transfer", "In Use"), states)

    def test_notifications_are_sent_at_each_step(self):
        req = self.submit_and_release(quantity=2)
        ApprovalService.approve(self.w.admin, req)
        TransferService.hand_over(self.w.eng_coord, req)
        TransferService.confirm_receipt(self.w.physics_rep, req, "Good")
        events = set(Notification.objects.values_list("event_type", flat=True))
        for event in ["Request made", "Released", "Approved", "Handed over", "Received"]:
            self.assertIn(event, events)
        self.assertTrue(self.w.eng_coord.notifications.filter(event_type="Request made").exists())

    def test_partial_approval_splits_the_reserved_units_into_a_linked_record(self):
        req = self.submit_and_release(quantity=1)
        ApprovalService.approve(self.w.admin, req)
        self.w.scope.refresh_from_db()
        part = req.transfer.asset
        self.assertEqual((self.w.scope.quantity, self.w.scope.available_quantity, self.w.scope.state), (1, 1, "Available"))
        self.assertEqual((part.quantity, part.state, part.parent), (1, "Reserved", self.w.scope))

    def test_requester_cannot_approve_their_own_request(self):
        req = self.submit_and_release()
        # Even if the requester later becomes an Administrator, the check compares user IDs.
        self.w.physics_rep.role = User.ADMINISTRATOR
        self.w.physics_rep.save()
        with self.assertRaisesMessage(BusinessRuleError, "You submitted this request"):
            ApprovalService.approve(self.w.physics_rep, req)

    def test_releaser_cannot_also_approve(self):
        req = self.submit_and_release()
        self.w.eng_coord.role = User.ADMINISTRATOR
        self.w.eng_coord.save()
        with self.assertRaisesMessage(BusinessRuleError, "You released this request"):
            ApprovalService.approve(self.w.eng_coord, req)
        req.refresh_from_db()
        self.w.scope.refresh_from_db()
        self.assertEqual(req.state, Request.RELEASED)
        self.assertEqual(self.w.scope.available_quantity, 2)  # nothing was reserved

    def test_last_unit_can_never_go_to_two_requests(self):
        w = self.w
        first = self.submit_and_release(quantity=2)
        second = self.submit_and_release(quantity=2, requester=w.fac_rep)
        # `second` was loaded before the first approval, so its asset object is out of date
        # (it still says 2 free units). The conditional UPDATE checks the database instead.
        ApprovalService.approve(w.admin, first)
        with self.assertRaisesMessage(BusinessRuleError, "Not enough units"):
            ApprovalService.approve(w.admin, second)
        w.scope.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(w.scope.available_quantity, 0)
        self.assertEqual(second.state, Request.RELEASED)
        self.assertEqual(Transfer.objects.count(), 1)

    def test_decline_needs_a_reason_and_ends_the_request(self):
        req = RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Lab", NEXT_MONTH)
        with self.assertRaises(BusinessRuleError):
            ApprovalService.decline(self.w.eng_coord, req, "  ")
        ApprovalService.decline(self.w.eng_coord, req, "Still needed by Engineering")
        req.refresh_from_db()
        self.assertEqual((req.state, req.reason), (Request.REJECTED, "Still needed by Engineering"))
        # Nothing runs after a reject.
        with self.assertRaises(BusinessRuleError):
            ApprovalService.release(self.w.eng_coord, req)
        with self.assertRaises(BusinessRuleError):
            ApprovalService.approve(self.w.admin, req)

    def test_rejection_by_administrator_ends_the_request_without_reserving(self):
        req = self.submit_and_release()
        ApprovalService.reject(self.w.admin, req, "Budget freeze")
        with self.assertRaises(BusinessRuleError):
            ApprovalService.approve(self.w.admin, req)
        self.w.scope.refresh_from_db()
        self.assertEqual(self.w.scope.available_quantity, 2)

    def test_cancel_after_approval_puts_the_units_back(self):
        req = self.submit_and_release(quantity=2)
        ApprovalService.approve(self.w.admin, req)
        RequestService.cancel(self.w.physics_rep, req, "Plans changed")
        self.w.scope.refresh_from_db()
        req.refresh_from_db()
        self.assertEqual((self.w.scope.state, self.w.scope.available_quantity), (Asset.AVAILABLE, 2))
        self.assertEqual(req.transfer.state, Transfer.CANCELLED)

    def test_cannot_request_more_units_than_are_free(self):
        with self.assertRaises(BusinessRuleError):
            RequestService.submit(self.w.physics_rep, self.w.scope, 3, "Lab", NEXT_MONTH)

    def test_a_department_cannot_request_its_own_asset(self):
        # The oscilloscope belongs to Engineering, so moving it to Engineering would change nothing (C5).
        with self.assertRaisesMessage(BusinessRuleError, "This asset already belongs to your department"):
            RequestService.submit(self.w.eng_rep, self.w.scope, 1, "Lab", NEXT_MONTH)
        self.client.force_login(self.w.eng_rep)
        self.assertNotContains(self.client.get(reverse("asset_detail", args=[self.w.scope.pk])), "Request this asset")
        self.client.force_login(self.w.physics_rep)
        self.assertContains(self.client.get(reverse("asset_detail", args=[self.w.scope.pk])), "Request this asset")

    def test_needed_by_date_cannot_be_in_the_past(self):
        with self.assertRaises(BusinessRuleError):
            RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Lab", date.today() - timedelta(days=1))


class PermissionTests(TestCase):
    """The server refuses actions by the wrong role or department (C1)."""

    def setUp(self):
        self.w = build_sample_world()
        self.req = RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Lab", NEXT_MONTH)

    def test_only_representatives_can_submit(self):
        with self.assertRaises(PermissionDenied):
            RequestService.submit(self.w.physics_coord, self.w.scope, 1, "Lab", NEXT_MONTH)

    def test_representative_cannot_release(self):
        with self.assertRaises(PermissionDenied):
            ApprovalService.release(self.w.physics_rep, self.req)

    def test_coordinator_of_another_department_cannot_release(self):
        with self.assertRaises(PermissionDenied):
            ApprovalService.release(self.w.physics_coord, self.req)

    def test_coordinator_cannot_approve(self):
        ApprovalService.release(self.w.eng_coord, self.req)
        with self.assertRaises(PermissionDenied):
            ApprovalService.approve(self.w.eng_coord, self.req)

    def test_only_the_receiving_department_can_confirm_receipt(self):
        ApprovalService.release(self.w.eng_coord, self.req)
        ApprovalService.approve(self.w.admin, self.req)
        TransferService.hand_over(self.w.eng_coord, self.req)
        with self.assertRaises(PermissionDenied):
            TransferService.confirm_receipt(self.w.eng_rep, self.req, "Good")

    def test_only_the_requester_can_cancel(self):
        with self.assertRaises(PermissionDenied):
            RequestService.cancel(self.w.fac_rep, self.req)


class PermissionViewTests(TestCase):
    """The same checks through the web pages: a forged POST gets HTTP 403."""

    def setUp(self):
        self.w = build_sample_world()
        self.req = RequestService.submit(self.w.physics_rep, self.w.scope, 1, "Lab", NEXT_MONTH)

    def test_representative_posting_to_approve_gets_403(self):
        self.client.force_login(self.w.physics_rep)
        response = self.client.post(reverse("request_approve", args=[self.req.pk]))
        self.assertEqual(response.status_code, 403)

    def test_representative_cannot_open_the_register_asset_page(self):
        self.client.force_login(self.w.physics_rep)
        self.assertEqual(self.client.get(reverse("asset_create")).status_code, 403)

    def test_other_department_cannot_see_the_request(self):
        self.client.force_login(self.w.fac_rep)
        self.assertEqual(self.client.get(reverse("request_detail", args=[self.req.pk])).status_code, 403)

    def test_owner_department_can_see_the_request(self):
        self.client.force_login(self.w.eng_coord)
        self.assertEqual(self.client.get(reverse("request_detail", args=[self.req.pk])).status_code, 200)

    def test_self_approval_shows_a_clear_error_on_the_page(self):
        ApprovalService.release(self.w.eng_coord, self.req)
        self.w.eng_coord.role = User.ADMINISTRATOR
        self.w.eng_coord.save()
        self.client.force_login(self.w.eng_coord)
        response = self.client.post(reverse("request_approve", args=[self.req.pk]), follow=True)
        self.assertContains(response, "You released this request")
