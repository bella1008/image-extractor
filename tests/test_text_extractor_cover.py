import unittest

from src.text_extractor import (
    build_review_items,
    build_contact_table_rows,
    detect_cover_schema,
    detect_cover_region_type,
    merge_contact_table_regions,
    normalize_contact_table_fields,
)


def region(region_type, text, bbox=None):
    return {
        "region_order": 0,
        "region_type": region_type,
        "heading": None,
        "text": text,
        "bbox": bbox or [0, 0, 1, 1],
        "source": {
            "page_number": 1,
            "review_order": 1,
            "page_role": "cover",
            "row": 1,
            "column": 1,
            "cell_role": "cover",
            "cell_order": 1,
            "reading_direction": "LTR",
        },
        "style_summary": {},
        "markdown": text,
    }


def style_span(text, size, bold, y0, y1):
    return {
        "text": text,
        "bbox": (0, y0, 100, y1),
        "font": "TestFont",
        "size": size,
        "flags": 0,
        "bold_candidate": bold,
        "italic_candidate": False,
        "underline_candidate": False,
    }


class CoverExtractionTests(unittest.TestCase):
    def test_contact_table_keeps_multiple_website_regions(self):
        rows = build_contact_table_rows(
            [
                region("table_heading", "Samsung Service Center"),
                region("table_heading", "Website"),
                region("table_heading", "Address"),
                region("contact_value", "1-800-SAMSUNG (726-7864)"),
                region("website", "www.samsung.com/ca/support (English)"),
                region("website", "www.samsung.com/ca_fr/support (French)"),
                region("body", "Samsung Electronics Canada Inc. 2050 Derry Road West"),
                region("body", "Mississauga, Ontario L5N 0B9"),
                region("body", "Canada"),
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["Website"],
            "www.samsung.com/ca/support (English)\nwww.samsung.com/ca_fr/support (French)",
        )
        self.assertEqual(
            rows[0]["Address"],
            "Samsung Electronics Canada Inc. 2050 Derry Road West\n"
            "Mississauga, Ontario L5N 0B9\n"
            "Canada",
        )

    def test_contact_table_merge_uses_all_table_regions(self):
        merged = merge_contact_table_regions(
            [
                region("contact_heading", "Contact Samsung world wide", [0, 0, 1, 1]),
                region("table_heading", "Samsung Service Center", [0, 10, 1, 11]),
                region("table_heading", "Website", [2, 10, 3, 11]),
                region("body", "Address", [4, 10, 5, 11]),
                region("contact_value", "1-800-SAMSUNG (726-7864)", [0, 20, 1, 21]),
                region("website", "www.samsung.com/ca/support (English)", [2, 20, 3, 21]),
                region("website", "www.samsung.com/ca_fr/support (French)", [2, 30, 3, 31]),
                region("body", "Samsung Electronics Canada Inc.", [4, 20, 5, 21]),
            ]
        )

        contact_table = next(item for item in merged if item["region_type"] == "contact_table")
        self.assertIn("www.samsung.com/ca/support (English)", contact_table["text"])
        self.assertIn("www.samsung.com/ca_fr/support (French)", contact_table["text"])
        self.assertIn("Address", contact_table["table"]["columns"])
        self.assertEqual(
            contact_table["normalized_fields"],
            {
                "field_schema": "cover_contact_table.v1",
                "service_center": ["1-800-SAMSUNG (726-7864)"],
                "service_phone_numbers": ["1-800-SAMSUNG", "726-7864"],
                "websites": [
                    {
                        "url": "www.samsung.com/ca/support",
                        "label": "English",
                    },
                    {
                        "url": "www.samsung.com/ca_fr/support",
                        "label": "French",
                    },
                ],
                "address": ["Samsung Electronics Canada Inc."],
            },
        )

    def test_normalizes_contact_table_fields_for_comparison(self):
        fields = normalize_contact_table_fields(
            [
                {
                    "Samsung Service Center": "1-800-SAMSUNG (726-7864)",
                    "Website": "www.samsung.com/ca/support (English)\n"
                    "www.samsung.com/ca_fr/support (French)",
                    "Address": "Samsung Electronics Canada Inc.\nCanada",
                }
            ]
        )

        self.assertEqual(fields["field_schema"], "cover_contact_table.v1")
        self.assertEqual(fields["service_center"], ["1-800-SAMSUNG (726-7864)"])
        self.assertEqual(fields["service_phone_numbers"], ["1-800-SAMSUNG", "726-7864"])
        self.assertEqual(
            fields["websites"],
            [
                {"url": "www.samsung.com/ca/support", "label": "English"},
                {"url": "www.samsung.com/ca_fr/support", "label": "French"},
            ],
        )
        self.assertEqual(fields["address"], ["Samsung Electronics Canada Inc.", "Canada"])

    def test_detects_full_document_code(self):
        span = {"size": 8}

        self.assertEqual(detect_cover_region_type("BN68-25100A-00", span), "document_code")

    def test_embedded_registration_url_stays_body_text(self):
        span = {"size": 8}

        self.assertEqual(
            detect_cover_region_type(
                "To receive more complete service, please register your product at www.samsung.com",
                span,
            ),
            "body",
        )

    def test_detects_canadian_french_language_label(self):
        span = {"size": 8}

        self.assertEqual(detect_cover_region_type("C-FRA", span), "language_label")

    def test_detects_language_common_zc_a2_cover_schema(self):
        cells = [
            {
                "text": (
                    "C-FRA Guide d'utilisation simple "
                    "1-800-SAMSUNG Samsung Service Center Website "
                    "www.samsung.com/ca_fr/support"
                )
            }
        ]

        schema = detect_cover_schema(cells)

        self.assertEqual(schema["schema_id"], "ZC_A2_COVER")
        self.assertIn("contact_table", schema["required_regions"])
        self.assertIn("language_label", schema["required_regions"])

    def test_safety_precaution_heading_does_not_absorb_caution_body_start(self):
        items = build_review_items(
            "Safety Precaution\n"
            "Caution\n"
            ": Pulling, pushing, or climbing on the TV may cause the TV to fall.",
            language="ENG",
        )

        self.assertEqual(items[0]["kind"], "heading")
        self.assertEqual(items[0]["text"], "Safety Precaution")
        self.assertEqual(items[1]["kind"], "body")
        self.assertTrue(items[1]["text"].startswith("Caution : Pulling"))

    def test_short_ui_fragments_and_visual_notes_are_not_headings(self):
        for text in [
            "on",
            "or",
            "Yes",
            "Simple User Guide",
            "Do Not Touch This Screen!",
            "(The Frame only)",
        ]:
            with self.subTest(text=text):
                items = build_review_items(text, language="ENG")
                self.assertNotEqual(items[0]["kind"], "heading")

        visual_note_items = build_review_items("Do Not Touch\nThis Screen!", language="ENG")
        self.assertNotEqual(visual_note_items[0]["kind"], "heading")

    def test_split_auto_update_lines_are_ui_labels_not_headings(self):
        items = build_review_items("Auto\nUpdate", language="ENG")

        self.assertEqual(items[0]["kind"], "ui_label")
        self.assertEqual(items[0]["text"], "Auto Update")

    def test_settings_path_fragments_are_ui_labels_not_headings(self):
        items = build_review_items(
            "All Settings\n"
            "General & Privacy\n"
            "Power and\n"
            "Energy Saving\n"
            "Brightness Optimization",
            language="ENG",
        )

        self.assertEqual(items[0]["kind"], "ui_label")
        self.assertEqual(
            items[0]["text"],
            "All Settings General & Privacy Power and Energy Saving Brightness Optimization",
        )

    def test_large_bold_consecutive_lines_are_merged_as_heading(self):
        items = build_review_items(
            "Before Reading This\n"
            "Simple User Guide\n"
            "This TV comes with this Simple User Guide.",
            language="ENG",
            style_spans=[
                style_span("Before Reading This", size=16, bold=True, y0=10, y1=20),
                style_span("Simple User Guide", size=16, bold=True, y0=22, y1=32),
                style_span(
                    "This TV comes with this Simple User Guide.",
                    size=7,
                    bold=False,
                    y0=45,
                    y1=55,
                ),
            ],
        )

        self.assertEqual(items[0]["kind"], "heading")
        self.assertEqual(items[0]["text"], "Before Reading This Simple User Guide")
        self.assertEqual(items[1]["kind"], "body")

    def test_troubleshooting_inline_reference_is_not_heading_but_bold_topics_are(self):
        items = build_review_items(
            "Troubleshooting\n"
            "For more information, refer to \"\n"
            "Troubleshooting\n"
            "\" in the User\n"
            "Guide.\n"
            "The TV won’t turn on.\n"
            "Make sure that the power cord is securely plugged into the product.\n"
            "The screen dims.\n"
            "The Eco Sensor automatically adjusts the screen brightness.",
            language="ENG",
            style_spans=[
                style_span("Troubleshooting", size=13, bold=True, y0=10, y1=20),
                style_span("For more information, refer to \"", size=7, bold=False, y0=30, y1=40),
                style_span("Troubleshooting", size=7, bold=True, y0=42, y1=52),
                style_span("\" in the User", size=7, bold=False, y0=54, y1=64),
                style_span("Guide.", size=7, bold=False, y0=66, y1=76),
                style_span("The TV won’t turn on.", size=9, bold=True, y0=90, y1=102),
                style_span(
                    "Make sure that the power cord is securely plugged into the product.",
                    size=7,
                    bold=False,
                    y0=112,
                    y1=122,
                ),
                style_span("The screen dims.", size=9, bold=True, y0=134, y1=146),
                style_span(
                    "The Eco Sensor automatically adjusts the screen brightness.",
                    size=7,
                    bold=False,
                    y0=156,
                    y1=166,
                ),
            ],
        )

        headings = [item["text"] for item in items if item["kind"] == "heading"]

        self.assertEqual(headings, ["Troubleshooting", "The TV won’t turn on.", "The screen dims."])


if __name__ == "__main__":
    unittest.main()
