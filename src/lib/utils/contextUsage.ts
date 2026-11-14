type ContextMessage = {
	content?: unknown;
	output?: unknown[];
	tool_calls?: unknown;
	files?: unknown[];
	usage?: Record<string, unknown>;
	info?: { usage?: Record<string, unknown> };
};

export const estimateTokens = (value: unknown): number => {
	if (value === null || value === undefined || value === '') return 0;
	if (typeof value !== 'string') {
		try {
			value = JSON.stringify(value);
		} catch {
			value = String(value);
		}
	}
	return Math.max(1, Math.floor(String(value).length / 4));
};

export const estimateMessagesTokens = (messages: ContextMessage[]): number =>
	messages.reduce((total, message) => {
		// Structured output already includes the assistant text and tool calls.
		let next = total + 4;
		next += message.output?.length
			? estimateTokens(message.output)
			: estimateTokens(message.content) + estimateTokens(message.tool_calls);
		if (message.files?.length) {
			next += estimateTokens(
				JSON.stringify(message.files).replace(/data:[\w/+.;=%-]*;base64,[A-Za-z0-9+/=]*/g, '')
			);
		}
		return next;
	}, 0);

// Usage objects survive message copies between streaming events. Weak keys let old
// checkpoints disappear when a new usage snapshot or chat replaces them.
const usageCheckpoints = new WeakMap<object, number>();

export const captureUsageCheckpoint = (message: ContextMessage): void => {
	const usage = message.usage ?? message.info?.usage;
	if (usage) usageCheckpoints.set(usage, estimateMessagesTokens([message]));
};

export const estimateUsageGrowth = (message: ContextMessage): number => {
	const usage = message.usage ?? message.info?.usage;
	if (!usage) return 0;
	const tokens = estimateMessagesTokens([message]);
	if (!usageCheckpoints.has(usage)) {
		// shortcut: loaded chats anchor here; persist checkpoints if reloads must retain in-flight estimates.
		usageCheckpoints.set(usage, tokens);
	}
	return Math.max(0, tokens - usageCheckpoints.get(usage)!);
};

// Context wheel: how full the model's context is after the newest reply.

type WheelHistory = {
	currentId?: string | null;
	messages?: Record<
		string,
		ContextMessage & {
			parentId?: string | null;
			contextSummary?: unknown;
			context_summary?: unknown;
		}
	>;
};

type WheelModel = {
	id?: string;
	context_window?: unknown;
	max_output_tokens?: unknown;
	openai?: { context_window?: unknown; max_output_tokens?: unknown };
	info?: { base_model_id?: string | null };
};

const tokenCount = (value: unknown): number =>
	typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.trunc(value) : 0;

/**
 * Tokens the model held after the newest reply on the displayed branch that reported usage:
 * that call's prompt (instructions, tools and every earlier message) plus its completion.
 * Sibling branches are not counted, and a reply still streaming counts once it reports usage.
 * Replies older than a context summary describe a context that no longer exists.
 * `countTokens` is getUsageTokenCount, which reads the last call of a tool loop, not the sum.
 */
export const getMeasuredContextTokens = (
	history: WheelHistory | null | undefined,
	countTokens: (usage?: Record<string, unknown> | null) => number
): number | null => {
	const seen = new Set<string>();
	let id = history?.currentId;
	while (id && !seen.has(id)) {
		seen.add(id);
		const message = history?.messages?.[id];
		if (!message) break;
		const tokens = countTokens(message.usage ?? message.info?.usage);
		if (tokens > 0) return tokens;
		const summary = message.contextSummary ?? message.context_summary;
		if (typeof summary === 'string' && summary.trim()) break;
		id = message.parentId;
	}
	return null;
};

/**
 * Tokens a conversation can hold before the provider refuses the next request: the declared
 * `context_window` less the `max_output_tokens` it reserves for a reply (when declared and
 * smaller). A preset uses its base model's declaration. Null when no window is declared.
 */
export const getContextCapacity = (
	modelId: string | undefined,
	models: WheelModel[]
): number | null => {
	const find = (id?: string | null) => (id ? models.find((model) => model.id === id) : undefined);
	const declared = (model: WheelModel | undefined, key: 'context_window' | 'max_output_tokens') =>
		tokenCount(model?.[key]) || tokenCount(model?.openai?.[key]);
	let model = find(modelId);
	if (!declared(model, 'context_window')) model = find(model?.info?.base_model_id);
	const window = declared(model, 'context_window');
	if (!window) return null;
	const reserved = declared(model, 'max_output_tokens');
	return reserved < window ? window - reserved : window;
};

export type ContextWheelState = {
	tokens: number;
	capacity: number;
	percent: number;
	level: 'normal' | 'high' | 'full';
};

/** The ring's state. Percent is rounded down, so the level never runs ahead of the number shown. */
export const getContextWheel = (
	tokens: number | null | undefined,
	capacity: number | null | undefined
): ContextWheelState | null => {
	if (!capacity || capacity <= 0) return null;
	const used = tokenCount(tokens);
	const percent = Math.floor((used / capacity) * 100);
	return {
		tokens: used,
		capacity,
		percent,
		level: percent >= 90 ? 'full' : percent >= 75 ? 'high' : 'normal'
	};
};
