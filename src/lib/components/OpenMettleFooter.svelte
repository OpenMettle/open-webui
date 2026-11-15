<script lang="ts">
	// Fork credit and build identity, shown whatever the branding switch says.
	import { getContext } from 'svelte';
	import { WEBUI_BUILD_HASH, WEBUI_VERSION } from '$lib/constants';
	import {
		UPSTREAM_LICENSE_URL,
		UPSTREAM_URL,
		shortBuildHash,
		versionLine
	} from '$lib/utils/openmettle';

	const i18n: any = getContext('i18n');

	export let className = '';

	$: line = versionLine(WEBUI_VERSION, WEBUI_BUILD_HASH, $i18n.t('dev build'));
	$: [openmettle, upstream, build] = line.split(' · ');
</script>

<div
	class="text-[0.6875rem] leading-4 text-gray-600 dark:text-gray-400 select-text {className}"
	data-openmettle-footer
	title={line}
>
	<span>{openmettle}</span> ·
	<span
		>{$i18n.t('a fork of')}
		<a class="underline" href={UPSTREAM_URL} target="_blank" rel="noopener noreferrer">{upstream}</a
		>
		(<a class="underline" href={UPSTREAM_LICENSE_URL} target="_blank" rel="noopener noreferrer"
			>{$i18n.t('License')}</a
		>)</span
	>
	·
	<span class={shortBuildHash(WEBUI_BUILD_HASH) ? 'font-mono' : ''} title={WEBUI_BUILD_HASH}
		>{build}</span
	>
</div>
