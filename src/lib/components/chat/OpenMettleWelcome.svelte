<script lang="ts">
	import { getContext } from 'svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n: any = getContext('i18n');
</script>

<div class="mettle-welcome">
	<img
		src="{WEBUI_BASE_URL}/static/openmettle/mettle.webp"
		alt={$i18n.t('Mettle, the OpenMettle robot with a red privacy status tab')}
		width="112"
		height="112"
		draggable="false"
	/>
	<div class="mettle-name">Open<span>Mettle</span></div>
	<p>{$i18n.t('Bring out the best in your AI.')}</p>
</div>

<style>
	.mettle-welcome {
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-bottom: 1.75rem;
		color: var(--mettle-ink, #24272c);
	}

	img {
		object-fit: contain;
	}

	.mettle-name {
		font-size: 1.5rem;
		font-weight: 750;
		letter-spacing: -0.055em;
		line-height: 1.25;
	}

	span {
		color: var(--mettle-emphasis, #b72f26);
	}

	p {
		margin-top: 0.5rem;
		font-size: 0.875rem;
		color: var(--mettle-muted, #64605a);
	}
</style>
