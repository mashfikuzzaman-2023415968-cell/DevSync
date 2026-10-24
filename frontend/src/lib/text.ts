/** Text length as the server counts it: Unicode code points after NFC normalisation (an emoji
 * is one character; a precomposed Bangla letter like "য়" becomes two). Form limits use this so
 * a field the form accepts is one the server accepts too. */
export function textLength(text: string): number {
  return Array.from(text.normalize("NFC")).length;
}
