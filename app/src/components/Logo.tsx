const MASK_ID = 'logo-body-outline'

/** The person's body as thick round lines, drawn twice by the mask to leave only its outline. */
function BodyShape() {
  return (
    <>
      <circle cx="27" cy="8" r="3.4" />
      <path d="M26 16 L22.5 28" />
      <path d="M20 16 Q15 17 15 23 L15 27" />
      <path d="M22.5 28 L29 35 L28.5 44" />
      <path d="M22.5 28 L18 36 L12 44" />
      <path d="M26 17 L31 23 L37 20.5" />
    </>
  )
}

/** The site logo: the outline of a person walking uphill with a hiking stick. */
export function Logo() {
  return (
    <svg className="logo" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <mask id={MASK_ID} maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48">
        <g fill="white" stroke="white" strokeWidth="6.4" strokeLinecap="round" strokeLinejoin="round">
          <BodyShape />
        </g>
        <g fill="black" stroke="black" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
          <BodyShape />
        </g>
      </mask>
      <rect className="logo-hiker" width="48" height="48" mask={`url(#${MASK_ID})`} />
      <path className="logo-stick" d="M36 11 L39.5 46" />
    </svg>
  )
}
