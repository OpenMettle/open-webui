import { describe, expect, it } from 'vitest';

import { getContextCapacity, getContextWheel, getMeasuredContextTokens } from './contextUsage';

// The shape getUsageTokenCount reads from an OpenAI-compatible provider.
const count = (usage?: Record<string, unknown> | null) =>
	Number(usage?.prompt_tokens ?? 0) + Number(usage?.completion_tokens ?? 0);
const usage = (prompt: number, completion: number) => ({
	prompt_tokens: prompt,
	completion_tokens: completion,
	// Open WebUI sums these across the calls of a tool loop; the wheel must not read them.
	total_tokens: 10 * (prompt + completion)
});

const history = (currentId: string | null) => ({
	currentId,
	messages: {
		u1: { parentId: null },
		a1: { parentId: 'u1', usage: usage(1000, 200) },
		// Two answers to the same second question: a regeneration.
		u2: { parentId: 'a1' },
		a2: { parentId: 'u2', usage: usage(1300, 700) },
		a2b: { parentId: 'u2', usage: usage(1300, 50) },
		u3: { parentId: 'a2b' },
		a3: { parentId: 'u3' }
	}
});

describe('getMeasuredContextTokens', () => {
	it('reads the newest reply on the displayed branch, not its sibling', () => {
		expect(getMeasuredContextTokens(history('a2'), count)).toBe(2000);
		expect(getMeasuredContextTokens(history('a2b'), count)).toBe(1350);
	});

	it('keeps the last measured reply while a new one has no usage yet', () => {
		expect(getMeasuredContextTokens(history('u3'), count)).toBe(1350);
		expect(getMeasuredContextTokens(history('a3'), count)).toBe(1350);
	});

	it('reads usage stored under info', () => {
		const chat = {
			currentId: 'a',
			messages: { a: { parentId: null, info: { usage: usage(40, 2) } } }
		};
		expect(getMeasuredContextTokens(chat, count)).toBe(42);
	});

	it('returns nothing before the first measured reply', () => {
		expect(getMeasuredContextTokens(history('u1'), count)).toBeNull();
		expect(getMeasuredContextTokens(history(null), count)).toBeNull();
		expect(getMeasuredContextTokens(null, count)).toBeNull();
		expect(getMeasuredContextTokens({ currentId: 'gone', messages: {} }, count)).toBeNull();
	});

	it('ignores replies from before a context summary', () => {
		const chat = history('a3');
		(chat.messages.u3 as Record<string, unknown>).contextSummary = 'Earlier: ...';
		expect(getMeasuredContextTokens(chat, count)).toBeNull();
	});

	it('stops on a parent loop', () => {
		const chat = { currentId: 'a', messages: { a: { parentId: 'b' }, b: { parentId: 'a' } } };
		expect(getMeasuredContextTokens(chat, count)).toBeNull();
	});
});

describe('getContextCapacity', () => {
	const models = [
		{ id: 'declared', context_window: 100768, max_output_tokens: 12288 },
		{ id: 'window-only', context_window: 32768 },
		{ id: 'nested', openai: { context_window: 4096, max_output_tokens: 1024 } },
		{ id: 'preset', info: { base_model_id: 'declared' } },
		{ id: 'plain' },
		{ id: 'odd', context_window: '100768', max_output_tokens: 12288 },
		{ id: 'reserve-too-large', context_window: 4096, max_output_tokens: 4096 }
	];

	it('subtracts the output allowance from the declared window', () => {
		expect(getContextCapacity('declared', models)).toBe(88480);
		expect(getContextCapacity('nested', models)).toBe(3072);
	});

	it('uses the whole window when no allowance is declared or it leaves no room', () => {
		expect(getContextCapacity('window-only', models)).toBe(32768);
		expect(getContextCapacity('reserve-too-large', models)).toBe(4096);
	});

	it('lets a preset inherit from its base model', () => {
		expect(getContextCapacity('preset', models)).toBe(88480);
	});

	it('returns nothing without a usable declaration', () => {
		expect(getContextCapacity('plain', models)).toBeNull();
		expect(getContextCapacity('odd', models)).toBeNull();
		expect(getContextCapacity('missing', models)).toBeNull();
		expect(getContextCapacity(undefined, models)).toBeNull();
	});
});

describe('getContextWheel', () => {
	it('has no state without a capacity', () => {
		expect(getContextWheel(500, null)).toBeNull();
		expect(getContextWheel(500, 0)).toBeNull();
	});

	it('is empty before the first measured reply', () => {
		expect(getContextWheel(null, 88480)).toEqual({
			tokens: 0,
			capacity: 88480,
			percent: 0,
			level: 'normal'
		});
	});

	it('changes level at 75% and 90%, rounding down', () => {
		expect(getContextWheel(41200, 88480)).toMatchObject({ percent: 46, level: 'normal' });
		expect(getContextWheel(749, 1000)).toMatchObject({ percent: 74, level: 'normal' });
		expect(getContextWheel(750, 1000)).toMatchObject({ percent: 75, level: 'high' });
		expect(getContextWheel(899, 1000)).toMatchObject({ percent: 89, level: 'high' });
		expect(getContextWheel(900, 1000)).toMatchObject({ percent: 90, level: 'full' });
	});

	it('reports more than 100% when the conversation has outgrown the capacity', () => {
		expect(getContextWheel(1200, 1000)).toMatchObject({ percent: 120, level: 'full' });
	});
});
