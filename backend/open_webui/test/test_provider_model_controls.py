"""Model Controls declared by an OpenAI-compatible provider in its model list.

Run inside the Open WebUI image (the module imports the app configuration):
    python -m unittest open_webui.test.test_provider_model_controls
"""

import unittest

from open_webui.utils.models import provider_model_controls
from open_webui.utils.payload import apply_model_controls

DECLARED = {
    'id': 'Qwen3.8-27B-MXFP4',
    'supportedReasoningEfforts': [
        {'reasoningEffort': 'none', 'label': 'Off'},
        {'reasoningEffort': 'low', 'label': 'Low'},
        {'reasoningEffort': 'medium', 'label': 'Medium'},
        {'reasoningEffort': 'xhigh', 'label': 'Max'},
    ],
    'defaultReasoningEffort': 'low',
}


class ProviderModelControlsTests(unittest.TestCase):
    def test_reasoning_scale_becomes_a_slider_with_labels_and_default(self):
        controls = provider_model_controls(DECLARED)
        effort = controls['reasoning_effort']
        self.assertEqual('slider', effort['display'])
        self.assertEqual('low', effort['default'])
        self.assertEqual(['none', 'low', 'medium', 'xhigh'], list(effort['options']))
        self.assertEqual('Max', effort['options']['xhigh']['label'])
        self.assertEqual({'reasoning_effort': 'xhigh'}, effort['options']['xhigh']['params'])

    def test_option_without_label_shows_its_value(self):
        controls = provider_model_controls({'supportedReasoningEfforts': [{'reasoningEffort': 'low'}, {'reasoningEffort': 'high'}]})
        self.assertEqual('high', controls['reasoning_effort']['options']['high']['label'])

    def test_single_option_stays_a_menu(self):
        controls = provider_model_controls({'supportedReasoningEfforts': [{'reasoningEffort': 'low'}]})
        self.assertNotIn('display', controls['reasoning_effort'])

    def test_models_without_a_declaration_or_malformed_ones_get_none(self):
        self.assertEqual({}, provider_model_controls({'id': 'plain'}))
        self.assertEqual({}, provider_model_controls(None))
        self.assertEqual({}, provider_model_controls({'supportedReasoningEfforts': 'low'}))
        self.assertEqual({}, provider_model_controls({'supportedReasoningEfforts': [{'reasoningEffort': '1bad'}]}))
        # A declared default that names no offered level is dropped, not trusted.
        unknown_default = provider_model_controls(
            {'supportedReasoningEfforts': [{'reasoningEffort': 'low'}], 'defaultReasoningEffort': 'max'}
        )
        self.assertNotIn('default', unknown_default['reasoning_effort'])

    def test_choices_are_applied_and_checked_like_admin_controls(self):
        controls = provider_model_controls(DECLARED)
        params = apply_model_controls({}, controls, {'reasoning_effort': 'none'})
        self.assertEqual({'reasoning_effort': 'none'}, params['custom_params'])
        params = apply_model_controls({}, controls, {})
        self.assertEqual({'reasoning_effort': 'low'}, params['custom_params'])
        with self.assertRaises(Exception):
            apply_model_controls({}, controls, {'reasoning_effort': 'extreme'})


if __name__ == '__main__':
    unittest.main()
