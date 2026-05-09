<script lang="ts">
  import { createEventDispatcher } from 'svelte'
  import type { AgentInfo, ViewName } from './types'

  export let agents: AgentInfo[] = []
  export let pendingCount = 0
  export let view: ViewName = 'pending_approval'
  export let selectedRecipient = ''

  const dispatch = createEventDispatcher<{
    select: { view: ViewName; recipient?: string }
  }>()

  function selectPending() {
    dispatch('select', { view: 'pending_approval' })
  }
  function selectAll() {
    dispatch('select', { view: 'all' })
  }
  function selectAgent(name: string) {
    dispatch('select', { view: 'for_recipient', recipient: name })
  }
</script>

<aside class="w-56 bg-ink-800 border-r border-slate-700 flex flex-col h-full overflow-y-auto">
  <div class="px-3 py-2 text-[11px] uppercase tracking-wider text-slate-500">Views</div>
  <button
    class="text-left px-3 py-1.5 text-sm hover:bg-ink-700 flex justify-between items-center
           {view === 'pending_approval' ? 'bg-ink-700 text-amber-300' : 'text-slate-300'}"
    on:click={selectPending}
  >
    <span>Pending approval</span>
    {#if pendingCount > 0}
      <span class="text-xs bg-amber-500/20 text-amber-300 rounded-full px-2 py-0.5">{pendingCount}</span>
    {/if}
  </button>
  <button
    class="text-left px-3 py-1.5 text-sm hover:bg-ink-700
           {view === 'all' ? 'bg-ink-700 text-slate-200' : 'text-slate-300'}"
    on:click={selectAll}
  >
    All recent
  </button>

  <div class="px-3 py-2 mt-2 text-[11px] uppercase tracking-wider text-slate-500">Agents</div>
  {#if agents.length === 0}
    <div class="px-3 py-2 text-xs text-slate-500 italic">
      No briefs found.<br/>
      Drop *.md files into the briefs dir.
    </div>
  {:else}
    {#each agents as a (a.name)}
      <button
        class="text-left px-3 py-1.5 text-sm hover:bg-ink-700 flex justify-between items-center
               {view === 'for_recipient' && selectedRecipient === a.name ? 'bg-ink-700 text-slate-200' : 'text-slate-300'}"
        on:click={() => selectAgent(a.name)}
      >
        <span class="flex items-center gap-1.5">
          {#if a.is_operator}
            <span class="text-amber-400">★</span>
          {/if}
          {a.name}
        </span>
        {#if a.pending_mail > 0}
          <span class="text-xs bg-slate-700 text-slate-300 rounded-full px-2 py-0.5">{a.pending_mail}</span>
        {/if}
      </button>
    {/each}
  {/if}
</aside>
