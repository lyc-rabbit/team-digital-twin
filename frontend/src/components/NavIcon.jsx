import React from 'react'

/**
 * 一级菜单图标取自 iconfont「字节跳动官方图标库」IconPark Outline（Apache-2.0）。
 * 描边使用系统图标同色 brand-600（#4f46e5）。
 */
const ICONS = {
  cockpit: (
    <g fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="4">
      <path strokeLinejoin="round" d="M8.444 41.556A21.93 21.93 0 0 1 2 26C2 13.85 11.85 4 24 4s22 9.85 22 22a21.93 21.93 0 0 1-6.444 15.556" />
      <path d="M14.1 35.9A13.96 13.96 0 0 1 10 26c0-7.732 6.268-14 14-14" />
      <path strokeLinejoin="round" d="M24 26v-8" />
    </g>
  ),
  team: (
    <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="4">
      <circle cx="14" cy="29" r="5" />
      <circle cx="34" cy="29" r="5" />
      <circle cx="24" cy="9" r="5" />
      <path d="M24 44c0-5.523-4.477-10-10-10S4 38.477 4 44m40 0c0-5.523-4.477-10-10-10s-10 4.477-10 10m10-20c0-5.523-4.477-10-10-10s-10 4.477-10 10" />
    </g>
  ),
  work: (
    <g fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="4">
      <path d="M12 33H4V7h40v26z" />
      <path strokeLinecap="round" d="M16 22v4m8 7v6m0-21v8m8-12v12M12 41h24" />
    </g>
  ),
  growth: (
    <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="4">
      <circle cx="24" cy="12" r="8" />
      <path d="M42 44c0-9.941-8.059-18-18-18S6 34.059 6 44" />
    </g>
  ),
  relations: (
    <g fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="4">
      <path d="M35 16a5 5 0 1 0 0-10a5 5 0 0 0 0 10ZM13 29a5 5 0 1 0 0-10a5 5 0 0 0 0 10Z" />
      <path strokeLinecap="round" d="m30 13.575l-12.66 7.67m-.001 5.319l13.34 7.883" />
      <path d="M35 32a5 5 0 1 1 0 10a5 5 0 0 1 0-10Z" />
    </g>
  ),
  analysis: (
    <g fill="none" stroke="currentColor" strokeWidth="4">
      <path strokeLinejoin="round" d="M44 5H4v12h40z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="m4 41.03l12.176-12.3l6.579 6.3L30.798 27l4.48 4.368" />
      <path strokeLinecap="round" d="M44 16.172v26m-40-26v14M13.016 43H44M17 11h21m-28-.003h1" />
    </g>
  ),
  assets: (
    <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="4">
      <ellipse cx="24" cy="11" rx="20" ry="6" />
      <path d="M10.77 15.5C6.62 16.6 4 18.208 4 20c0 3.314 8.954 6 20 6s20-2.686 20-6c0-1.792-2.619-3.4-6.77-4.5c-3.526.933-8.158 1.5-13.23 1.5s-9.703-.567-13.23-1.5" />
      <path d="M10.77 24.5C6.62 25.6 4 27.208 4 29c0 3.314 8.954 6 20 6s20-2.686 20-6c0-1.792-2.619-3.4-6.77-4.5c-3.526.933-8.158 1.5-13.23 1.5s-9.703-.567-13.23-1.5" />
      <path d="M10.77 33.5C6.62 34.6 4 36.208 4 38c0 3.314 8.954 6 20 6s20-2.686 20-6c0-1.792-2.619-3.4-6.77-4.5c-3.526.934-8.158 1.5-13.23 1.5s-9.703-.566-13.23-1.5" />
    </g>
  ),
}

export default function NavIcon({ name, size = 16, className = '' }) {
  const inner = ICONS[name]
  if (!inner) return null
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      className={`flex-shrink-0 text-brand-600 ${className}`}
      aria-hidden="true"
    >
      {inner}
    </svg>
  )
}
