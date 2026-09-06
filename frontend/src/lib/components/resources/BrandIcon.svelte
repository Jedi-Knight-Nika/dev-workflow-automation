<script lang="ts">
  import {
    SiAnthropic,
    SiGithub,
    SiGitlab,
    SiGooglegemini,
    SiJira,
    SiLinear,
    SiNpm,
    SiOpenai,
    SiPypi,
    SiTrello
  } from '@icons-pack/svelte-simple-icons';

  let {
    brand,
    size = 20,
    labelled = false
  }: { brand: string; size?: number; labelled?: boolean } = $props();

  const normalized = $derived(brand.toLowerCase().replaceAll(/[^a-z]/g, ''));
  const title = $derived(labelled ? brand : '');
</script>

<span class="brand-icon" style={`--icon-size: ${size}px`} aria-hidden={!labelled}>
  {#if normalized.includes('github')}
    <SiGithub {size} {title} />
  {:else if normalized.includes('gitlab')}
    <SiGitlab {size} {title} color="#FC6D26" />
  {:else if normalized.includes('trello')}
    <SiTrello {size} {title} color="#0C66E4" />
  {:else if normalized.includes('linear')}
    <SiLinear {size} {title} color="#7C6FF7" />
  {:else if normalized.includes('anthropic') || normalized.includes('claude')}
    <SiAnthropic {size} {title} color="#D97757" />
  {:else if normalized.includes('openai') || normalized.includes('gpt')}
    <SiOpenai {size} {title} color="#10A37F" />
  {:else if normalized.includes('google') || normalized.includes('gemini')}
    <SiGooglegemini {size} {title} color="#8E75FF" />
  {:else if normalized.includes('npm')}
    <SiNpm {size} {title} color="#CB3837" />
  {:else if normalized.includes('pypi') || normalized.includes('python')}
    <SiPypi {size} {title} color="#3775A9" />
  {:else if normalized.includes('jira') || normalized.includes('atlassian')}
    <SiJira {size} {title} color="#2684FF" />
  {:else}
    <span class="fallback" style={`font-size: ${Math.max(8, size * 0.45)}px`}>AI</span>
  {/if}
</span>

<style>
  .brand-icon {
    display: inline-grid;
    width: var(--icon-size);
    height: var(--icon-size);
    flex: none;
    place-items: center;
    color: var(--color-text);
  }
  .fallback {
    font-weight: 900;
    letter-spacing: -0.06em;
  }
</style>
