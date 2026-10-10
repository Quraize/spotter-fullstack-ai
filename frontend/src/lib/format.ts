const pad2 = (n: number) => String(n).padStart(2, '0')

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${pad2(minutes % 60)}m`
}

export function formatMiles(miles: number, decimals = 0): string {
  const text = miles.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  return `${text} mi`
}

export function formatLoad(lb: number): string {
  return `${Math.round(lb).toLocaleString('en-US')} lb`
}

export function formatRisk(value: number): string {
  return value.toFixed(2)
}

const dateTimeFormat = new Intl.DateTimeFormat('en-US', {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

const timeFormat = new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** e.g. "Sat, Oct 11, 14:05" in the browser's time zone. */
export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

/** e.g. "14:05" in the browser's time zone. */
export function formatTime(iso: string): string {
  return timeFormat.format(new Date(iso))
}

const LOCAL_DATETIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/

/**
 * Convert an <input type="datetime-local"> value, which is in the browser's
 * local time, to ISO 8601 with the browser's UTC offset for that instant.
 */
export function toIsoWithOffset(localDateTime: string): string {
  const match = LOCAL_DATETIME.exec(localDateTime)
  if (!match) throw new Error(`Invalid date-time: ${localDateTime}`)
  const [, year, month, day, hour, minute, second = '00'] = match
  const date = new Date(+year, +month - 1, +day, +hour, +minute, +second)
  if (Number.isNaN(date.getTime())) throw new Error(`Invalid date-time: ${localDateTime}`)
  const offsetMinutes = -date.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const abs = Math.abs(offsetMinutes)
  return `${year}-${month}-${day}T${hour}:${minute}:${pad2(+second)}${sign}${pad2(Math.floor(abs / 60))}:${pad2(abs % 60)}`
}

/** The next full hour, as a datetime-local value. */
export function defaultDepartureLocal(now: Date = new Date()): string {
  const d = new Date(now.getTime())
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}
