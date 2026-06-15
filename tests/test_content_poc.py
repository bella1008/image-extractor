import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from src.content_poc import (
    build_content_markdown,
    build_content_poc_payload,
    make_output_paths,
    write_content_poc_outputs,
)


class ContentPocTests(unittest.TestCase):
    def test_make_output_paths_uses_source_token_and_language(self):
        paths = make_output_paths(
            Path("outputs/content_poc"),
            "BN68-20834D-00",
            "ZC_L02",
            "ENG",
            timestamp="260615_2130",
        )

        self.assertEqual(paths.root, Path("outputs/content_poc/BN68-20834D-00/ZC_L02_ENG"))
        self.assertEqual(paths.json_path.name, "content_poc.json")
        self.assertEqual(paths.markdown_path.name, "content_blocks.md")
        self.assertEqual(
            paths.xlsx_path.name,
            "BN68-20834D-00_ZC_L02_ENG_260615_2130_content_review.xlsx",
        )
        self.assertEqual(paths.crop_dir.name, "crops")

    def test_build_content_payload_excludes_cover_cells_and_flags_risky_blocks(self):
        payload = build_content_poc_payload(minimal_extracted_payload())

        self.assertEqual(payload["summary"]["cell_count"], 2)
        self.assertEqual(payload["summary"]["block_count"], 3)
        self.assertEqual(payload["summary"]["manual_review_block_count"], 2)
        self.assertEqual(
            [block["block_type"] for block in payload["blocks"]],
            ["heading", "safety_symbol_table", "navigation_ui"],
        )
        self.assertTrue(payload["blocks"][1]["manual_review_required"])
        self.assertTrue(payload["blocks"][1]["image_crop_required"])
        self.assertEqual(payload["blocks"][1]["source"]["cell_role"], "content")

    def test_build_content_markdown_groups_blocks_by_section(self):
        payload = build_content_poc_payload(minimal_extracted_payload())

        markdown = build_content_markdown(payload)

        self.assertIn("# Content POC", markdown)
        self.assertIn("## 01. Warning! Important Safety Instructions", markdown)
        self.assertIn("### Block 002 - safety_symbol_table", markdown)
        self.assertIn("manual_review_required: `true`", markdown)

    def test_write_content_outputs_writes_review_workbook(self):
        payload = build_content_poc_payload(minimal_extracted_payload())

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = make_output_paths(
                Path(temp_dir),
                "BN68-20834D-00",
                "ZC_L02",
                "ENG",
                timestamp="260615_2130",
            )
            written = write_content_poc_outputs(payload, paths)

            self.assertTrue(written["json_path"].exists())
            self.assertTrue(written["markdown_path"].exists())
            self.assertTrue(written["xlsx_path"].exists())
            saved = json.loads(written["json_path"].read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"]["block_count"], 3)

            workbook = load_workbook(written["xlsx_path"])
            self.assertEqual(
                workbook.sheetnames,
                [
                    "Content Summary",
                    "Content Review",
                    "Safety Tables",
                    "Navigation UI",
                    "Spec Tables",
                    "Regulatory Notes",
                ],
            )
            self.assertEqual(
                [cell.value for cell in workbook["Content Review"][1]],
                [
                    "block_order",
                    "section_heading",
                    "block_type",
                    "manual_review_required",
                    "lines_text",
                    "sentence_count",
                    "crop_path",
                    "page",
                    "cell_order",
                ],
            )
            self.assertEqual(
                [cell.value for cell in workbook["Safety Tables"][1]],
                [
                    "block_order",
                    "section_heading",
                    "row_order",
                    "symbol_key",
                    "label",
                    "lines_text",
                ],
            )

    def test_embedded_ventilation_heading_is_split_from_previous_bullet(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_embedded_heading())

        headings = [block["text"] for block in payload["blocks"] if block["block_type"] == "heading"]
        self.assertIn("Providing proper ventilation for your TV", headings)
        ventilation_block = next(
            block
            for block in payload["blocks"]
            if block["section_heading"] == "Providing proper ventilation for your TV"
            and block["block_type"] == "bullet"
        )
        self.assertTrue(ventilation_block["text"].startswith("When installing the TV"))
        self.assertEqual(
            [sentence["text"] for sentence in ventilation_block["sentences"]],
            [
                "When installing the TV, ensure proper ventilation.",
                "Failing to maintain proper ventilation may result in a fire.",
            ],
        )
        self.assertEqual(
            ventilation_block["lines"],
            [
                "When installing the TV, ensure proper ventilation.",
                "Failing to maintain proper ventilation may result in a fire.",
            ],
        )

    def test_caution_warning_row_is_part_of_safety_symbol_table(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_safety_warning_row())

        table_blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "Warning! Important Safety Instructions"
            and block["block_type"] == "safety_symbol_table"
        ]
        self.assertEqual(len(table_blocks), 2)
        self.assertTrue(table_blocks[0]["text"].startswith("CAUTION RISK OF ELECTRIC SHOCK"))
        self.assertEqual(table_blocks[0]["rows"][0]["symbol_key"], "caution_warning")
        self.assertEqual(table_blocks[0]["rows"][0]["label"], "CAUTION")
        self.assertNotIn("description", table_blocks[0]["rows"][0])
        self.assertEqual(
            table_blocks[0]["rows"][0]["lines"],
            [
                "CAUTION",
                "RISK OF ELECTRIC SHOCK.",
                "DO NOT OPEN.",
            ],
        )

    def test_safety_symbol_table_accepts_caution_instruction_row_from_next_cell(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_split_safety_instruction_row())

        table_blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "Warning! Important Safety Instructions"
            and block["block_type"] == "safety_symbol_table"
        ]

        self.assertEqual(len(table_blocks), 2)
        self.assertEqual(
            table_blocks[1]["lines"],
            [
                "Caution.",
                "Consult instructions for use: This symbol instructs the user to consult the Simple User Guide for further safety related information.",
            ],
        )

    def test_additional_embedded_headings_are_split_from_body_text(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_additional_headings())

        headings = [block["text"] for block in payload["blocks"] if block["block_type"] == "heading"]

        self.assertIn("Preventing the TV from falling", headings)
        self.assertIn("Precautions when installing the TV with a stand", headings)
        self.assertIn("How to turn on and off the Microphone", headings)
        self.assertNotIn("(The Frame only)", headings)

    def test_quoted_heading_reference_is_not_split_as_embedded_heading(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_quoted_heading_reference())

        headings = [block["text"] for block in payload["blocks"] if block["block_type"] == "heading"]

        self.assertEqual(headings, ["Safety Precaution"])
        self.assertIn('"Preventing the TV from falling."', payload["blocks"][1]["text"])

    def test_short_precautions_heading_is_normalized_to_full_heading(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_short_precautions_heading())

        headings = [block["text"] for block in payload["blocks"] if block["block_type"] == "heading"]

        self.assertIn("Precautions when installing the TV with a stand", headings)
        self.assertNotIn("Precautions when installing the TV with a", headings)

    def test_falling_tv_procedure_is_split_into_note_and_numbered_steps(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_falling_tv_procedure())

        section_blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "Preventing the TV from falling"
        ]

        self.assertEqual(section_blocks[1]["block_type"], "procedure_note")
        self.assertEqual(section_blocks[1]["text"], "Wall-anchor (not supplied)")
        step_blocks = [block for block in section_blocks if block["block_type"] == "numbered_step"]
        self.assertTrue(all("step_order" not in block for block in step_blocks))
        self.assertTrue(
            step_blocks[0]["text"].startswith(
                "1. Using the appropriate screws, firmly fasten a set of brackets to the wall."
            )
        )
        self.assertEqual(
            step_blocks[0]["lines"],
            [
                "1. Using the appropriate screws, firmly fasten a set of brackets to the wall.",
                "Confirm that the screws are firmly attached to the wall.",
                "You may need additional material such as wall anchors depending on the type of wall.",
            ],
        )
        self.assertTrue(
            step_blocks[1]["text"].startswith(
                "2. Using the appropriately sized screws, firmly fasten a set of brackets to the TV."
            )
        )
        self.assertTrue(
            step_blocks[2]["text"].startswith(
                "3. Connect the brackets fixed to the TV and the brackets fixed to the wall"
            )
        )

    def test_falling_tv_procedure_split_handles_bullet_fragments(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_fragmented_falling_tv_procedure())

        section_blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "Preventing the TV from falling"
        ]
        step_blocks = [block for block in section_blocks if block["block_type"] == "numbered_step"]

        self.assertEqual(section_blocks[1]["block_type"], "procedure_note")
        self.assertEqual(len(step_blocks), 3)
        self.assertEqual(
            step_blocks[0]["lines"],
            [
                "1. Using the appropriate screws, firmly fasten a set of brackets to the wall.",
                "Confirm that the screws are firmly attached to the wall.",
                "You may need additional material such as wall anchors depending on the type of wall.",
            ],
        )
        self.assertIn(
            "For the screw specifications, refer to the standard screw part",
            step_blocks[1]["text"],
        )
        self.assertIn(
            "Connect the string so that the brackets fixed to the wall",
            step_blocks[2]["text"],
        )
        self.assertNotIn("stand properly", step_blocks[2]["text"])

    def test_caution_label_is_merged_with_following_body(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_inline_caution())

        warning_blocks = [block for block in payload["blocks"] if block["block_type"] == "warning"]

        self.assertEqual(len(warning_blocks), 1)
        self.assertEqual(
            warning_blocks[0]["text"],
            "CAUTION: There is danger of an explosion if you replace the batteries used in the remote with the wrong type of battery. Replace only with the same or equivalent type.",
        )
        self.assertEqual(
            warning_blocks[0]["lines"],
            [
                "CAUTION: There is danger of an explosion if you replace the batteries used in the remote with the wrong type of battery.",
                "Replace only with the same or equivalent type.",
            ],
        )

    def test_caution_and_warning_body_are_split_into_bullets(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_caution_and_warning())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Operation"]
        bullet_texts = [block["text"] for block in blocks if block["block_type"] == "bullet"]

        self.assertIn(
            "CAUTION: There is danger of an explosion if you replace the batteries used in the remote with the wrong type of battery. Replace only with the same or equivalent type.",
            bullet_texts,
        )
        self.assertIn(
            "WARNING - Do not use liquid fumigators containing chemicals, such as mosquito repellent or air freshener, around the product. If steam comes in contact with the product surface or enters the product, it may cause stains or malfunction.",
            bullet_texts,
        )
        self.assertEqual(
            [
                len(block["sentences"])
                for block in blocks
                if block["block_type"] == "bullet" and block["text"].startswith(("CAUTION:", "WARNING -"))
            ],
            [2, 2],
        )

    def test_parenthetical_navigation_path_is_merged_into_one_block(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_parenthetical_navigation())

        internet_blocks = [
            block for block in payload["blocks"] if block["section_heading"] == "Internet security"
        ]
        nav_blocks = [block for block in internet_blocks if block["block_type"] == "navigation_ui"]

        self.assertEqual(len(nav_blocks), 1)
        self.assertEqual(
            nav_blocks[0]["text"],
            "(> left directional button > Settings > Support > Software Update > Auto Update)",
        )
        self.assertFalse(any(block["text"] == ">" for block in internet_blocks))
        self.assertIn("turn on Auto Update in the TV's menu", internet_blocks[1]["text"])
        self.assertTrue(internet_blocks[3]["text"].startswith("When an update is available"))

    def test_model_specific_parenthetical_navigation_paths_are_merged(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_model_specific_navigation())

        blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "Before Reading This Simple User Guide"
        ]
        nav_blocks = [block for block in blocks if block["block_type"] == "navigation_ui"]

        self.assertEqual(
            [block["text"] for block in nav_blocks],
            [
                "(F6***F/H5***F: > left directional button > Settings > Support > Open User guide)",
                "(Other models: > left directional button > Settings > Support > Tips and User Guides > Open User guide)",
            ],
        )
        self.assertFalse(any(block["text"] == ")" for block in blocks))

    def test_package_content_items_are_grouped_as_item_list(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_package_content())

        package_blocks = [
            block for block in payload["blocks"] if block["section_heading"] == "01 Package Content"
        ]
        item_list = next(block for block in package_blocks if block["block_type"] == "item_list")
        note = next(block for block in package_blocks if block["block_type"] == "item_list_note")

        self.assertEqual(item_list["list_type"], "package_contents")
        self.assertEqual(
            item_list["items"],
            [
                {"item_order": 1, "text": "Simple User Guide"},
                {"item_order": 2, "text": "Warranty Card / Regulatory Guide (Not available in some locations)"},
                {"item_order": 3, "text": "Samsung Smart Remote"},
                {"item_order": 4, "text": "Wireless One Connect Box"},
            ],
        )
        self.assertEqual(
            note["text"],
            "*: Some of the items specified above may not be included in the package, depending on the TV model.",
        )

    def test_package_content_notes_are_kept_outside_item_list(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_package_content_notes())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "01 Package Content"]
        item_list = next(block for block in blocks if block["block_type"] == "item_list")
        notes = [block["text"] for block in blocks if block["block_type"] == "item_list_note"]

        self.assertFalse(any(item["text"].startswith(":") for item in item_list["items"]))
        self.assertEqual(
            notes,
            [
                "*: Some of the items specified above may not be included in the package, depending on the TV model.",
                "**: Some components may not be provided, depending on the One Connect connection method (wired or wireless connection).",
                "**: The number of One Connect cables provided may differ depending on the model.",
            ],
        )

    def test_safety_warning_precautions_are_split_into_bullets(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_warning_precautions())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Safety Precaution"]
        bullet_texts = [block["text"] for block in blocks if block["block_type"] == "bullet"]

        self.assertTrue(blocks[1]["text"].endswith("such as:"))
        self.assertEqual(
            bullet_texts,
            [
                "Always use cabinets or stands or mounting methods recommended by Samsung.",
                "Always use furniture that can safely support the television set.",
                "Never place a television set in an unstable location.",
            ],
        )

    def test_safety_warning_precaution_continuation_is_split_into_bullets(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_warning_precaution_continuation())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Safety Precaution"]
        bullet_texts = [block["text"] for block in blocks if block["block_type"] == "bullet"]

        self.assertNotIn("1. 2. 3.", bullet_texts)
        self.assertIn(
            "Always educate about the dangers of climbing on furniture to reach the television set or its controls.",
            bullet_texts,
        )
        self.assertIn(
            "When you have to relocate or lift the TV for replacement or cleaning, be sure not to pull out the stand.",
            bullet_texts,
        )

    def test_condition_label_is_split_from_following_body(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_frame_condition())

        blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "Precautions when installing the TV with a stand"
        ]

        self.assertEqual(blocks[1]["block_type"], "condition_label")
        self.assertEqual(blocks[1]["text"], "(The Frame only)")
        self.assertEqual(
            blocks[2]["text"],
            "When you install the TV with a stand, avoid placing the stand on the back part.",
        )

    def test_model_scoped_condition_labels_are_split_from_body(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_model_scoped_condition_labels())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Model Conditions"]
        condition_texts = [block["text"] for block in blocks if block["block_type"] == "condition_label"]
        body_texts = [block["text"] for block in blocks if block["block_type"] == "body"]

        self.assertEqual(
            condition_texts,
            [
                "(S95F, The Frame (LS03FA) only)",
                "(One Connect Box Supported Model only)",
                "CLASS 1 LASER PRODUCT (The Frame (LS03FA) only)",
                "(EXCEPT FOR H5***F,F6***F)",
            ],
        )
        self.assertIn(
            "You can use the One Connect cable holder to tidy up the cables while installing the wall mount.",
            body_texts,
        )
        self.assertIn(
            "For more information about how to connect via the One Connect Box, refer to Unpacking and Installation Guide.",
            body_texts,
        )
        self.assertIn("Electric shock", body_texts)

    def test_one_connect_cable_action_labels_are_grouped(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_one_connect_action_labels())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "02 Connecting the TV to the One Connect Box"]
        action_labels = next(block for block in blocks if block["block_type"] == "figure_action_labels")

        self.assertEqual(
            action_labels["labels"],
            ["Bending", "Twisting", "Pulling", "Pressing on", "Electric shock"],
        )

    def test_inline_ui_labels_are_merged_and_figure_legend_is_grouped(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_tv_controller_figure())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Using the TV Controller"]
        body_texts = [block["text"] for block in blocks if block["block_type"] == "body"]
        legend = next(block for block in blocks if block["block_type"] == "figure_legend")

        self.assertIn(
            "You can turn on the TV with the TV Controller button at the bottom of the TV, and then use the Control menu. The Control menu appears when the TV Controller button is pressed while the TV is On.",
            body_texts,
        )
        self.assertEqual(
            legend["items"],
            [
                {"key": "A", "text": "Control menu"},
                {"key": "B", "text": "TV Controller button / Remote control sensor / Microphone switch"},
                {"key": "C", "text": "TV Controller button / Remote control sensor"},
                {"key": "D", "text": "Microphone switch"},
            ],
        )

    def test_package_screen_notice_is_split_as_figure_notice(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_package_screen_notice())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "01 Package Content"]
        figure_notice = next(block for block in blocks if block["block_type"] == "figure_notice")

        self.assertEqual(
            figure_notice["lines"],
            [
                "The screen can be damaged from direct pressure when handled incorrectly.",
                "As shown in the figure, make sure to grip the edges of the screen when you lift the TV.",
                "For more information about handling, refer to the Unpacking and Installation Guide came with this product.",
                "Do Not Touch This Screen!",
            ],
        )

    def test_microphone_figure_labels_and_model_condition_are_grouped(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_microphone_labels_and_models())

        blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "How to turn on and off the Microphone"
        ]
        variant_labels = next(block for block in blocks if block["block_type"] == "figure_variant_labels")
        callout_label = next(block for block in blocks if block["block_type"] == "figure_callout_label")
        model_condition = next(block for block in blocks if block["block_type"] == "model_condition")

        self.assertEqual(variant_labels["labels"], ["Type A", "Type B", "Type C", "Type D"])
        self.assertEqual(callout_label["text"], "On/Off Switch")
        self.assertEqual(
            model_condition["models"],
            ["R9*H", "R8*H", "QN1EH", "QN7*H", "QN8*H", "QN9**H", "S8*H", "S9*H", "M9*H", "M8*H", "U9***H", "LS03H*"],
        )
        self.assertEqual(
            model_condition["text"],
            "This function is supported only in R9*H/R8*H/QN1EH/QN7*H/QN8*H/QN9**H/S8*H/S9*H/M9*H/M8*H/U9***H/LS03H*.",
        )

    def test_split_microphone_model_condition_is_merged_into_one_sentence(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_split_microphone_model_condition())

        blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "How to turn on and off the Microphone"
        ]
        model_condition = next(block for block in blocks if block["block_type"] == "model_condition")

        self.assertEqual(
            model_condition["text"],
            "This function is supported only in Q8F (except for 32Q8F)/QN7*F/QN8*F/QN9*F/QN9**F/S8*F/S9*F/MR95F/The Frame.",
        )
        self.assertIn("The Frame", model_condition["models"])

    def test_operation_body_list_is_split_into_bullets(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_operation_body_list())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Operation"]
        bullet_texts = [block["text"] for block in blocks if block["block_type"] == "bullet"]

        self.assertIn("This apparatus uses batteries.", bullet_texts)
        self.assertIn("Do not short-circuit, disassemble, or overheat the batteries.", bullet_texts)
        self.assertFalse(
            any(
                block["block_type"] == "body" and "This apparatus uses batteries" in block["text"]
                for block in blocks
            )
        )

    def test_troubleshooting_reference_navigation_is_grouped(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_troubleshooting_reference())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Troubleshooting"]
        nav_blocks = [block for block in blocks if block["block_type"] == "navigation_ui"]

        self.assertEqual(blocks[1]["text"], 'For more information, refer to "Troubleshooting" in the User Guide.')
        self.assertEqual(len(nav_blocks), 1)
        self.assertEqual(
            nav_blocks[0]["text"],
            "(> left directional button > Settings > Support > Tips and User Guides > Open User Guide > Troubleshooting)",
        )

    def test_troubleshooting_reference_accepts_lowercase_user_guide(self):
        payload = build_content_poc_payload(
            minimal_extracted_payload_with_lowercase_user_guide_reference()
        )

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Troubleshooting"]
        nav_blocks = [block for block in blocks if block["block_type"] == "navigation_ui"]

        self.assertEqual(blocks[1]["text"], 'For more information, refer to "Troubleshooting" in the User guide.')
        self.assertFalse(
            any(block["block_type"] == "navigation_ui" and block["text"] == "Troubleshooting" for block in blocks)
        )
        self.assertEqual(
            [block["text"] for block in nav_blocks],
            [
                "(F6***F/H5***F: > left directional button > Settings > Support > Open User guide > Troubleshooting)",
                "(Other models: > left directional button > Settings > Support > Tips and User Guides > Open User guide > Troubleshooting)",
            ],
        )

    def test_quoted_troubleshooting_label_stays_body_text(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_troubleshooting_reference())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Troubleshooting"]
        self.assertEqual(blocks[1]["block_type"], "body")
        self.assertIn('"Troubleshooting"', blocks[1]["text"])
        self.assertEqual(blocks[2]["block_type"], "navigation_ui")
        self.assertEqual(
            blocks[2]["text"],
            "(> left directional button > Settings > Support > Tips and User Guides > Open User Guide > Troubleshooting)",
        )

    def test_troubleshooting_subheading_after_quoted_reference_is_split(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_remote_control_heading_reference())

        headings = [block["text"] for block in payload["blocks"] if block["block_type"] == "heading"]
        remote_blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "The remote control does not work."
        ]

        self.assertIn("The TV won’t turn on.", headings)
        self.assertIn("The remote control does not work.", headings)
        self.assertEqual(remote_blocks[1]["block_type"], "body")
        self.assertEqual(remote_blocks[1]["text"], "Replace the remote control batteries.")

    def test_software_update_navigation_keeps_inline_labels_in_body(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_software_update_navigation())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Troubleshooting"]
        nav_blocks = [block for block in blocks if block["block_type"] == "navigation_ui"]

        self.assertEqual(
            blocks[1]["text"],
            "To keep your TV in optimum condition, upgrade to the latest software. Use the Update Now or Auto Update functions on the TV's menu",
        )
        self.assertEqual(
            nav_blocks[0]["text"],
            "(> left directional button > Settings > Support > Software Update > Update Now or Auto Update)",
        )

    def test_fragmented_software_update_sentence_is_merged(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_fragmented_software_update_navigation())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Troubleshooting"]
        nav_blocks = [block for block in blocks if block["block_type"] == "navigation_ui"]
        body_texts = [block["text"] for block in blocks if block["block_type"] == "body"]

        self.assertIn(
            "To keep your TV in optimum condition, upgrade to the latest software. Use the Update Now or Auto Update functions on the TV's menu",
            body_texts,
        )
        self.assertEqual(
            nav_blocks[0]["text"],
            "(> left directional button > Settings > Support > Software Update > Update Now or Auto Update)",
        )

    def test_auto_update_navigation_fragment_is_normalized(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_split_auto_update_navigation())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Internet security"]
        nav_blocks = [block for block in blocks if block["block_type"] == "navigation_ui"]
        texts = [block["text"] for block in blocks]

        self.assertEqual(
            nav_blocks[0]["text"],
            "(> left directional button > Settings > Support > Software Update > Auto Update)",
        )
        self.assertNotIn("Auto", texts)

    def test_go_to_navigation_fragments_are_grouped(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_go_to_navigation_fragments())

        blocks = [block for block in payload["blocks"] if block["section_heading"] == "Eco Sensor and screen brightness"]
        condition_label = next(block for block in blocks if block["block_type"] == "condition_label")
        nav_block = next(block for block in blocks if block["block_type"] == "navigation_ui")

        self.assertEqual(condition_label["text"], "(except for H5***F, F6***F)")
        self.assertEqual(
            nav_block["text"],
            "(> left directional button > Settings > All Settings > General & Privacy > Power and Energy Saving > Brightness Optimization)",
        )
        self.assertFalse(any(block["text"] in {">", "."} for block in blocks))

    def test_remote_button_icon_gaps_are_represented_as_inline_tokens(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_remote_button_icon_gaps())

        blocks = [
            block
            for block in payload["blocks"]
            if block["section_heading"] == "The remote control does not work."
        ]
        power_block = next(block for block in blocks if "{btn_power}" in block["text"])
        pair_block = next(block for block in blocks if "{btn_return}" in block["text"])

        self.assertEqual(
            power_block["text"],
            "Check if the remote control sensor at the bottom of the TV blinks when you press the {btn_power} button on the remote control.",
        )
        self.assertEqual(power_block["inline_tokens"], ["btn_power"])
        self.assertEqual(
            pair_block["text"],
            "If your TV came with a Samsung Smart Remote (Bluetooth Remote), make sure to pair the remote to the TV. To pair a Samsung Smart Remote, press the {btn_return} and {btn_play_pause} buttons together for 3 seconds.",
        )
        self.assertEqual(pair_block["inline_tokens"], ["btn_return", "btn_play_pause"])
        self.assertFalse(any(block["text"] == "a Samsung Smart Remote, press the" for block in blocks))
        self.assertFalse(any(block["text"] == "and buttons together for 3 seconds." for block in blocks))

    def test_notes_are_split_into_regulatory_note_blocks(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_notes())

        headings = [block["text"] for block in payload["blocks"] if block["block_type"] == "heading"]
        regulatory_blocks = [
            block for block in payload["blocks"] if block["block_type"] == "regulatory_note"
        ]
        by_topic = {block["topic_id"]: block for block in regulatory_blocks}

        self.assertIn("Notes", headings)
        self.assertEqual(
            list(by_topic),
            [
                "REG_CLASS_B_DIGITAL",
                "REG_POWER_LABEL",
                "REG_LAN_CABLE_STP",
                "REG_UNPACKING_GUIDE_VARIANCE",
                "REG_5GHZ_INDOOR_USE",
                "REG_6GHZ_BAND_OPERATION",
            ],
        )
        self.assertIn("* Shielded Twisted Pair", by_topic["REG_LAN_CABLE_STP"]["text"])
        self.assertIn("5150 - 5250 MHz", by_topic["REG_5GHZ_INDOOR_USE"]["text"])
        self.assertIn("5925 - 7125 MHz", by_topic["REG_6GHZ_BAND_OPERATION"]["text"])
        self.assertEqual(
            by_topic["REG_POWER_LABEL"]["lines"],
            [
                "For information about the power supply, and more information about power consumption, refer to the information on the label attached to the product.",
                "On most models, the label is attached to the back of the TV.",
                "(On some models, the label is inside the cover terminal.)",
                "On Wireless One Connect Box models, the label is attached to the bottom of the Wireless One Connect Box.",
            ],
        )
        self.assertEqual(
            by_topic["REG_LAN_CABLE_STP"]["lines"],
            [
                "To connect a LAN cable, use a CAT 7 (*STP type) cable for the connection.",
                "(100/10 Mbps)",
                "* Shielded Twisted Pair",
            ],
        )

    def test_power_label_note_splits_one_connect_box_sentence(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_one_connect_power_label_note())

        regulatory_blocks = [
            block for block in payload["blocks"] if block["block_type"] == "regulatory_note"
        ]
        by_topic = {block["topic_id"]: block for block in regulatory_blocks}

        self.assertEqual(
            by_topic["REG_POWER_LABEL"]["lines"],
            [
                "For information about the power supply, and more information about power consumption, refer to the information on the label attached to the product.",
                "On most models, the label is attached to the back of the TV.",
                "(On some models, the label is inside the cover terminal.)",
                "On One Connect Box models, the label is attached to the bottom of the One Connect Box.",
            ],
        )

    def test_specification_compound_heading_is_split_into_spec_table(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_specifications())

        headings = [block["text"] for block in payload["blocks"] if block["block_type"] == "heading"]
        spec_tables = [block for block in payload["blocks"] if block["block_type"] == "spec_table"]

        self.assertIn("04 Specifications and Other Information", headings)
        self.assertIn("Specifications", headings)
        self.assertEqual(len(spec_tables), 1)
        self.assertEqual(spec_tables[0]["section_heading"], "Specifications")
        self.assertEqual(spec_tables[0]["rows"][0]["field"], "Display Resolution")
        self.assertEqual(spec_tables[0]["rows"][0]["model_pattern"], "QN9**H")
        self.assertEqual(spec_tables[0]["rows"][0]["value"], "7680 x 4320")

    def test_specification_fields_are_structured_as_model_and_common_spec_tables(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_full_specifications())

        spec_tables = [block for block in payload["blocks"] if block["block_type"] == "spec_table"]
        by_field = {block["spec_field"]: block for block in spec_tables}

        self.assertEqual(by_field["Display Resolution"]["spec_category"], "model_spec")
        self.assertEqual(
            by_field["Display Resolution"]["rows"][0],
            {
                "row_order": 1,
                "field": "Display Resolution",
                "model_pattern": "QN9**H",
                "value": "7680 x 4320",
                "unit": "",
            },
        )
        self.assertEqual(by_field["Display Resolution"]["rows"][1]["model_pattern"], "Other models")
        self.assertEqual(by_field["Sound (Output)"]["rows"][-1]["model_pattern"], "QN9**H")
        self.assertEqual(by_field["Sound (Output)"]["rows"][-1]["value"], "90 W")
        sound_rows = {
            row["model_pattern"]: row["value"]
            for row in by_field["Sound (Output)"]["rows"]
        }
        self.assertEqual(sound_rows['QN8*HD (55"-85")'], "30 W")
        self.assertEqual(sound_rows['QN8*HD (100")'], "40 W")
        self.assertEqual(sound_rows['S90H (48"-83")/S92H'], "40 W")
        self.assertEqual(by_field["Operating Temperature"]["spec_category"], "common_required_spec")
        self.assertEqual(by_field["Operating Temperature"]["rows"][0]["value"], "50 °F to 104 °F (10 °C to 40 °C)")
        self.assertEqual(by_field["Storage Humidity"]["rows"][0]["value"], "5 % to 95 %, non-condensing")

    def test_sound_output_heading_with_inline_value_is_structured_as_spec_table(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_inline_sound_output_value())

        spec_table = next(
            block
            for block in payload["blocks"]
            if block["block_type"] == "spec_table" and block["spec_field"] == "Sound (Output)"
        )
        rows = {row["model_pattern"]: row["value"] for row in spec_table["rows"]}

        self.assertEqual(rows["H5***F"], "10 W")
        self.assertEqual(rows['F6***F (32")'], "10 W")
        self.assertEqual(rows["U7***F/U8***F/QEF1"], "20 W")

    def test_display_resolution_splits_multiple_model_values(self):
        payload = build_content_poc_payload(minimal_extracted_payload_with_multiple_display_resolutions())

        spec_table = next(
            block
            for block in payload["blocks"]
            if block["block_type"] == "spec_table" and block["spec_field"] == "Display Resolution"
        )

        self.assertEqual(
            spec_table["rows"],
            [
                {
                    "row_order": 1,
                    "field": "Display Resolution",
                    "model_pattern": "QN9**F",
                    "value": "7680 x 4320",
                    "unit": "",
                },
                {
                    "row_order": 2,
                    "field": "Display Resolution",
                    "model_pattern": "F6***F",
                    "value": "1920 x 1080",
                    "unit": "",
                },
                {
                    "row_order": 3,
                    "field": "Display Resolution",
                    "model_pattern": "H5***F",
                    "value": "1366 x 768",
                    "unit": "",
                },
                {
                    "row_order": 4,
                    "field": "Display Resolution",
                    "model_pattern": "Other models",
                    "value": "3840 x 2160",
                    "unit": "",
                },
            ],
        )


def minimal_extracted_payload():
    return {
        "file_name": "sample.pdf",
        "source_token": "ZC_L02",
        "region": "ZC",
        "buyer_codes": ["ZC"],
        "language": "ENG",
        "doc_type": "A2",
        "detected_doc_type": "A2",
        "pages": [
            {
                "page_number": 1,
                "review_order": 1,
                "language": "ENG",
                "page_role": "content",
                "cells": [
                    {
                        "row": 1,
                        "column": 1,
                        "role": "cover",
                        "reading_order": 1,
                        "reading_direction": "LTR",
                        "review_items": [{"item_order": 1, "kind": "body", "text": "Cover", "sentences": ["Cover"]}],
                    },
                    {
                        "row": 1,
                        "column": 3,
                        "role": "content",
                        "reading_order": 3,
                        "reading_direction": "LTR",
                        "review_items": [
                            {
                                "item_order": 1,
                                "kind": "heading",
                                "text": "Warning! Important Safety Instructions",
                                "sentences": [],
                            },
                            {
                                "item_order": 2,
                                "kind": "body",
                                "text": (
                                    "This symbol indicates that high voltage is present inside. "
                                    "Class II product: This symbol indicates that a safety connection "
                                    "to electrical earth is not required. AC voltage: Rated voltage "
                                    "marked with this symbol is AC voltage. DC voltage: Rated voltage "
                                    "marked with this symbol is DC voltage. Caution. Consult instructions "
                                    "for use: This symbol instructs the user to consult the user manual."
                                ),
                                "sentences": ["This symbol indicates that high voltage is present inside."],
                            },
                        ],
                    },
                    {
                        "row": 1,
                        "column": 4,
                        "role": "content",
                        "reading_order": 4,
                        "reading_direction": "LTR",
                        "review_items": [
                            {
                                "item_order": 1,
                                "kind": "navigation",
                                "text": "> Settings > Support > Open User Guide",
                                "sentences": ["> Settings > Support > Open User Guide"],
                            }
                        ],
                    },
                ],
            }
        ],
    }


def minimal_extracted_payload_with_embedded_heading():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Mounting the TV on a wall",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "bullet",
            "text": (
                "For 82 inch or larger models, have four people mount the TV onto a wall. "
                "Providing proper ventilation for your TV When installing the TV, ensure proper ventilation. "
                "Failing to maintain proper ventilation may result in a fire."
            ),
            "sentences": [
                "For 82 inch or larger models, have four people mount the TV onto a wall.",
                "Providing proper ventilation for your TV When installing the TV, ensure proper ventilation.",
                "Failing to maintain proper ventilation may result in a fire.",
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_safety_warning_row():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Warning! Important Safety Instructions",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "warning",
            "text": "CAUTION RISK OF ELECTRIC SHOCK. DO NOT OPEN.",
            "sentences": ["CAUTION RISK OF ELECTRIC SHOCK.", "DO NOT OPEN."],
        },
        {
            "item_order": 3,
            "kind": "body",
            "text": (
                "This symbol indicates that high voltage is present inside. "
                "Class II product: This symbol indicates that a safety connection "
                "to electrical earth is not required. AC voltage: Rated voltage "
                "marked with this symbol is AC voltage. DC voltage: Rated voltage "
                "marked with this symbol is DC voltage. Caution. Consult instructions "
                "for use: This symbol instructs the user to consult the user manual."
            ),
            "sentences": ["This symbol indicates that high voltage is present inside."],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_split_safety_instruction_row():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Warning! Important Safety Instructions", "sentences": []},
        {
            "item_order": 2,
            "kind": "warning",
            "text": "CAUTION RISK OF ELECTRIC SHOCK. DO NOT OPEN.",
            "sentences": [],
        },
        {
            "item_order": 3,
            "kind": "body",
            "text": "Caution. Consult instructions for use: This symbol instructs the user to consult the Simple User Guide for further safety related information.",
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_additional_headings():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "WARNING",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                "Preventing the TV from falling : Wall-anchor (not supplied) "
                "Precautions when installing the TV with a (The Frame only) "
                "When you install the TV with a stand, avoid placing the stand on the back part."
            ),
            "sentences": [
                "Preventing the TV from falling : Wall-anchor (not supplied) Precautions when installing the TV with a stand (The Frame only) When you install the TV with a stand, avoid placing the stand on the back part."
            ],
        },
        {
            "item_order": 3,
            "kind": "body",
            "text": "How to turn on and off the Microphone Type A Type B",
            "sentences": ["How to turn on and off the Microphone Type A Type B"],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_quoted_heading_reference():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Safety Precaution",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                'For added stability and safety, you can purchase and install '
                'the anti-tip device, referring to "Preventing the TV from falling."'
            ),
            "sentences": [
                'For added stability and safety, you can purchase and install the anti-tip device, referring to "Preventing the TV from falling."'
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_short_precautions_heading():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Precautions when installing the TV with a",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": "(The Frame only) When you install the TV with a stand, avoid placing the stand on the back part.",
            "sentences": [
                "(The Frame only) When you install the TV with a stand, avoid placing the stand on the back part."
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_falling_tv_procedure():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Preventing the TV from falling",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                ": Wall-anchor (not supplied) "
                "Using the appropriate screws, firmly fasten a set of brackets to the wall. "
                "Confirm that the screws are firmly attached to the wall. "
                "You may need additional material such as wall anchors depending on the type of wall. "
                "Using the appropriately sized screws, firmly fasten a set of brackets to the TV. "
                "For the screw specifications, refer to the standard screw part in the table on the Unpacking and Installation Guide. "
                "Connect the brackets fixed to the TV and the brackets fixed to the wall with a durable, heavy-duty string, and then tie the string tightly. "
                "Install the TV near the wall so that it does not fall backwards. "
                "Connect the string so that the brackets fixed to the wall are at the same height as or lower than the brackets fixed to the TV."
            ),
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_fragmented_falling_tv_procedure():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Preventing the TV from falling",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                ": Wall-anchor (not supplied) "
                "Using the appropriate screws, firmly fasten a set of brackets to the wall. "
                "Confirm that the screws are firmly attached to the wall."
            ),
            "sentences": [],
        },
        {
            "item_order": 3,
            "kind": "bullet",
            "text": "– You may need additional material such as wall anchors depending on the type of wall. Using the appropriately sized screws, firmly fasten a set of brackets to the TV.",
            "sentences": [],
        },
        {
            "item_order": 4,
            "kind": "bullet",
            "text": "– For the screw specifications, refer to the standard screw part in the table on the Unpacking and Installation Guide. Connect the brackets fixed to the TV and the brackets fixed to the wall with a durable, heavy-duty string, and then tie the string tightly.",
            "sentences": [],
        },
        {
            "item_order": 5,
            "kind": "bullet",
            "text": "– Install the TV near the wall so that it does not fall backwards.",
            "sentences": [],
        },
        {
            "item_order": 6,
            "kind": "bullet",
            "text": "– Connect the string so that the brackets fixed to the wall are at the same height as or lower than the brackets fixed to the TV. stand properly.",
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_inline_caution():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Operation", "sentences": []},
        {"item_order": 2, "kind": "warning", "text": "CAUTION", "sentences": ["CAUTION"]},
        {
            "item_order": 3,
            "kind": "body",
            "text": ": There is danger of an explosion if you replace the batteries used in the remote with the wrong type of battery. Replace only with the same or equivalent type.",
            "sentences": [
                ": There is danger of an explosion if you replace the batteries used in the remote with the wrong type of battery.",
                "Replace only with the same or equivalent type.",
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_caution_and_warning():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Operation", "sentences": []},
        {"item_order": 2, "kind": "warning", "text": "CAUTION", "sentences": ["CAUTION"]},
        {
            "item_order": 3,
            "kind": "body",
            "text": (
                ": There is danger of an explosion if you replace the batteries used in the remote "
                "with the wrong type of battery. Replace only with the same or equivalent type. "
                "WARNING - Do not use liquid fumigators containing chemicals, such as mosquito repellent "
                "or air freshener, around the product. If steam comes in contact with the product surface "
                "or enters the product, it may cause stains or malfunction."
            ),
            "sentences": [
                ": There is danger of an explosion if you replace the batteries used in the remote with the wrong type of battery.",
                "Replace only with the same or equivalent type.",
                "WARNING - Do not use liquid fumigators containing chemicals, such as mosquito repellent or air freshener, around the product.",
                "If steam comes in contact with the product surface or enters the product, it may cause stains or malfunction.",
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_parenthetical_navigation():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Internet security", "sentences": []},
        {
            "item_order": 2,
            "kind": "bullet",
            "text": "To automatically receive these updates, turn on",
            "sentences": ["To automatically receive these updates, turn on"],
        },
        {"item_order": 3, "kind": "ui_label", "text": "Auto Update", "sentences": ["Auto Update"]},
        {"item_order": 4, "kind": "body", "text": "in the TV's menu (", "sentences": ["in the TV's menu ("]},
        {
            "item_order": 5,
            "kind": "navigation",
            "text": "> left directional button > Settings > Support >",
            "sentences": ["> left directional button > Settings > Support >"],
        },
        {"item_order": 6, "kind": "ui_label", "text": "Software Update", "sentences": ["Software Update"]},
        {"item_order": 7, "kind": "navigation", "text": ">", "sentences": [">"]},
        {"item_order": 8, "kind": "ui_label", "text": "Auto Update", "sentences": ["Auto Update"]},
        {
            "item_order": 9,
            "kind": "body",
            "text": "). When an update is available, a popup message appears on the TV screen.",
            "sentences": [").", "When an update is available, a popup message appears on the TV screen."],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_package_content():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "01 Package Content", "sentences": []},
        {
            "item_order": 2,
            "kind": "body",
            "text": "Make sure the following items are included with your TV. If any items are missing, contact your dealer.",
            "sentences": [
                "Make sure the following items are included with your TV.",
                "If any items are missing, contact your dealer.",
            ],
        },
        {"item_order": 3, "kind": "bullet", "text": "Simple User Guide", "sentences": ["Simple User Guide"]},
        {
            "item_order": 4,
            "kind": "bullet",
            "text": "Warranty Card / Regulatory Guide (Not available in some locations)",
            "sentences": ["Warranty Card / Regulatory Guide (Not available in some locations)"],
        },
        {"item_order": 5, "kind": "list_item", "text": "*Samsung Smart Remote", "sentences": ["*Samsung Smart Remote"]},
        {
            "item_order": 6,
            "kind": "list_item",
            "text": "*Wireless One Connect Box *: Some of the items specified above may not be included in the package, depending on the TV model.",
            "sentences": [
                "*Wireless One Connect Box *: Some of the items specified above may not be included in the package, depending on the TV model."
            ],
        },
        {
            "item_order": 7,
            "kind": "bullet",
            "text": "The type of battery may vary depending on the model.",
            "sentences": ["The type of battery may vary depending on the model."],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_package_content_notes():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "01 Package Content", "sentences": []},
        {"item_order": 2, "kind": "bullet", "text": "Simple User Guide", "sentences": []},
        {"item_order": 3, "kind": "list_item", "text": "*Samsung Smart Remote", "sentences": []},
        {
            "item_order": 4,
            "kind": "list_item",
            "text": "*: Some of the items specified above may not be included in the package, depending on the TV model.",
            "sentences": [],
        },
        {
            "item_order": 5,
            "kind": "list_item",
            "text": "**: Some components may not be provided, depending",
            "sentences": [],
        },
        {
            "item_order": 6,
            "kind": "body",
            "text": "on the One Connect connection method (wired or wireless connection).",
            "sentences": [],
        },
        {
            "item_order": 7,
            "kind": "list_item",
            "text": "**: The number of One Connect cables provided may differ",
            "sentences": [],
        },
        {"item_order": 8, "kind": "body", "text": "depending on the model.", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_warning_precautions():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Safety Precaution", "sentences": []},
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                "WARNING : Never place a television set in an unstable location. "
                "Many injuries can be avoided by taking simple precautions such as: "
                "Always use cabinets or stands or mounting methods recommended by Samsung. "
                "Always use furniture that can safely support the television set. "
                "Never place a television set in an unstable location."
            ),
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_warning_precaution_continuation():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Safety Precaution", "sentences": []},
        {"item_order": 2, "kind": "bullet", "text": "1. 2. 3.", "sentences": []},
        {
            "item_order": 3,
            "kind": "body",
            "text": (
                "Always educate about the dangers of climbing on furniture to reach the television set or its controls. "
                "Always route cords and cables connected to your television so they cannot be tripped over, pulled or grabbed. "
                "Never place a television set in an unstable location. "
                "When you have to relocate or lift the TV for replacement or cleaning, be sure not to pull out the stand."
            ),
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_frame_condition():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Precautions when installing the TV with a stand",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": "(The Frame only) When you install the TV with a stand, avoid placing the stand on the back part.",
            "sentences": [
                "(The Frame only) When you install the TV with a stand, avoid placing the stand on the back part."
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_model_scoped_condition_labels():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Model Conditions", "sentences": []},
        {
            "item_order": 2,
            "kind": "body",
            "text": "(S95F, The Frame (LS03FA) only) You can use the One Connect cable holder to tidy up the cables while installing the wall mount.",
            "sentences": [],
        },
        {
            "item_order": 3,
            "kind": "body",
            "text": "(One Connect Box Supported Model only) For more information about how to connect via the One Connect Box, refer to Unpacking and Installation Guide.",
            "sentences": [],
        },
        {
            "item_order": 4,
            "kind": "body",
            "text": "Electric shock CLASS 1 LASER PRODUCT (The Frame (LS03FA) only)",
            "sentences": [],
        },
        {
            "item_order": 5,
            "kind": "body",
            "text": "(EXCEPT FOR H5***F,F6***F)",
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_one_connect_action_labels():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "02 Connecting the TV to the One Connect Box", "sentences": []},
        {
            "item_order": 2,
            "kind": "bullet",
            "text": "Take care not to subject the cable to any of the actions below. The One Connect Cable contains a power circuit.",
            "sentences": [],
        },
        {"item_order": 3, "kind": "body", "text": "Bending", "sentences": []},
        {"item_order": 4, "kind": "body", "text": "Twisting", "sentences": []},
        {"item_order": 5, "kind": "body", "text": "Pulling", "sentences": []},
        {"item_order": 6, "kind": "body", "text": "Pressing on", "sentences": []},
        {"item_order": 7, "kind": "body", "text": "Electric shock", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_tv_controller_figure():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Using the TV Controller", "sentences": []},
        {"item_order": 2, "kind": "body", "text": "You can turn on the TV with the", "sentences": ["You can turn on the TV with the"]},
        {"item_order": 3, "kind": "ui_label", "text": "TV Controller", "sentences": ["TV Controller"]},
        {"item_order": 4, "kind": "body", "text": "button at the bottom of the TV, and then use the", "sentences": ["button at the bottom of the TV, and then use the"]},
        {"item_order": 5, "kind": "ui_label", "text": "Control menu", "sentences": ["Control menu"]},
        {"item_order": 6, "kind": "body", "text": ". The", "sentences": [".", "The"]},
        {"item_order": 7, "kind": "ui_label", "text": "Control menu", "sentences": ["Control menu"]},
        {"item_order": 8, "kind": "body", "text": "appears when the", "sentences": ["appears when the"]},
        {"item_order": 9, "kind": "ui_label", "text": "TV Controller", "sentences": ["TV Controller"]},
        {"item_order": 10, "kind": "body", "text": "button is pressed while the TV is On.", "sentences": ["button is pressed while the TV is On."]},
        {"item_order": 11, "kind": "ui_label", "text": "Control menu TV Controller", "sentences": ["Control menu TV Controller"]},
        {"item_order": 12, "kind": "body", "text": "button /", "sentences": ["button /"]},
        {"item_order": 13, "kind": "ui_label", "text": "Remote control sensor", "sentences": ["Remote control sensor"]},
        {"item_order": 14, "kind": "body", "text": "/", "sentences": ["/"]},
        {"item_order": 15, "kind": "ui_label", "text": "Microphone switch", "sentences": ["Microphone switch"]},
        {"item_order": 16, "kind": "body", "text": "/ * Motion Sensor TV Controller", "sentences": ["/ * Motion Sensor TV Controller"]},
        {"item_order": 17, "kind": "body", "text": "button /", "sentences": ["button /"]},
        {"item_order": 18, "kind": "ui_label", "text": "Remote control sensor Microphone switch", "sentences": ["Remote control sensor Microphone switch"]},
        {"item_order": 19, "kind": "list_item", "text": "*: The Frame only", "sentences": ["*: The Frame only"]},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_package_screen_notice():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "01 Package Content", "sentences": []},
        {
            "item_order": 2,
            "kind": "bullet",
            "text": (
                "Check for any accessories hidden behind or in the packing materials when opening the box. "
                "The screen can be damaged from direct pressure when handled incorrectly. "
                "As shown in the figure, make sure to grip the edges of the screen when you lift the TV. "
                "For more information about handling, refer to the Unpacking and Installation Guide came with this product. "
                "Do Not Touch This Screen!"
            ),
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_microphone_labels_and_models():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "How to turn on and off the Microphone", "sentences": []},
        {"item_order": 2, "kind": "body", "text": "Type A", "sentences": ["Type A"]},
        {"item_order": 3, "kind": "body", "text": "Type B", "sentences": ["Type B"]},
        {"item_order": 4, "kind": "body", "text": "Type C", "sentences": ["Type C"]},
        {"item_order": 5, "kind": "body", "text": "Type D : On/Off Switch You can turn on or off the microphone by using the switch.", "sentences": []},
        {"item_order": 6, "kind": "bullet", "text": "This function is supported only in R9*H/R8*H/QN1EH/", "sentences": []},
        {"item_order": 7, "kind": "warning", "text": "QN7*H/QN8*H/QN9**H/S8*H/S9*H/M9*H/M8*H/", "sentences": []},
        {"item_order": 8, "kind": "body", "text": "U9***H/LS03H*.", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_split_microphone_model_condition():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "How to turn on and off the Microphone", "sentences": []},
        {"item_order": 2, "kind": "bullet", "text": "This function is supported only in Q8F (except for 32Q8F)/", "sentences": []},
        {"item_order": 3, "kind": "warning", "text": "QN7*F/QN8*F/QN9*F/QN9**F/S8*F/S9*F/MR95F/The", "sentences": []},
        {"item_order": 4, "kind": "body", "text": "Frame.", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_operation_body_list():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Operation", "sentences": []},
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                "This apparatus uses batteries. "
                "In your community, there might be environmental regulations that require you to dispose of these batteries properly. "
                "Store the accessories (remote control, batteries, or etc.) in a location safely out of the reach. "
                "Do not short-circuit, disassemble, or overheat the batteries."
            ),
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_troubleshooting_reference():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Troubleshooting", "sentences": []},
        {"item_order": 2, "kind": "body", "text": "For more information, refer to \"", "sentences": []},
        {"item_order": 3, "kind": "ui_label", "text": "Troubleshooting", "sentences": []},
        {"item_order": 4, "kind": "body", "text": "\" in the User Guide.", "sentences": []},
        {"item_order": 5, "kind": "navigation", "text": "> left directional button > Settings > Support > Tips and User Guides > Open User Guide >", "sentences": []},
        {"item_order": 6, "kind": "ui_label", "text": "Troubleshooting", "sentences": []},
        {"item_order": 7, "kind": "navigation", "text": ")", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_lowercase_user_guide_reference():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Troubleshooting", "sentences": []},
        {"item_order": 2, "kind": "body", "text": "For more information, refer to \"", "sentences": []},
        {"item_order": 3, "kind": "ui_label", "text": "Troubleshooting", "sentences": []},
        {"item_order": 4, "kind": "body", "text": "\" in the User guide.", "sentences": []},
        {"item_order": 5, "kind": "body", "text": "(F6***F/H5***F:", "sentences": []},
        {"item_order": 6, "kind": "navigation", "text": "> left directional button > Settings > Support >", "sentences": []},
        {"item_order": 7, "kind": "body", "text": "Open User guide", "sentences": []},
        {"item_order": 8, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 9, "kind": "ui_label", "text": "Troubleshooting", "sentences": []},
        {"item_order": 10, "kind": "navigation", "text": ")", "sentences": []},
        {"item_order": 11, "kind": "body", "text": "(Other models:", "sentences": []},
        {"item_order": 12, "kind": "navigation", "text": "> left directional button > Settings > Support > Tips and User Guides >", "sentences": []},
        {"item_order": 13, "kind": "body", "text": "Open User guide", "sentences": []},
        {"item_order": 14, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 15, "kind": "ui_label", "text": "Troubleshooting", "sentences": []},
        {"item_order": 16, "kind": "navigation", "text": ")", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_model_specific_navigation():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "Before Reading This Simple User Guide",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": "This TV comes with this Simple User Guide and an embedded User guide.",
            "sentences": ["This TV comes with this Simple User Guide and an embedded User guide."],
        },
        {"item_order": 3, "kind": "body", "text": "(F6***F/H5***F:", "sentences": []},
        {
            "item_order": 4,
            "kind": "navigation",
            "text": "> left directional button > Settings > Support >",
            "sentences": [],
        },
        {"item_order": 5, "kind": "body", "text": "Open User guide", "sentences": []},
        {"item_order": 6, "kind": "navigation", "text": ")", "sentences": []},
        {"item_order": 7, "kind": "body", "text": "(Other models:", "sentences": []},
        {
            "item_order": 8,
            "kind": "navigation",
            "text": "> left directional button > Settings > Support >",
            "sentences": [],
        },
        {"item_order": 9, "kind": "body", "text": "Tips and User Guides", "sentences": []},
        {"item_order": 10, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 11, "kind": "body", "text": "Open User guide", "sentences": []},
        {"item_order": 12, "kind": "navigation", "text": ")", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_remote_control_heading_reference():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "The TV won’t turn on.", "sentences": []},
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                'Try pressing the TV Controller button at the bottom of the TV to make sure that the problem is not with the remote control. '
                'If the TV turns on, refer to "The remote control does not work." The remote control does not work. '
                "Replace the remote control batteries."
            ),
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_software_update_navigation():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Troubleshooting", "sentences": []},
        {
            "item_order": 2,
            "kind": "bullet",
            "text": "To keep your TV in optimum condition, upgrade to the latest software. Use the",
            "sentences": [],
        },
        {"item_order": 3, "kind": "ui_label", "text": "Update Now", "sentences": []},
        {"item_order": 4, "kind": "body", "text": "or", "sentences": []},
        {"item_order": 5, "kind": "ui_label", "text": "Auto Update", "sentences": []},
        {"item_order": 6, "kind": "body", "text": "functions on the TV's menu (", "sentences": []},
        {"item_order": 7, "kind": "navigation", "text": "> left directional button > Settings > Support >", "sentences": []},
        {"item_order": 8, "kind": "ui_label", "text": "Software Update", "sentences": []},
        {"item_order": 9, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 10, "kind": "ui_label", "text": "Update Now", "sentences": []},
        {"item_order": 11, "kind": "body", "text": "or", "sentences": []},
        {"item_order": 12, "kind": "ui_label", "text": "Auto Update", "sentences": []},
        {"item_order": 13, "kind": "body", "text": ").", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_fragmented_software_update_navigation():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Troubleshooting", "sentences": []},
        {
            "item_order": 2,
            "kind": "bullet",
            "text": "To keep your TV in optimum condition, upgrade to the latest",
            "sentences": [],
        },
        {"item_order": 3, "kind": "body", "text": "software. Use the", "sentences": []},
        {"item_order": 4, "kind": "ui_label", "text": "Update Now", "sentences": []},
        {"item_order": 5, "kind": "body", "text": "or", "sentences": []},
        {"item_order": 6, "kind": "ui_label", "text": "Auto Update", "sentences": []},
        {"item_order": 7, "kind": "body", "text": "functions on the TV's menu (", "sentences": []},
        {"item_order": 8, "kind": "navigation", "text": "> left directional button > Settings > Support >", "sentences": []},
        {"item_order": 9, "kind": "ui_label", "text": "Software Update", "sentences": []},
        {"item_order": 10, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 11, "kind": "ui_label", "text": "Update Now", "sentences": []},
        {"item_order": 12, "kind": "body", "text": "or", "sentences": []},
        {"item_order": 13, "kind": "ui_label", "text": "Auto Update", "sentences": []},
        {"item_order": 14, "kind": "body", "text": ").", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_split_auto_update_navigation():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Internet security", "sentences": []},
        {
            "item_order": 2,
            "kind": "bullet",
            "text": "To automatically receive these updates, turn on",
            "sentences": [],
        },
        {"item_order": 3, "kind": "ui_label", "text": "Auto Update", "sentences": []},
        {"item_order": 4, "kind": "body", "text": "in the TV's menu (", "sentences": []},
        {"item_order": 5, "kind": "navigation", "text": "> left directional button > Settings > Support >", "sentences": []},
        {"item_order": 6, "kind": "ui_label", "text": "Software Update", "sentences": []},
        {"item_order": 7, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 8, "kind": "ui_label", "text": "Update", "sentences": []},
        {"item_order": 9, "kind": "body", "text": ").", "sentences": []},
        {"item_order": 10, "kind": "ui_label", "text": "Auto", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_go_to_navigation_fragments():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Eco Sensor and screen brightness", "sentences": []},
        {
            "item_order": 2,
            "kind": "body",
            "text": "(except for H5***F, F6***F) Eco Sensor adjusts the brightness of the TV automatically. If you want to turn this off, go to",
            "sentences": [],
        },
        {"item_order": 3, "kind": "navigation", "text": "> left directional button > Settings >", "sentences": []},
        {"item_order": 4, "kind": "ui_label", "text": "All Settings", "sentences": []},
        {"item_order": 5, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 6, "kind": "body", "text": "General &", "sentences": []},
        {"item_order": 7, "kind": "body", "text": "Privacy", "sentences": []},
        {"item_order": 8, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 9, "kind": "ui_label", "text": "Power and Energy Saving", "sentences": []},
        {"item_order": 10, "kind": "navigation", "text": ">", "sentences": []},
        {"item_order": 11, "kind": "ui_label", "text": "Brightness Optimization", "sentences": []},
        {"item_order": 12, "kind": "body", "text": ".", "sentences": []},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_remote_button_icon_gaps():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "The remote control does not work.", "sentences": []},
        {
            "item_order": 2,
            "kind": "bullet",
            "text": "Check if the remote control sensor at the bottom of the TV blinks when you press the button on the remote control.",
            "sentences": [
                "Check if the remote control sensor at the bottom of the TV blinks when you press the button on the remote control."
            ],
        },
        {
            "item_order": 3,
            "kind": "bullet",
            "text": "If your TV came with a Samsung Smart Remote (Bluetooth Remote), make sure to pair the remote to the TV. To pair",
            "sentences": [
                "If your TV came with a Samsung Smart Remote (Bluetooth Remote), make sure to pair the remote to the TV.",
                "To pair",
            ],
        },
        {
            "item_order": 4,
            "kind": "body",
            "text": "a Samsung Smart Remote, press the",
            "sentences": ["a Samsung Smart Remote, press the"],
        },
        {
            "item_order": 5,
            "kind": "body",
            "text": "and buttons together for 3 seconds.",
            "sentences": ["and buttons together for 3 seconds."],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_notes():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Storage Humidity", "sentences": []},
        {
            "item_order": 2,
            "kind": "body",
            "text": "5 % to 95 %, non-condensing",
            "sentences": ["5 % to 95 %, non-condensing"],
        },
        {"item_order": 3, "kind": "body", "text": "Notes", "sentences": ["Notes"]},
        {
            "item_order": 4,
            "kind": "body",
            "text": (
                "This device is a Class B digital apparatus. "
                "For information about the power supply, and more information about power consumption, "
                "refer to the information on the label attached to the product. "
                "On most models, the label is attached to the back of the TV. "
                "(On some models, the label is inside the cover terminal.) "
                "On Wireless One Connect Box models, the label is attached to the bottom of the Wireless One Connect Box. "
                "To connect a LAN cable, use a CAT 7 (*STP type) cable for the connection. (100/10 Mbps)"
            ),
            "sentences": ["This device is a Class B digital apparatus."],
        },
        {
            "item_order": 5,
            "kind": "list_item",
            "text": "* Shielded Twisted Pair",
            "sentences": ["* Shielded Twisted Pair"],
        },
        {
            "item_order": 6,
            "kind": "body",
            "text": (
                "The images and specifications of the Unpacking and Installation Guide may differ from the actual product. "
                "Operation in the band 5150 - 5250 MHz is only for indoor "
                "[Operation in the band 5925 - 7125 MHz should follow] "
                "This product shall not be used for control of or communications with unmanned aircraft systems. "
                "Operation of this product shall be limited to indoor use "
                "Operation of this product on oil platforms, automobiles, trains, maritime vessels and aircraft shall be prohibited "
                "except for on large aircraft flying above 3,048 m (10,000 ft)."
            ),
            "sentences": [
                "The images and specifications of the Unpacking and Installation Guide may differ from the actual product."
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_one_connect_power_label_note():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "body", "text": "Notes", "sentences": ["Notes"]},
        {
            "item_order": 2,
            "kind": "body",
            "text": (
                "This device is a Class B digital apparatus. "
                "For information about the power supply, and more information about power consumption, "
                "refer to the information on the label attached to the product. "
                "On most models, the label is attached to the back of the TV. "
                "(On some models, the label is inside the cover terminal.) "
                "On One Connect Box models, the label is attached to the bottom of the One Connect Box."
            ),
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_specifications():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {
            "item_order": 1,
            "kind": "heading",
            "text": "04 Specifications and Other Information Specifications Display Resolution",
            "sentences": [],
        },
        {
            "item_order": 2,
            "kind": "body",
            "text": "QN9**H: 7680 x 4320 Other models: 3840 x 2160",
            "sentences": ["QN9**H: 7680 x 4320 Other models: 3840 x 2160"],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_multiple_display_resolutions():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "04 Specifications and Other Information", "sentences": []},
        {"item_order": 2, "kind": "heading", "text": "Specifications", "sentences": []},
        {"item_order": 3, "kind": "heading", "text": "Display Resolution", "sentences": []},
        {
            "item_order": 4,
            "kind": "body",
            "text": "QN9**F: 7680 x 4320 F6***F: 1920 x 1080 H5***F: 1366 x 768 Other models: 3840 x 2160",
            "sentences": [
                "QN9**F: 7680 x 4320 F6***F: 1920 x 1080 H5***F: 1366 x 768 Other models: 3840 x 2160"
            ],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_inline_sound_output_value():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "Specifications", "sentences": []},
        {"item_order": 2, "kind": "heading", "text": "Sound (Output) H5***F: 10 W", "sentences": []},
        {
            "item_order": 3,
            "kind": "warning",
            "text": 'F6***F (32"): 10 W, F6***F (40"): 20 W U7***F/U8***F/QEF1: 20 W',
            "sentences": [],
        },
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


def minimal_extracted_payload_with_full_specifications():
    payload = minimal_extracted_payload()
    payload["pages"][0]["cells"][1]["review_items"] = [
        {"item_order": 1, "kind": "heading", "text": "04 Specifications and Other Information", "sentences": []},
        {"item_order": 2, "kind": "heading", "text": "Specifications", "sentences": []},
        {"item_order": 3, "kind": "heading", "text": "Display Resolution", "sentences": []},
        {
            "item_order": 4,
            "kind": "body",
            "text": "QN9**H: 7680 x 4320 Other models: 3840 x 2160",
            "sentences": ["QN9**H: 7680 x 4320 Other models: 3840 x 2160"],
        },
        {"item_order": 5, "kind": "heading", "text": "Sound (Output)", "sentences": []},
        {
            "item_order": 6,
            "kind": "warning",
            "text": 'U8***H/U9***H: 20 W QN8*HD (55"-85"): 30 W, QN8*HD (100"): 40 W',
            "sentences": ['U8***H/U9***H: 20 W QN8*HD (55"-85"): 30 W, QN8*HD (100"): 40 W'],
        },
        {"item_order": 7, "kind": "heading", "text": "R9*H/S95H: 70 W", "sentences": []},
        {
            "item_order": 8,
            "kind": "warning",
            "text": 'S90H (42"): 20 W, S90H (48"-83")/S92H: 40 W',
            "sentences": ['S90H (42"): 20 W, S90H (48"-83")/S92H: 40 W'],
        },
        {"item_order": 9, "kind": "heading", "text": "QN9**H: 90 W Operating Temperature", "sentences": []},
        {"item_order": 10, "kind": "body", "text": "50 °F to 104 °F (10 °C to 40 °C)", "sentences": ["50 °F to 104 °F (10 °C to 40 °C)"]},
        {"item_order": 11, "kind": "heading", "text": "Operating Humidity", "sentences": []},
        {"item_order": 12, "kind": "body", "text": "10 % to 80 %, non-condensing", "sentences": ["10 % to 80 %, non-condensing"]},
        {"item_order": 13, "kind": "heading", "text": "Storage Temperature", "sentences": []},
        {"item_order": 14, "kind": "bullet", "text": "-4 °F to 113 °F (-20 °C to 45 °C)", "sentences": ["-4 °F to 113 °F (-20 °C to 45 °C)"]},
        {"item_order": 15, "kind": "heading", "text": "Storage Humidity", "sentences": []},
        {"item_order": 16, "kind": "body", "text": "5 % to 95 %, non-condensing", "sentences": ["5 % to 95 %, non-condensing"]},
    ]
    payload["pages"][0]["cells"] = payload["pages"][0]["cells"][:2]
    return payload


if __name__ == "__main__":
    unittest.main()
