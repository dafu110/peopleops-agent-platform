import unittest

from core.auth import Principal, has_permission
from core.database import list_interview_actions
from core.matcher import normalize_analysis
from core.security import redact_pii, verify_password
from core.tools import schedule_interview
from core.workflow import keyword_intent


class WorkflowIntentTests(unittest.TestCase):
    def test_keyword_intent_routes_action(self):
        self.assertEqual(keyword_intent("帮我给张三发送明天下午两点的面试邀约"), "action_tool")

    def test_keyword_intent_routes_resume(self):
        self.assertEqual(keyword_intent("评估一下这份简历和 JD 的匹配度"), "resume")

    def test_keyword_intent_routes_rag(self):
        self.assertEqual(keyword_intent("年假制度是什么？"), "rag")


class MatcherNormalizationTests(unittest.TestCase):
    def test_normalize_analysis_clamps_score_and_lists(self):
        result = normalize_analysis({"score": 120, "pros": "Python 经验", "cons": ["缺少管理经验"]})

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["pros"], ["Python 经验"])
        self.assertEqual(result["cons"], ["缺少管理经验"])


class SecurityTests(unittest.TestCase):
    def test_redact_pii_masks_common_identifiers(self):
        text = "候选人电话 13812345678，邮箱 test@example.com，身份证 110101199003071234"

        redacted = redact_pii(text)

        self.assertNotIn("13812345678", redacted)
        self.assertNotIn("test@example.com", redacted)
        self.assertNotIn("110101199003071234", redacted)

    def test_verify_password_allows_empty_expected_password(self):
        self.assertTrue(verify_password("", None))
        self.assertTrue(verify_password("secret", "secret"))
        self.assertFalse(verify_password("wrong", "secret"))


class ToolExecutionTests(unittest.TestCase):
    def test_schedule_interview_returns_auditable_local_result(self):
        result = schedule_interview("张三", "明天下午两点")

        self.assertEqual(result.tool_name, "schedule_interview")
        self.assertIn(result.status, {"DRY_RUN", "PERSISTED", "SUCCESS"})
        self.assertIn("execution_mode", result.metadata)
        self.assertGreaterEqual(len(list_interview_actions(limit=1)), 1)


class AuthorizationTests(unittest.TestCase):
    def test_role_permissions(self):
        self.assertTrue(has_permission(Principal("alice", "admin"), "users"))
        self.assertTrue(has_permission(Principal("bob", "hrbp"), "tool"))
        self.assertFalse(has_permission(Principal("viewer", "viewer"), "tool"))


if __name__ == "__main__":
    unittest.main()
