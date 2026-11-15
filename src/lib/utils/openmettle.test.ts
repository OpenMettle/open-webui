import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import {
	OPENMETTLE_VERSION,
	openMettlePostProcessor,
	productName,
	rebrandText,
	setOpenMettleBranding,
	shortBuildHash,
	showsReplyHeader,
	versionLine
} from './openmettle';

const english: Record<string, string> = JSON.parse(
	readFileSync(new URL('../i18n/locales/en-US/translation.json', import.meta.url), 'utf8')
);
// en-US leaves most values empty; i18next then shows the key.
const shown = (key: string) => english[key] || key;

describe('branding switch', () => {
	it('names the product after the switch', () => {
		expect(productName(true)).toBe('OpenMettle');
		expect(productName(false)).toBe('Open WebUI');
		expect(productName(undefined)).toBe('Open WebUI');
	});

	it('renames the application in translated text', () => {
		const key = 'Open WebUI can use tools provided by any OpenAPI server.';
		expect(rebrandText(shown(key), key)).toBe(
			'OpenMettle can use tools provided by any OpenAPI server.'
		);
		const settings = 'settings.admin.audio.sttWhisperModel.description';
		expect(rebrandText(shown(settings), settings)).toBe(
			'OpenMettle uses faster-whisper internally.'
		);
	});

	it('keeps the name where the text is about the upstream project or its community', () => {
		for (const key of [
			'Help us translate Open WebUI!',
			'Running Open WebUI for a team?',
			'Share to Open WebUI Community',
			'Made by Open WebUI Community',
			'settings.admin.general.help.description'
		]) {
			expect(rebrandText(shown(key), key)).toBe(shown(key));
		}
		const sharing = 'settings.admin.general.communitySharing.description';
		expect(rebrandText(shown(sharing), sharing)).toBe(
			'Allow users to share chats with the Open WebUI community.'
		);
	});

	it('every key kept for the upstream project still exists', () => {
		const kept = [
			'Help us translate Open WebUI!',
			'Open WebUI version',
			'Running Open WebUI for a team?',
			'settings.admin.general.help.description'
		];
		for (const key of kept) expect(english).toHaveProperty([key]);
	});

	it('changes translations only while the switch is on', () => {
		const key = 'Connect external apps to Open WebUI.';
		setOpenMettleBranding(false);
		expect(openMettlePostProcessor.process(key, key)).toBe(key);
		setOpenMettleBranding(true);
		expect(openMettlePostProcessor.process(key, [key])).toBe(
			'Connect external apps to OpenMettle.'
		);
		setOpenMettleBranding(undefined);
		expect(openMettlePostProcessor.process(key, key)).toBe(key);
	});
});

describe('version line', () => {
	it('shows the fork, the upstream base and the commit', () => {
		expect(versionLine('0.13.3', 'ab3186bb3c0ffee0000000000000000000000000')).toBe(
			`OpenMettle v${OPENMETTLE_VERSION} · Open WebUI v0.13.3 · ab3186b`
		);
	});

	it('falls back when the build carries no commit', () => {
		for (const hash of ['', 'dev-build', undefined, null]) {
			expect(shortBuildHash(hash)).toBe('');
			expect(versionLine('0.13.3', hash, 'dev build')).toBe(
				`OpenMettle v${OPENMETTLE_VERSION} · Open WebUI v0.13.3 · dev build`
			);
		}
		expect(versionLine(undefined, 'ab3186b')).toContain('Open WebUI v?');
	});
});

describe('reply header', () => {
	const user = (id: string, models = ['qwen']) => ({ role: 'user', parentId: null, models, id });
	const reply = (parentId: string, model = 'qwen', extra = {}) => ({
		role: 'assistant',
		parentId,
		model,
		...extra
	});
	const chat = (messages: Record<string, any>) => ({ messages });

	it('always shows it with the switch off, as upstream does', () => {
		const history = chat({ u1: user('u1'), a1: reply('u1') });
		expect(showsReplyHeader(false, history, history.messages.a1)).toBe(true);
		expect(showsReplyHeader(undefined, history, history.messages.a1)).toBe(true);
	});

	it('hides it when one model answers the whole chat', () => {
		const history = chat({ u1: user('u1'), a1: reply('u1'), u2: user('u2'), a2: reply('u2') });
		expect(showsReplyHeader(true, history, history.messages.a2)).toBe(false);
	});

	it('shows it when the chat has replies from more than one model, on any branch', () => {
		const history = chat({ u1: user('u1'), a1: reply('u1'), a1b: reply('u1', 'gemma') });
		expect(showsReplyHeader(true, history, history.messages.a1)).toBe(true);
	});

	it('shows it for a turn sent to several models and for arena replies', () => {
		const compare = chat({ u1: user('u1', ['qwen', 'gemma']), a1: reply('u1') });
		expect(showsReplyHeader(true, compare, compare.messages.a1)).toBe(true);
		const arena = chat({ u1: user('u1'), a1: reply('u1', 'qwen', { arena: true }) });
		expect(showsReplyHeader(true, arena, arena.messages.a1)).toBe(true);
	});
});
