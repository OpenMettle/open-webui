import { describe, expect, it } from 'vitest';

import { localizeModelControls, modelControlsOf } from './localizedContent';

const provider = {
	reasoning_effort: {
		display: 'slider' as const,
		label: 'Reasoning effort',
		default: 'low',
		options: { none: { label: 'Off' }, low: { label: 'Low' }, xhigh: { label: 'Max' } }
	}
};
const admin = {
	tone: { label: 'Tone', options: { brief: { label: 'Brief' }, full: { label: 'Full' } } }
};

describe('modelControlsOf', () => {
	it('uses the controls the provider declares when no admin-defined ones exist', () => {
		expect(modelControlsOf({ provider_model_controls: provider })).toEqual(provider);
		expect(modelControlsOf({ info: { params: {} }, provider_model_controls: provider })).toEqual(provider);
	});

	it('lets admin-defined controls replace the provider declaration', () => {
		expect(modelControlsOf({ info: { params: { model_controls: admin } }, provider_model_controls: provider })).toEqual(admin);
	});

	it('returns nothing for a model without controls', () => {
		expect(modelControlsOf({ id: 'plain' })).toEqual({});
		expect(modelControlsOf(undefined)).toEqual({});
	});
});

describe('localizeModelControls', () => {
	it('localizes provider-declared controls like admin-defined ones', () => {
		const controls = localizeModelControls({ provider_model_controls: provider }, 'en-US');
		expect(controls.reasoning_effort.display).toBe('slider');
		expect(controls.reasoning_effort.options.xhigh.label).toBe('Max');
	});
});
