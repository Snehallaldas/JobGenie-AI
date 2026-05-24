import json
import unittest
from unittest.mock import patch

from app.routers.interview import build_score_card
from app.services.mistral_service import _is_low_quality_answer, evaluate_answer


class EvaluateAnswerTests(unittest.TestCase):
    def test_short_keyword_answer_is_not_low_quality(self):
        self.assertFalse(_is_low_quality_answer("I use Python.", ["Python"]))

    def test_vague_answer_is_low_quality(self):
        self.assertTrue(_is_low_quality_answer("Yes, I can do it."))

    def test_gibberish_answer_is_low_quality(self):
        self.assertTrue(_is_low_quality_answer("abc def ghi jkl mno pqr stu vwx yz"))

    @patch("app.services.mistral_service._complete_chat")
    def test_short_keyword_answer_is_evaluated(self, mock_complete_chat):
        mock_complete_chat.return_value = json.dumps(
            {
                "relevance_score": 8,
                "technical_depth_score": 7,
                "clarity_score": 8,
                "overall_score": 8,
                "feedback": "Good answer.",
                "strengths": ["Clear and relevant"],
                "improvements": ["Add one more example"],
                "keywords_used": ["Python"],
            }
        )

        result = evaluate_answer(
            question="How do you handle backend APIs?",
            answer="I use Python.",
            expected_keywords=["Python"],
            job_title="Backend Engineer",
        )

        self.assertEqual(result["overall_score"], 8)
        self.assertNotEqual(result["feedback"], "Answer appears incomplete, random, or unrelated. Please provide a meaningful response.")

    def test_build_score_card_handles_missing_evaluation_payload(self):
        score_card = build_score_card(
            [
                {
                    "question_index": 0,
                    "question": "Tell me about yourself.",
                    "evaluation": None,
                }
            ],
            1,
        )

        self.assertEqual(score_card["overall_score"], 0)
        self.assertEqual(score_card["score_percentage"], 0)
        self.assertEqual(score_card["category_scores"], {
            "relevance": 0,
            "technical_depth": 0,
            "clarity": 0,
        })
        self.assertEqual(score_card["question_scores"][0]["overall_score"], 0)
        self.assertEqual(score_card["question_scores"][0]["feedback"], "")
        self.assertNotIn("NaN", json.dumps(score_card))


if __name__ == "__main__":
    unittest.main()
