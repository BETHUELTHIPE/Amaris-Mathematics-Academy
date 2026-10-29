"""Offline contract checks for fail-closed production ruleset enforcement."""
import copy
import unittest

from verify_frontend_branch_ruleset import ProtectionMissing, check_rulesets


class RulesetTests(unittest.TestCase):
    def setUp(self):
        self.detail = {
            "id": 42,
            "target": "branch",
            "enforcement": "active",
            "conditions": {
                "ref_name": {
                    "include": ["refs/heads/render-live-current-20260918"],
                    "exclude": [],
                }
            },
            "bypass_actors": [],
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_approving_review_count": 1,
                        "dismiss_stale_reviews_on_push": True,
                        "required_review_thread_resolution": True,
                    },
                },
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [
                            {"context": "Candidate TypeScript, lint, auth, booking, and dependency checks"},
                            {"context": "Production branch ruleset enforcement active"},
                        ],
                    },
                },
                {"type": "non_fast_forward"},
            ],
        }

    def verify(self, item):
        check_rulesets(
            [{"id": item["id"], "target": item["target"], "enforcement": item["enforcement"]}],
            {item["id"]: item},
        )

    def test_complete_rule_passes(self):
        self.verify(self.detail)

    def test_no_approval_is_a_release_blocker(self):
        item = copy.deepcopy(self.detail)
        item["rules"] = [r for r in item["rules"] if r["type"] != "pull_request"]
        with self.assertRaises(ProtectionMissing):
            self.verify(item)

    def test_owner_configured_zero_reviewers_still_requires_strict_checks(self):
        item = copy.deepcopy(self.detail)
        item["rules"][0]["parameters"]["required_approving_review_count"] = 0
        item["rules"][0]["parameters"]["required_review_thread_resolution"] = False
        item["rules"][0]["parameters"]["require_last_push_approval"] = False
        self.verify(item)

    def test_missing_review_count_is_rejected(self):
        item = copy.deepcopy(self.detail)
        del item["rules"][0]["parameters"]["required_approving_review_count"]
        with self.assertRaises(ProtectionMissing):
            self.verify(item)

    def test_missing_stale_review_dismissal_is_blocked(self):
        item = copy.deepcopy(self.detail)
        item["rules"][0]["parameters"]["dismiss_stale_reviews_on_push"] = False
        with self.assertRaises(ProtectionMissing):
            self.verify(item)

    def test_absent_checks_and_non_strict_checks_are_blocked(self):
        item = copy.deepcopy(self.detail)
        item["rules"][1]["parameters"]["required_status_checks"] = []
        with self.assertRaises(ProtectionMissing):
            self.verify(item)
        item = copy.deepcopy(self.detail)
        item["rules"][1]["parameters"]["strict_required_status_checks_policy"] = False
        with self.assertRaises(ProtectionMissing):
            self.verify(item)

    def test_ruleset_for_other_branch_not_accepted(self):
        item = copy.deepcopy(self.detail)
        item["conditions"]["ref_name"]["include"] = ["refs/heads/main"]
        with self.assertRaises(ProtectionMissing):
            self.verify(item)

    def test_inactive_bypass_and_force_push_are_blocked(self):
        item = copy.deepcopy(self.detail)
        item["enforcement"] = "disabled"
        with self.assertRaises(ProtectionMissing):
            self.verify(item)
        item = copy.deepcopy(self.detail)
        item["bypass_actors"] = [{"actor_id": 1, "actor_type": "Team"}]
        with self.assertRaises(ProtectionMissing):
            self.verify(item)
        item = copy.deepcopy(self.detail)
        item["rules"] = [r for r in item["rules"] if r["type"] != "non_fast_forward"]
        with self.assertRaises(ProtectionMissing):
            self.verify(item)


if __name__ == "__main__":
    unittest.main()
