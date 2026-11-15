<script lang="ts">
	import { getContext } from 'svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n: any = getContext('i18n');
</script>

<div class="mettle-welcome">
	<div class="mettle-art">
		<img
			src="{WEBUI_BASE_URL}/static/openmettle/mettle.webp"
			alt={$i18n.t('Mettle, the OpenMettle robot with a red privacy status tab')}
			width="128"
			height="128"
			draggable="false"
		/>
	</div>
	<div class="mettle-name">Open<span>Mettle</span></div>
	<p>{$i18n.t('Bring out the best in your AI.')}</p>
</div>

<style>
	/* One focal point: Mettle, lifted by light rather than by a box (a pool of light behind him and a
	   soft contact shadow below), with space around him. Vermilion appears only in the wordmark;
	   the send button is the page's other accent. */
	.mettle-welcome {
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-bottom: 2.25rem;
		color: var(--mettle-ink, #24272c);
	}

	.mettle-art {
		position: relative;
		isolation: isolate;
		display: grid;
		place-items: center;
		width: 11rem;
		height: 9.5rem;
		margin-bottom: 0.75rem;
	}

	.mettle-art::before {
		content: '';
		position: absolute;
		inset: -1rem -2.5rem -0.5rem;
		z-index: -1;
		background:
			radial-gradient(closest-side, rgb(255 255 255 / 90%), rgb(255 255 255 / 0%)),
			radial-gradient(closest-side, rgb(231 71 60 / 10%), rgb(231 71 60 / 0%) 85%);
	}

	.mettle-art::after {
		content: '';
		position: absolute;
		bottom: 0.6rem;
		left: 22%;
		right: 22%;
		height: 0.9rem;
		z-index: -1;
		background: radial-gradient(closest-side, rgb(25 28 33 / 22%), rgb(25 28 33 / 0%));
	}

	:global(.dark) .mettle-art::before {
		background:
			radial-gradient(closest-side, rgb(242 235 221 / 13%), rgb(242 235 221 / 0%)),
			radial-gradient(closest-side, rgb(231 71 60 / 14%), rgb(231 71 60 / 0%) 85%);
	}

	:global(.dark) .mettle-art::after {
		background: radial-gradient(closest-side, rgb(0 0 0 / 55%), rgb(0 0 0 / 0%));
	}

	img {
		width: 8rem;
		height: 8rem;
		object-fit: contain;
		filter: drop-shadow(0 6px 10px rgb(25 28 33 / 16%));
	}

	:global(.dark) img {
		filter: drop-shadow(0 0 1px rgb(242 235 221 / 30%)) drop-shadow(0 8px 14px rgb(0 0 0 / 45%));
	}

	/* A single, short arrival; nothing loops, and nothing moves for people who ask for less motion. */
	@media (prefers-reduced-motion: no-preference) {
		img {
			animation: mettle-arrive 420ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
		}
	}

	@keyframes mettle-arrive {
		from {
			opacity: 0;
			transform: translateY(6px) scale(0.98);
		}
	}

	.mettle-name {
		font-size: 1.625rem;
		font-weight: 750;
		letter-spacing: -0.055em;
		line-height: 1.2;
	}

	span {
		color: var(--mettle-emphasis, #b72f26);
	}

	p {
		margin-top: 0.375rem;
		font-size: 0.875rem;
		color: var(--mettle-muted, #64605a);
	}
</style>
