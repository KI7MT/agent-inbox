<script lang="ts">
  import { createEventDispatcher } from 'svelte'
  import type { Message } from './types'

  export let messages: Message[] = []
  export let loading = false
  export let selectedId = ''

  const dispatch = createEventDispatcher<{ select: string }>()

  function priorityColor(p: string): string {
    if (p === 'urgent') return 'text-red-400'
    if (p === 'action') return 'text-amber-400'
    return 'text-slate-500'
  }

  function statusBadge(s: string): string {
    switch (s) {
      case 'unread':      return 'bg-amber-500/20 text-amber-400'
      case 'read':        return 'bg-slate-600/30 text-slate-400'
      case 'approved':    return 'bg-emerald-500/20 text-emerald-400'
      case 'in_progress': return 'bg-sky-500/20 text-sky-400'
      case 'rejected':    return 'bg-red-500/20 text-red-400'
      case 'done':        return 'bg-slate-700/30 text-slate-500'
      default:            return 'bg-slate-700/30 text-slate-500'
    }
  }

  function formatTime(ts: string): string {
    if (!ts) return ''
    const d = new Date(ts.endsWith('Z') ? ts : ts + 'Z')
    const diff = Date.now() - d.getTime()
    if (diff < 3600_000) return Math.max(0, Math.floor(diff / 60_000)) + 'm ago'
    if (diff < 86_400_000) return Math.floor(diff / 3600_000) + 'h ago'
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
</script>

{#if loading}
  <div class="flex items-center justify-center py-8 text-slate-500 text-sm">Loading…</div>
{:else if messages.length === 0}
  <div class="flex items-center justify-center py-8 text-slate-500 text-sm">No messages</div>
{:else}
  {#each messages as msg (msg.id)}
    <button
      class="w-full text-left px-3 py-2 border-b border-slate-700/50 hover:bg-ink-800
             {selectedId === msg.id ? 'bg-ink-800' : ''}"
      on:click={() => dispatch('select', msg.id)}
    >
      <div class="flex items-center justify-between text-xs mb-1">
        <span class="text-slate-400">
          <span class="text-slate-300 font-medium">{msg.sender}</span>
          <span class="mx-1 text-slate-600">→</span>
          <span class="text-slate-300">{msg.recipient}</span>
        </span>
        <span class="text-slate-500">{formatTime(msg.timestamp)}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[10px] uppercase tracking-wider {priorityColor(msg.priority)}">
          {msg.priority}
        </span>
        <span class="text-xs px-1.5 py-0.5 rounded {statusBadge(msg.status)}">
          {msg.status.replace('_', ' ')}
        </span>
        {#if msg.parent_id}
          <span class="text-[10px] text-slate-500">↳</span>
        {/if}
      </div>
      <div class="text-sm text-slate-200 mt-1 truncate">{msg.subject}</div>
    </button>
  {/each}
{/if}
