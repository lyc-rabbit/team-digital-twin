/** 全站时间：北京时间（Asia/Shanghai，UTC+8） */

export const TIMEZONE = 'Asia/Shanghai'
export const TZ_LABEL = '北京时间'

function parts(date = new Date()) {
  const fmt = new Intl.DateTimeFormat('en-GB', {
    timeZone: TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    hourCycle: 'h23',
  })
  return Object.fromEntries(fmt.formatToParts(date).map((p) => [p.type, p.value]))
}

/** YYYY-MM-DD */
export function beijingToday(date) {
  const p = parts(date)
  return `${p.year}-${p.month}-${p.day}`
}

/** datetime-local 控件：YYYY-MM-DDTHH:MM */
export function beijingDateTimeLocal(date) {
  const p = parts(date)
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

/** 给日历等需要带偏移的 ISO：无偏移则视为北京时间并补 +08:00 */
export function toBeijingISO(raw) {
  if (!raw) return raw
  const s = String(raw).trim().replace(' ', 'T')
  if (/[zZ]$/.test(s) || /[+-]\d{2}:\d{2}$/.test(s)) return s
  if (s.length <= 10) return `${s}T00:00:00+08:00`
  const body = s.length >= 19 ? s.slice(0, 19) : (s.length >= 16 ? `${s.slice(0, 16)}:00` : `${s}:00:00`)
  return `${body}+08:00`
}
