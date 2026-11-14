<script lang="ts">
	import { getContext } from 'svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import type { ContextWheelState } from '$lib/utils/contextUsage';

	const i18n: any = getContext('i18n');

	// From getContextWheel. `measured` is false until a reply on this branch has reported usage.
	export let wheel: ContextWheelState;
	export let measured = false;
	// False where the chat is compacted automatically, so it never has to be restarted.
	export let suggestNewChat = true;
	export let onClick: () => void = () => {};

	const RADIUS = 7;
	const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

	$: fraction = Math.min(1, wheel.tokens / wheel.capacity);
	$: capacity = wheel.capacity.toLocaleString();
	$: summary = measured
		? $i18n.t('{{used}} of {{capacity}} tokens ({{percent}}%), including instructions and tools', {
				used: wheel.tokens.toLocaleString(),
				capacity,
				percent: wheel.percent
			})
		: $i18n.t('Context use appears after the first reply. Room for {{capacity}} tokens.', {
				capacity
			});
	$: hint =
		wheel.level === 'full' && suggestNewChat
			? $i18n.t('Nearly full: start a new chat to carry on.')
			: '';
	$: tooltip = hint ? `${summary}. ${hint}` : summary;
	$: ringClass =
		wheel.level === 'full'
			? 'text-red-600 dark:text-red-400'
			: wheel.level === 'high'
				? 'text-amber-600 dark:text-amber-400'
				: 'text-gray-500 dark:text-gray-400';
</script>

<Tooltip content={tooltip} placement="top">
	<button
		type="button"
		aria-label={`${$i18n.t('Context usage')}: ${tooltip}`}
		data-context-level={wheel.level}
		class="context-wheel flex items-center gap-1 self-center rounded-full p-1.5 text-xs transition hover:bg-gray-50/40 dark:hover:bg-gray-800/40"
		on:click={onClick}
	>
		<svg viewBox="0 0 18 18" class="size-[1.125rem] -rotate-90" fill="none" aria-hidden="true">
			<circle
				cx="9"
				cy="9"
				r={RADIUS}
				stroke="currentColor"
				stroke-width="2.25"
				class="text-gray-200 dark:text-gray-700"
			/>
			{#if fraction > 0}
				<circle
					cx="9"
					cy="9"
					r={RADIUS}
					stroke="currentColor"
					stroke-width="2.25"
					stroke-linecap="round"
					stroke-dasharray={`${fraction * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
					class={ringClass}
				/>
			{/if}
		</svg>
		{#if wheel.level !== 'normal'}
			<!-- The percentage, not colour alone, marks a nearly full context. -->
			<span class="font-medium tabular-nums {ringClass}">{wheel.percent}%</span>
		{/if}
	</button>
</Tooltip>
