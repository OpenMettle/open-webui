// OpenMettle, a fork of Open WebUI: product name, the branding switch and the version line.
// The switch (env OPENMETTLE_BRANDING, reported by /api/config as `openmettle.branding`) is off by
// default; backend/open_webui/utils/openmettle.py says when Open WebUI's licence allows turning it on.

export const OPENMETTLE_NAME = 'OpenMettle';
// Bump on an OpenMettle release of the fork. Open WebUI's version stays in package.json.
export const OPENMETTLE_VERSION = '0.1.0-dev';
export const OPENMETTLE_URL = 'https://github.com/OpenMettle';
export const UPSTREAM_NAME = 'Open WebUI';
export const UPSTREAM_URL = 'https://github.com/open-webui/open-webui';
export const UPSTREAM_LICENSE_URL = 'https://github.com/open-webui/open-webui/blob/main/LICENSE';

export const productName = (branding: boolean | undefined) =>
	branding ? OPENMETTLE_NAME : UPSTREAM_NAME;

// Strings that name the Open WebUI project itself (its team, community, translations, sponsorship
// or version requirements) rather than the application on screen. They keep the name.
const UPSTREAM_PROJECT_KEYS = new Set([
	'By supporting the project through sponsorship or an enterprise license, you help us stay independent, ship new features faster, improve stability, and grow Open WebUI for the long haul.',
	'Help us translate Open WebUI!',
	'MCP support is experimental and its specification changes often, which can lead to incompatibilities. OpenAPI specification support is directly maintained by the Open WebUI team, making it the more reliable option for compatibility.',
	'Open WebUI version',
	'Open WebUI version (v{{OPEN_WEBUI_VERSION}}) is lower than required version (v{{REQUIRED_VERSION}})',
	'Participate in community leaderboards and evaluations! Syncing aggregated usage stats helps drive research and improvements to Open WebUI. Your privacy is paramount: no message content is ever shared.',
	'Running Open WebUI for a team?',
	'settings.admin.general.help.description',
	'You have more than 50 users, which often means this workspace is supporting organizational use. Open WebUI is free to use as-is, with no restrictions or hidden limits, and we want to keep it that way.',
	'Your entire contribution will go directly to the plugin developer; Open WebUI does not take any percentage. However, the chosen funding platform might have its own fees.'
]);
// "Open WebUI Community" and "the Open WebUI community" are the upstream sharing site.
const APPLICATION_MENTION = /Open WebUI(?! [Cc]ommunity)/g;

/** A translated string with the application's name changed to OpenMettle, unless it is about the upstream project. */
export const rebrandText = (text: string, key: string | string[] | undefined) => {
	const keys = Array.isArray(key) ? key : [key];
	if (
		typeof text !== 'string' ||
		keys.some((k) => k !== undefined && UPSTREAM_PROJECT_KEYS.has(k))
	) {
		return text;
	}
	return text.replace(APPLICATION_MENTION, OPENMETTLE_NAME);
};

let branding = false;

export const setOpenMettleBranding = (value: boolean | undefined) => {
	branding = value === true;
};

// i18next post-processor: applies rebrandText while the switch is on.
export const openMettlePostProcessor = {
	type: 'postProcessor' as const,
	name: 'openmettle',
	process: (value: string, key: string | string[]) => (branding ? rebrandText(value, key) : value)
};

/** The commit the image was built from, shortened; '' for a build without one. */
export const shortBuildHash = (hash: string | undefined | null) =>
	/^[0-9a-f]{7,64}$/i.test(hash ?? '') ? (hash as string).slice(0, 7) : '';

/** For the footer and Settings > About, e.g. "OpenMettle v0.1.0-dev · Open WebUI v0.13.3 · ab3186b". */
export const versionLine = (
	upstreamVersion: string | undefined,
	buildHash: string | undefined | null,
	noBuild = 'dev build'
) =>
	[
		`${OPENMETTLE_NAME} v${OPENMETTLE_VERSION}`,
		`${UPSTREAM_NAME} v${upstreamVersion || '?'}`,
		shortBuildHash(buildHash) || noBuild
	].join(' · ');

type ReplyMessage = {
	role?: string;
	model?: string;
	parentId?: string | null;
	models?: string[];
	arena?: boolean;
};

/**
 * Whether an assistant reply shows the model's avatar and name above its text. Open WebUI always
 * does. With the branding switch on, the name stays only where it tells replies apart: an arena
 * reply, a turn sent to several models at once, or a chat answered by more than one model on any
 * branch. Otherwise the reply is just text, as in ChatGPT; the name stays in the timestamp tooltip
 * and as a heading for screen readers.
 */
export const showsReplyHeader = (
	branding: boolean | undefined,
	history: { messages?: Record<string, ReplyMessage> } | undefined,
	message: ReplyMessage | undefined
) => {
	if (!branding || !message || message.arena) return true;
	const messages = history?.messages ?? {};
	const parent = message.parentId ? messages[message.parentId] : undefined;
	if ((parent?.models?.length ?? 1) > 1) return true;
	const repliedBy = new Set<string>();
	for (const m of Object.values(messages)) {
		if (m?.role === 'assistant' && m.model) repliedBy.add(m.model);
	}
	return repliedBy.size > 1;
};
