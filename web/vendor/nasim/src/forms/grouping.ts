// Writing a number with a separator every three digits while it is typed, and taking it back to the
// plain digits the form keeps. The form never sees a separator: only the box does.

const SEPARATORS = /[,،٬\s]/g;
const PLAIN = /^-?[\d۰-۹٠-٩]*(?:[.٫][\d۰-۹٠-٩]*)?$/;

// Not a `\B` lookahead: that treats Persian digits as non-word characters and would skip them.
function threes(whole: string): string {
  let out = '';
  for (let index = 0; index < whole.length; index += 1) {
    if (index > 0 && (whole.length - index) % 3 === 0) out += ',';
    out += whole.charAt(index);
  }
  return out;
}

/** What was typed without its separators ("1,234" → "1234"). */
export function ungroup(text: string): string {
  return text.replace(SEPARATORS, '');
}

/**
 * The text with a comma every three digits of its whole part. Anything that is not a plain number (a
 * letter, two points) is shown as it is, so a typo stays visible instead of being tidied away.
 */
export function group(text: string): string {
  const plain = ungroup(text);
  if (!PLAIN.test(plain)) return text;
  const sign = plain.startsWith('-') ? '-' : '';
  const body = sign ? plain.slice(1) : plain;
  const point = body.search(/[.٫]/);
  const whole = point === -1 ? body : body.slice(0, point);
  const rest = point === -1 ? '' : body.slice(point);
  return `${sign}${threes(whole)}${rest}`;
}

/** How many characters before `caret` are not separators: the caret's place once separators move. */
export function significantBefore(text: string, caret: number): number {
  return ungroup(text.slice(0, caret)).length;
}

/** The caret position in `text` that has `count` non-separator characters before it. */
export function caretAfter(text: string, count: number): number {
  if (count <= 0) return 0;
  let seen = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (!/[,،٬\s]/.test(text.charAt(index))) seen += 1;
    if (seen === count) return index + 1;
  }
  return text.length;
}
