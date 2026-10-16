// Backend diagnostics (a command's stderr) can echo credentials. Everything that reaches the ledger goes
// through redact() first; the rules are deliberately blunt: a message with a hidden word is better than a
// ledger with a token in it.
const MARK = '[redacted]';
const NAME = '(?:key|token|secret|password|passwd|pwd|credential|cookie|session|authorization|auth(?![a-z]))';

const RULES: Array<[RegExp, string]> = [
  // Header lines that carry credentials: the whole value to the end of the line (scheme and credentials, or every cookie).
  [/\b((?:Proxy-)?Authorization|Set-Cookie|Cookie)\s*[:=][^\r\n]*/giu, `$1: ${MARK}`],
  // JSON web tokens and well known key shapes
  [/\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}/gu, MARK],
  [/\b(?:sk|pk|rk)-[A-Za-z0-9_-]{8,}/gu, MARK],
  [/\bgh[pousr]_[A-Za-z0-9]{20,}/gu, MARK],
  [/\bxox[abprs]-[A-Za-z0-9-]{10,}/gu, MARK],
  [/\bAKIA[0-9A-Z]{16}\b/gu, MARK],
  [/\bAIza[0-9A-Za-z_-]{20,}/gu, MARK],
  // credentials inside a URL: scheme://user:pass@host or scheme://token@host
  [/(\b[a-z][a-z0-9+.-]*:\/\/)[^/\s@]+@/giu, `$1${MARK}@`],
  // Authorization header values written without the header name
  [/\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{6,}/giu, `$1 ${MARK}`],
  // NAME=value, NAME: value, "name": "value", 'name': 'value' (single or double quoted names and values)
  [new RegExp(`(["']?)\\b([A-Za-z0-9_.-]*${NAME}[A-Za-z0-9_.-]*)\\b(["']?\\s*[=:]\\s*)("(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*'|[^\\s,;}]+)`, 'giu'), `$1$2$3${MARK}`],
  // command line flags that carry a secret: --api-key abc, --token=abc
  [new RegExp(`(--[a-z0-9-]*(?:key|token|secret|password|passwd)[a-z0-9-]*)(\\s+|=)(\\S+)`, 'giu'), `$1$2${MARK}`],
  // long strings that mix letters and digits: hex digests, base64 blobs, opaque ids
  [/(?<![A-Za-z0-9+/_-])(?=[A-Za-z0-9+/_-]*[0-9])(?=[A-Za-z0-9+/_-]*[A-Za-z])[A-Za-z0-9+/_-]{32,}={0,2}/gu, MARK],
];

export function redact(text: string): string {
  let out = text;
  for (const [pattern, replacement] of RULES) out = out.replace(pattern, replacement);
  return out;
}
