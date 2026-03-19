import unittest

from autoqa_shared.explorer import ExplorationEngine


class ExplorerSamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ExplorationEngine(db=None)

    def test_repeated_edit_actions_share_a_sampling_group(self) -> None:
        elements = [
            {
                "displayLabel": "Edit John",
                "tag": "button",
                "role": "button",
                "category": "edit",
                "disabled": False,
                "href": "",
                "formSignature": "",
            },
            {
                "displayLabel": "Edit Mary",
                "tag": "button",
                "role": "button",
                "category": "edit",
                "disabled": False,
                "href": "",
                "formSignature": "",
            },
        ]

        counts = self.engine._sample_group_counts("/users", elements)
        group = self.engine._sample_group_for_element("/users", elements[0], "edit")

        self.assertEqual(counts[group], 2)
        self.assertTrue(self.engine._should_skip_due_to_sampling(group, counts, {group: 1}))

    def test_repeated_submit_controls_share_a_sampling_group(self) -> None:
        pending = {
            "displayLabel": "Save Customer",
            "label": "save customer",
            "form_label": "Customer Form",
            "tag": "button",
            "role": "button",
            "category": "form",
            "disabled": False,
            "href": "",
            "isSubmitControl": True,
            "formSignature": "form|customer|post|2",
        }
        elements = [dict(pending), dict(pending)]

        counts = self.engine._sample_group_counts("/customers", elements)
        group = self.engine._sample_group_for_submit("/customers", pending)

        self.assertEqual(counts[group], 2)
        self.assertTrue(self.engine._should_skip_due_to_sampling(group, counts, {group: 1}))


if __name__ == "__main__":
    unittest.main()
