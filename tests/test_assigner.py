"""Tests for Employee ID assignment logic and chronological sorting."""

from datetime import datetime

from gws_employeeid.assigner import (
    find_max_existing_numeric_id,
    plan_assignments,
    sort_users_by_creation_time,
)
from gws_employeeid.models.config import AssignmentConfig
from gws_employeeid.models.user import WorkspaceUser


def _make_user(
    email: str,
    created_iso: str | None = None,
    emp_id: str | None = None,
    suspended: bool = False,
) -> WorkspaceUser:
    dt = None
    if created_iso:
        dt = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
    return WorkspaceUser(
        primary_email=email,
        full_name=email.split("@")[0].title(),
        creation_time=dt,
        employee_id=emp_id,
        suspended=suspended,
    )


class TestFindMaxExistingNumericId:
    """Tests for scanning existing numeric IDs."""

    def test_finds_max_plain_digits(self) -> None:
        users = [
            _make_user("a@test.com", emp_id="101"),
            _make_user("b@test.com", emp_id="500"),
            _make_user("c@test.com", emp_id="250"),
            _make_user("d@test.com", emp_id=None),
        ]
        assert find_max_existing_numeric_id(users) == 500

    def test_finds_max_with_prefix(self) -> None:
        users = [
            _make_user("a@test.com", emp_id="EMP-010"),
            _make_user("b@test.com", emp_id="EMP-095"),
            _make_user("c@test.com", emp_id="OTHER-999"),
        ]
        assert find_max_existing_numeric_id(users, prefix="EMP-") == 95

    def test_returns_none_when_no_numeric_ids(self) -> None:
        users = [
            _make_user("a@test.com", emp_id="ABC"),
            _make_user("b@test.com", emp_id=None),
        ]
        assert find_max_existing_numeric_id(users) is None


class TestSortUsersByCreationTime:
    """Tests for chronological ordering."""

    def test_sorts_oldest_first(self) -> None:
        u1 = _make_user("u1@test.com", "2022-01-01T00:00:00Z")
        u2 = _make_user("u2@test.com", "2021-01-01T00:00:00Z")
        u3 = _make_user("u3@test.com", "2023-01-01T00:00:00Z")

        sorted_users = sort_users_by_creation_time([u1, u2, u3])
        assert [u.primary_email for u in sorted_users] == [
            "u2@test.com",
            "u1@test.com",
            "u3@test.com",
        ]

    def test_places_none_creation_time_first(self) -> None:
        u1 = _make_user("u1@test.com", "2022-01-01T00:00:00Z")
        u2 = _make_user("u2@test.com", None)

        sorted_users = sort_users_by_creation_time([u1, u2])
        assert sorted_users[0].primary_email == "u2@test.com"

    def test_tie_breaks_by_email(self) -> None:
        u1 = _make_user("bob@test.com", "2022-01-01T00:00:00Z")
        u2 = _make_user("alice@test.com", "2022-01-01T00:00:00Z")

        sorted_users = sort_users_by_creation_time([u1, u2])
        assert [u.primary_email for u in sorted_users] == [
            "alice@test.com",
            "bob@test.com",
        ]


class TestPlanAssignments:
    """Tests for computing ID assignment plans."""

    def test_leaves_existing_populated_alone(self) -> None:
        u_old_has_id = _make_user(
            "alice@test.com", "2020-01-01T00:00:00Z", emp_id="1001"
        )
        u_new_no_id = _make_user("bob@test.com", "2021-01-01T00:00:00Z", emp_id=None)

        config = AssignmentConfig()
        plan = plan_assignments([u_old_has_id, u_new_no_id], config)

        assert len(plan) == 2

        alice_item = next(p for p in plan if p.user.primary_email == "alice@test.com")
        assert alice_item.action == "skip_existing"
        assert alice_item.old_employee_id == "1001"
        assert alice_item.new_employee_id is None

        bob_item = next(p for p in plan if p.user.primary_email == "bob@test.com")
        assert bob_item.action == "assign"
        # Auto-detects 1001 as highest existing, so bob gets 1002!
        assert bob_item.new_employee_id == "1002"

    def test_assigns_incremental_based_on_creation_time(self) -> None:
        u_new = _make_user("charlie@test.com", "2023-01-01T00:00:00Z")
        u_old = _make_user("alice@test.com", "2021-01-01T00:00:00Z")
        u_mid = _make_user("bob@test.com", "2022-01-01T00:00:00Z")

        config = AssignmentConfig(start_id=100)
        plan = plan_assignments([u_new, u_old, u_mid], config)

        assignments = {p.user.primary_email: p.new_employee_id for p in plan}
        assert assignments["alice@test.com"] == "100"
        assert assignments["bob@test.com"] == "101"
        assert assignments["charlie@test.com"] == "102"

    def test_avoids_collisions_with_existing_ids(self) -> None:
        # Alice already has ID 101
        u_alice = _make_user("alice@test.com", "2020-01-01T00:00:00Z", emp_id="101")
        # Bob created in 2021
        u_bob = _make_user("bob@test.com", "2021-01-01T00:00:00Z")
        # Charlie created in 2022
        u_charlie = _make_user("charlie@test.com", "2022-01-01T00:00:00Z")

        # Explicitly starting at 100:
        # Bob gets 100.
        # Next is 101, but Alice has 101, so Charlie should get 102!
        config = AssignmentConfig(start_id=100)
        plan = plan_assignments([u_alice, u_bob, u_charlie], config)

        assignments = {p.user.primary_email: p.new_employee_id for p in plan}
        assert assignments["alice@test.com"] is None
        assert assignments["bob@test.com"] == "100"
        assert assignments["charlie@test.com"] == "102"

    def test_prefix_and_zero_padding(self) -> None:
        u1 = _make_user("a@test.com", "2021-01-01T00:00:00Z")
        u2 = _make_user("b@test.com", "2022-01-01T00:00:00Z")

        config = AssignmentConfig(prefix="EMP-", pad_width=4, start_id=1)
        plan = plan_assignments([u1, u2], config)

        assert plan[0].new_employee_id == "EMP-0001"
        assert plan[1].new_employee_id == "EMP-0002"

    def test_exclude_suspended_users(self) -> None:
        u_active = _make_user("active@test.com", "2021-01-01T00:00:00Z")
        u_suspended = _make_user(
            "suspended@test.com", "2020-01-01T00:00:00Z", suspended=True
        )

        config = AssignmentConfig(exclude_suspended=True, start_id=1)
        plan = plan_assignments([u_active, u_suspended], config)

        suspended_item = next(
            p for p in plan if p.user.primary_email == "suspended@test.com"
        )
        assert suspended_item.action == "skip_suspended"
        assert suspended_item.new_employee_id is None

        active_item = next(p for p in plan if p.user.primary_email == "active@test.com")
        assert active_item.action == "assign"
        assert active_item.new_employee_id == "1"

    def test_force_overwrites_existing_ids(self) -> None:
        u_old = _make_user("alice@test.com", "2020-01-01T00:00:00Z", emp_id="OLD-999")
        u_new = _make_user("bob@test.com", "2021-01-01T00:00:00Z", emp_id="OLD-111")

        config = AssignmentConfig(force=True, start_id=1)
        plan = plan_assignments([u_old, u_new], config)

        assert plan[0].action == "assign"
        assert plan[0].new_employee_id == "1"
        assert plan[1].action == "assign"
        assert plan[1].new_employee_id == "2"
