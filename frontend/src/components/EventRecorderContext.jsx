import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { Plus } from 'lucide-react'
import EventLogger from './EventLogger.jsx'
import EventDraftWizard from './EventDraftWizard.jsx'

const Ctx = createContext({ open: () => {}, openDraft: () => {}, close: () => {} })

const IDLE = { mode: 'idle', context: {}, queue: [] }

function toLoggerContext(draft, match, index, total) {
  return {
    source: draft.source || 'calendar-draft',
    event_type: match.event_type,
    event_tag: match.event_tag,
    event_time: draft.event_time,
    created_by: draft.created_by,
    person_id: match.person_id || '',
    related_persons: match.related_persons || [],
    fields: match.suggested_fields || { facts: draft.draft_text },
    draft_text: draft.draft_text,
    queue_index: index,
    queue_total: total,
  }
}

export function EventRecorderProvider({ members, children, onSaved }) {
  const [state, setState] = useState(IDLE)
  const open = useCallback((context = {}) => setState({ mode: 'logger', context, queue: [] }), [])
  const openDraft = useCallback((context = {}) => setState({ mode: 'draft', context, queue: [] }), [])
  const close = useCallback(() => setState(IDLE), [])

  const openQueue = useCallback((items) => {
    if (!items?.length) {
      setState(IDLE)
      return
    }
    const [first, ...rest] = items
    setState({ mode: 'logger', context: first, queue: rest })
  }, [])

  const advance = useCallback((saved) => {
    if (saved) onSaved?.()
    setState((cur) => {
      if (!cur.queue.length) return IDLE
      const [next, ...rest] = cur.queue
      return { mode: 'logger', context: next, queue: rest }
    })
  }, [onSaved])

  const confirmDraft = useCallback((draft) => {
    const matches = draft.matches || []
    const items = matches.map((m, i) => toLoggerContext(draft, m, i + 1, matches.length))
    openQueue(items)
  }, [openQueue])

  const value = useMemo(() => ({ open, openDraft, close }), [open, openDraft, close])

  return (
    <Ctx.Provider value={value}>
      {children}
      {state.mode === 'draft' && (
        <div className="fixed inset-0 z-[80] bg-black/40 flex items-start justify-center overflow-y-auto p-4">
          <div className="w-full max-w-3xl my-6 bg-slate-50 rounded-2xl shadow-2xl border border-slate-200">
            <EventDraftWizard
              members={members}
              context={state.context}
              onClose={close}
              onConfirm={confirmDraft}
            />
          </div>
        </div>
      )}
      {state.mode === 'logger' && (
        <div className="fixed inset-0 z-[80] bg-black/40 flex items-start justify-center overflow-y-auto p-4">
          <div className="w-full max-w-3xl my-6 bg-slate-50 rounded-2xl shadow-2xl border border-slate-200">
            <EventLogger
              members={members}
              context={state.context}
              modal
              onClose={close}
              onSkip={() => advance(false)}
              onSaved={() => advance(true)}
            />
          </div>
        </div>
      )}
    </Ctx.Provider>
  )
}

export function useEventRecorder() {
  return useContext(Ctx)
}

export function RecordEventButton({ context, className, label = '记录事件' }) {
  const { open } = useEventRecorder()
  return (
    <button
      type="button"
      onClick={() => open(context || {})}
      className={className || 'inline-flex items-center gap-1.5 text-xs font-medium text-white bg-brand-600 hover:bg-brand-700 px-3 py-1.5 rounded-lg'}
    >
      <Plus size={13} />
      {label}
    </button>
  )
}

export function RecordEventDraftButton({ context, className, label = '记录事件' }) {
  const { openDraft } = useEventRecorder()
  return (
    <button
      type="button"
      onClick={() => openDraft(context || {})}
      className={className || 'inline-flex items-center gap-1.5 text-xs font-medium text-white bg-brand-600 hover:bg-brand-700 px-3 py-1.5 rounded-lg'}
    >
      <Plus size={13} />
      {label}
    </button>
  )
}
