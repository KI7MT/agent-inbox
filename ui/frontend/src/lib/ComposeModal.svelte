<script lang="ts">
  import { createEventDispatcher } from 'svelte'
  import type { AgentInfo } from './types'

  export let show = false
  export let agents: AgentInfo[] = []
  export let operator = 'operator'
  export let replyTo: { sender: string; subject: string } | null = null

  let recipient = ''
  let priority = 'info'
  let subject = ''
  let body = ''
  let error = ''
  let sending = false

  const dispatch = createEventDispatcher<{
    send: { recipient: string; priority: string; subject: string; body: string }
    close: void
  }>()

  $: if (show && replyTo) {
    recipient = replyTo.sender
    subject = replyTo.subject.toLowerCase().startsWith('re:')
      ? replyTo.subject
      : `Re: ${replyTo.subject}`
  }
  $: if (!show) {
    recipient = ''
    priority = 'info'
    subject = ''
    body = ''
    error = ''
    sending = false
  }

  function close() {
    dispatch('close')
  }

  function submit() {
    error = ''
    if (!recipient) { error = 'recipient required'; return }
    if (!subject) { error = 'subject required'; return }
    sending = true
    dispatch('send', { recipient, priority, subject, body })
  }

  // Parent calls these via bind:this when send completes / errors.
  export function onSent() {
    sending = false
    dispatch('close')
  }
  export function onError(msg: string) {
    sending = false
    error = msg
  }
</script>

<svelte:window on:keydown={(e) => { if (show && e.key === 'Escape') close() }} />

{#if show}
  <div class="fixed inset-0 z-50">
    <button type="button"
            class="absolute inset-0 w-full h-full bg-black/60 cursor-default"
            aria-label="Close dialog"
            on:click={close}></button>
    <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
    <div class="bg-ink-800 border border-slate-700 rounded shadow-xl w-[600px] max-w-[90vw] pointer-events-auto"
         role="dialog"
         aria-modal="true"
         aria-labelledby="compose-title">
      <header class="px-4 py-2 border-b border-slate-700 flex justify-between items-center">
        <h2 id="compose-title" class="text-slate-100 font-medium">
          {replyTo ? 'Reply' : 'New message'}
        </h2>
        <button class="text-slate-400 hover:text-slate-200" on:click={close} aria-label="Close">×</button>
      </header>

      <div class="p-4 space-y-3">
        <label class="block text-xs text-slate-400">
          To
          <select bind:value={recipient}
                  class="mt-1 w-full bg-ink-700 text-slate-200 rounded px-2 py-1 border border-slate-600">
            <option value="">(select recipient)</option>
            {#each agents as a (a.name)}
              <option value={a.name}>{a.name}</option>
            {/each}
            <option value="all">all (broadcast)</option>
          </select>
        </label>

        <label class="block text-xs text-slate-400">
          Priority
          <select bind:value={priority}
                  class="mt-1 w-full bg-ink-700 text-slate-200 rounded px-2 py-1 border border-slate-600">
            <option value="info">info</option>
            <option value="action">action (needs approval)</option>
            <option value="urgent">urgent (needs approval)</option>
          </select>
        </label>

        <label class="block text-xs text-slate-400">
          Subject
          <input bind:value={subject}
                 class="mt-1 w-full bg-ink-700 text-slate-200 rounded px-2 py-1 border border-slate-600"
                 placeholder="Short subject line" />
        </label>

        <label class="block text-xs text-slate-400">
          Body (markdown)
          <textarea bind:value={body}
                    class="mt-1 w-full h-40 bg-ink-700 text-slate-200 rounded px-2 py-1 border border-slate-600 font-mono text-xs"
                    placeholder="What do you want them to know?"></textarea>
        </label>

        {#if error}
          <div class="text-xs text-red-400">{error}</div>
        {/if}

        <div class="text-xs text-slate-500">
          From: <span class="text-slate-300">{operator}</span>
        </div>
      </div>

      <footer class="px-4 py-2 border-t border-slate-700 flex justify-end gap-2">
        <button class="text-xs px-3 py-1.5 rounded text-slate-300 hover:text-slate-100"
                on:click={close}>
          Cancel
        </button>
        <button class="text-xs px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-medium disabled:opacity-50"
                disabled={sending || !recipient || !subject}
                on:click={submit}>
          {sending ? 'Sending…' : 'Send'}
        </button>
      </footer>
    </div>
    </div>
  </div>
{/if}
