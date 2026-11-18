import { createRoot } from 'react-dom/client';
import { RefractedText, type RefractedTextProps } from './components/refracted-text';

// Server titles rendered by the panel are plain text in the HTML:
//   <span class="rt-title" data-rt-title="Server name">…</span>
// This script replaces each one with the RefractedText component. The text
// stays in the page when scripts or WebGL 2.0 are unavailable. Only the title
// of a server's own page uses it: lists show a lightweight icon and plain text.

const REFRACTED_CONFIG: Omit<RefractedTextProps, 'text'> = {
  theme: 'dark',
  topColor: 'auto',
  bottomColor: 'auto',
  beamColor: 'auto',
  spectrumWarmColor: 'auto',
  spectrumMiddleColor: 'auto',
  spectrumCoolColor: 'auto',
  reveal: true,
  stagger: 0.55,
  liftDuration: 1.75,
  ease: 'power4.out',
  beamFollowsLift: false,
  animateBeam: true,
  openingDuration: 6.9,
  duration: 13.2,
  intensity: 1.2,
  dispersion: 1,
  colorIntensity: 1,
  beamPosition: 0.5,
  fixedBeam: false,
  paused: false,
  cursorMovesBeam: false,
  fontSize: '400px',
  fontFamily: "'ReactDrops Square Display', 'Arial Black', sans-serif",
  fontWeight: 900,
  letterSpacing: 'normal',
  extraBold: 2.25,
  fontHeight: 80,
  cornerRounding: 1,
};

// The component scales the word to its container width, so a long name on one
// line becomes unreadably small. Names wrap at word boundaries instead.
const MAX_LINE_LENGTH = 22;
const MAX_LINES = 3;
// Every title owns one WebGL context; browsers keep only about sixteen alive.
const MAX_WEBGL_LINES = 12;

export function wrapTitle(name: string, maxLength: number): string[] {
  const lines: string[] = [];
  let current = '';
  for (const word of name.trim().split(/\s+/).filter(Boolean)) {
    const candidate = current ? `${current} ${word}` : word;
    if (current && Array.from(candidate).length > maxLength) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function Title({ lines }: { lines: string[] }) {
  return (
    <span className="rt-title__lines">
      {lines.map((line, index) => (
        <RefractedText key={`${index}:${line}`} text={line} {...REFRACTED_CONFIG} />
      ))}
    </span>
  );
}

function mountTitles() {
  let budget = MAX_WEBGL_LINES;
  document.querySelectorAll<HTMLElement>('[data-rt-title]').forEach((element) => {
    const name = element.dataset.rtTitle ?? '';
    const lines = wrapTitle(name, MAX_LINE_LENGTH);
    // Keep the plain text when there is nothing to draw or no context to spare.
    if (!lines.length || lines.length > MAX_LINES || lines.length > budget) return;
    budget -= lines.length;
    element.classList.add('rt-title--ready');
    createRoot(element).render(<Title lines={lines} />);
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountTitles);
else mountTitles();
